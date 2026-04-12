from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from app.core.config import get_settings
from app.core.exceptions import ValidationError

TARGET_COOKIE_NAMES = {"SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"}
CHROMIUM_SOURCES = {
    "edge": {
        "label": "Microsoft Edge",
        "user_data_dir": Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data",
        "channel": "msedge",
    },
    "chrome": {
        "label": "Google Chrome",
        "user_data_dir": Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
        "channel": "chrome",
    },
}
IGNORED_PROFILE_DIRS = {
    "System Profile",
    "Guest Profile",
    "Crashpad",
    "ShaderCache",
    "SwReporter",
}


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


class BrowserCookieLockedError(RuntimeError):
    pass


def discover_bilibili_browser_sources() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for browser, config in CHROMIUM_SOURCES.items():
        user_data_dir = Path(config["user_data_dir"])
        if not user_data_dir.exists():
            continue

        profiles = _discover_profiles(user_data_dir, browser)
        default_profile_id = _detect_default_profile_id(user_data_dir, browser, profiles)
        sources.append(
            {
                "browser": browser,
                "label": str(config["label"]),
                "user_data_dir": str(user_data_dir),
                "default_profile_id": default_profile_id,
                "profiles": profiles,
            }
        )
    return sources


def import_bilibili_auth_from_browser(
    *,
    browser: str | None = None,
    profile_directory: str | None = None,
    user_data_dir: str | None = None,
) -> dict[str, Any]:
    if os.name != "nt":
        raise ValidationError(message="当前仅支持在 Windows 环境中自动读取浏览器 Cookie。")

    resolved_browser, resolved_user_data_dir = _resolve_user_data_dir(
        browser=browser,
        user_data_dir=user_data_dir,
    )
    profile_dir = _resolve_profile_directory(
        user_data_dir=resolved_user_data_dir,
        browser=resolved_browser,
        profile_directory=profile_directory,
    )
    cookies_db_path = _resolve_cookie_database_path(profile_dir)
    if cookies_db_path is None:
        raise ValidationError(message="未找到对应配置目录下的浏览器 Cookie 数据库。")

    try:
        decrypted_cookie_map = _read_bilibili_cookies_from_database(
            cookies_db_path=cookies_db_path,
            user_data_dir=resolved_user_data_dir,
        )
        cookie = _compose_cookie_string(decrypted_cookie_map)
    except BrowserCookieLockedError:
        cookie = _capture_bilibili_cookie_via_playwright(browser=resolved_browser)

    if not cookie:
        raise ValidationError(
            message="没有在所选浏览器配置中读取到 Bilibili 登录 Cookie，请确认当前配置已登录 B站。"
        )

    account_profile, validation_message = fetch_bilibili_account_profile(cookie)
    return {
        "cookie": cookie,
        "account_profile": account_profile,
        "validation_message": validation_message,
        "import_source": {
            "browser": resolved_browser,
            "profile_directory": profile_dir.name,
            "user_data_dir": str(resolved_user_data_dir),
            "label": f"{_browser_label(resolved_browser)} / {profile_dir.name}",
        },
    }


def fetch_bilibili_account_profile(cookie: str) -> tuple[dict[str, Any] | None, str | None]:
    normalized_cookie = str(cookie or "").strip()
    if not normalized_cookie:
        return None, None

    settings = get_settings()
    try:
        response = httpx.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers={
                "User-Agent": settings.bilibili_user_agent,
                "Accept": "application/json, text/plain, */*",
                "Cookie": normalized_cookie,
                "Referer": "https://www.bilibili.com/",
            },
            timeout=12.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, "已保存登录态，但暂时无法验证账号信息。"

    if payload.get("code") not in {0, None}:
        return None, "已保存登录态，但 B站未返回有效的账号信息。"

    data = payload.get("data") or {}
    is_login = bool(data.get("isLogin"))
    if not is_login:
        return {"is_login": False}, "当前 Cookie 已保存，但 B站未识别为登录状态。"

    return (
        {
            "is_login": True,
            "mid": str(data.get("mid") or "").strip() or None,
            "username": str(data.get("uname") or "").strip() or None,
            "level": int(data.get("level_info", {}).get("current_level"))
            if isinstance(data.get("level_info"), dict)
            and data.get("level_info", {}).get("current_level") is not None
            else None,
            "avatar_url": str(data.get("face") or "").strip() or None,
        },
        None,
    )


def _discover_profiles(user_data_dir: Path, browser: str) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    candidates: list[Path] = []
    default_dir = user_data_dir / "Default"
    if default_dir.exists():
        candidates.append(default_dir)
    candidates.extend(
        sorted(
            path
            for path in user_data_dir.iterdir()
            if path.is_dir()
            and path.name.startswith("Profile ")
            and path.name not in IGNORED_PROFILE_DIRS
        )
    )

    seen: set[str] = set()
    for profile_dir in candidates:
        if profile_dir.name in seen:
            continue
        seen.add(profile_dir.name)
        profiles.append(
            {
                "id": f"{browser}:{profile_dir.name}",
                "label": "默认配置" if profile_dir.name == "Default" else profile_dir.name,
                "directory_name": profile_dir.name,
                "cookie_db_exists": _resolve_cookie_database_path(profile_dir) is not None,
            }
        )
    return profiles


def _detect_default_profile_id(
    user_data_dir: Path,
    browser: str,
    profiles: list[dict[str, Any]],
) -> str | None:
    local_state_path = user_data_dir / "Local State"
    last_used = ""
    if local_state_path.exists():
        try:
            payload = json.loads(local_state_path.read_text(encoding="utf-8"))
            last_used = str(payload.get("profile", {}).get("last_used") or "").strip()
        except Exception:
            last_used = ""

    if last_used:
        for profile in profiles:
            if profile["directory_name"] == last_used:
                return str(profile["id"])

    return str(profiles[0]["id"]) if profiles else None


def _resolve_user_data_dir(
    *,
    browser: str | None,
    user_data_dir: str | None,
) -> tuple[str, Path]:
    normalized_custom_dir = str(user_data_dir or "").strip()
    if normalized_custom_dir:
        custom_path = Path(normalized_custom_dir)
        if not custom_path.exists():
            raise ValidationError(message="提供的浏览器用户数据目录不存在。")
        return (browser or "custom").strip().lower() or "custom", custom_path

    normalized_browser = (browser or "").strip().lower()
    if normalized_browser:
        config = CHROMIUM_SOURCES.get(normalized_browser)
        if config is None:
            raise ValidationError(message="暂不支持所选浏览器，请选择 Edge 或 Chrome。")
        user_data_path = Path(config["user_data_dir"])
        if not user_data_path.exists():
            raise ValidationError(message="本机未检测到所选浏览器的用户数据目录。")
        return normalized_browser, user_data_path

    sources = discover_bilibili_browser_sources()
    if not sources:
        raise ValidationError(message="本机未检测到可用的 Chromium 浏览器配置。")
    first_source = sources[0]
    return str(first_source["browser"]), Path(str(first_source["user_data_dir"]))


def _resolve_profile_directory(
    *,
    user_data_dir: Path,
    browser: str,
    profile_directory: str | None,
) -> Path:
    normalized_profile = str(profile_directory or "").strip()
    if normalized_profile:
        profile_dir = user_data_dir / normalized_profile
        if not profile_dir.exists():
            raise ValidationError(message="所选浏览器配置目录不存在。")
        return profile_dir

    default_profile_id = _detect_default_profile_id(
        user_data_dir,
        browser,
        _discover_profiles(user_data_dir, browser),
    )
    if default_profile_id:
        inferred_profile = default_profile_id.split(":", 1)[-1]
        inferred_path = user_data_dir / inferred_profile
        if inferred_path.exists():
            return inferred_path

    fallback = user_data_dir / "Default"
    if fallback.exists():
        return fallback

    raise ValidationError(message="未找到可读取的浏览器配置目录。")


def _resolve_cookie_database_path(profile_dir: Path) -> Path | None:
    candidates = [
        profile_dir / "Network" / "Cookies",
        profile_dir / "Cookies",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_bilibili_cookies_from_database(
    *,
    cookies_db_path: Path,
    user_data_dir: Path,
) -> dict[str, str]:
    master_key = _load_chromium_master_key(user_data_dir)
    temp_dir = Path(tempfile.mkdtemp(prefix="spiderbilibili-cookies-"))
    temp_db_path = temp_dir / "Cookies"
    temp_wal_path = temp_dir / "Cookies-wal"
    temp_shm_path = temp_dir / "Cookies-shm"
    try:
        try:
            shutil.copy2(cookies_db_path, temp_db_path)
        except PermissionError as exc:
            raise BrowserCookieLockedError("cookie database is locked") from exc

        if cookies_db_path.with_name("Cookies-wal").exists():
            shutil.copy2(cookies_db_path.with_name("Cookies-wal"), temp_wal_path)
        if cookies_db_path.with_name("Cookies-shm").exists():
            shutil.copy2(cookies_db_path.with_name("Cookies-shm"), temp_shm_path)

        connection = sqlite3.connect(temp_db_path)
        try:
            rows = connection.execute(
                """
                SELECT name, value, encrypted_value
                FROM cookies
                WHERE host_key LIKE '%bilibili.com%'
                  AND name IN (?, ?, ?, ?, ?)
                ORDER BY host_key DESC
                """,
                ("SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"),
            ).fetchall()
        finally:
            connection.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    cookie_map: dict[str, str] = {}
    for name, value, encrypted_value in rows:
        cookie_name = str(name or "").strip()
        if not cookie_name or cookie_name in cookie_map:
            continue
        resolved_value = str(value or "").strip()
        if not resolved_value and encrypted_value:
            resolved_value = _decrypt_chromium_cookie_value(
                encrypted_value=bytes(encrypted_value),
                master_key=master_key,
            )
        if resolved_value:
            cookie_map[cookie_name] = resolved_value
    return cookie_map


def _load_chromium_master_key(user_data_dir: Path) -> bytes:
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        raise ValidationError(message="未找到浏览器 Local State 文件，无法解密 Cookie。")

    try:
        payload = json.loads(local_state_path.read_text(encoding="utf-8"))
        encrypted_key_b64 = str(payload["os_crypt"]["encrypted_key"])
    except Exception as exc:
        raise ValidationError(message="读取浏览器主密钥失败。") from exc

    encrypted_key = base64.b64decode(encrypted_key_b64)
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    return _crypt_unprotect_data(encrypted_key)


def _decrypt_chromium_cookie_value(*, encrypted_value: bytes, master_key: bytes) -> str:
    if encrypted_value[:3] in {b"v10", b"v11"}:
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:]
        plain_text = AESGCM(master_key).decrypt(nonce, ciphertext, None)
        return plain_text.decode("utf-8", errors="replace").strip()

    plain_text = _crypt_unprotect_data(encrypted_value)
    return plain_text.decode("utf-8", errors="replace").strip()


def _crypt_unprotect_data(encrypted_data: bytes) -> bytes:
    if os.name != "nt":
        raise ValidationError(message="当前仅支持在 Windows 环境中解密浏览器 Cookie。")

    if not encrypted_data:
        return b""

    buffer = ctypes.create_string_buffer(encrypted_data, len(encrypted_data))
    in_blob = _DataBlob(
        len(encrypted_data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)),
    )
    out_blob = _DataBlob()

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    result = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not result:
        raise ValidationError(message="系统无法解密当前浏览器配置中的 Cookie。")

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _capture_bilibili_cookie_via_playwright(*, browser: str) -> str:
    settings = get_settings()
    browser_config = CHROMIUM_SOURCES.get(browser, {})
    channel = browser_config.get("channel")
    login_timeout_seconds = 180

    with sync_playwright() as playwright:
        launch_fn = playwright.chromium.launch
        try:
            launched_browser = launch_fn(
                headless=False,
                channel=channel,
                args=["--disable-features=msEdgeSidebarV2"],
            )
        except PlaywrightError:
            launched_browser = launch_fn(
                headless=False,
                args=["--disable-features=msEdgeSidebarV2"],
            )

        context = launched_browser.new_context(
            user_agent=settings.bilibili_user_agent,
            locale="zh-CN",
        )
        page = context.new_page()
        try:
            page.goto("https://www.bilibili.com/", wait_until="domcontentloaded")
            deadline = time.time() + login_timeout_seconds
            while time.time() < deadline:
                cookies = context.cookies("https://www.bilibili.com")
                cookie_map = {
                    str(item.get("name") or ""): str(item.get("value") or "")
                    for item in cookies
                    if item.get("name") in TARGET_COOKIE_NAMES and item.get("value")
                }
                cookie = _compose_cookie_string(cookie_map)
                if "SESSDATA" in cookie_map and cookie:
                    return cookie
                page.wait_for_timeout(2000)
        finally:
            context.close()
            launched_browser.close()

    raise ValidationError(
        message="本机浏览器 Cookie 正被占用，系统已尝试打开登录窗口，但你没有在限定时间内完成 B站登录。请重试。"
    )


def _compose_cookie_string(cookie_map: dict[str, str]) -> str:
    ordered_names = ["SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"]
    return "; ".join(
        f"{name}={cookie_map[name]}"
        for name in ordered_names
        if str(cookie_map.get(name) or "").strip()
    )


def _browser_label(browser: str) -> str:
    config = CHROMIUM_SOURCES.get(browser)
    return str(config["label"]) if config is not None else browser
