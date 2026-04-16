from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import system as system_routes
from app.db.base import Base
from app.db.bootstrap import bootstrap_system_configs
from app.db.session import get_db_session
from app.main import app


def build_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    with factory() as session:
        bootstrap_system_configs(session, commit=True)
    return factory


def build_db_override(session_factory: sessionmaker[Session]):
    def _override() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    return _override


def test_system_settings_endpoints_can_read_and_update_keys() -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    original_discover = system_routes.discover_bilibili_browser_sources
    original_fetch_profile = system_routes.fetch_bilibili_account_profile
    try:
        system_routes.discover_bilibili_browser_sources = lambda: [
            {
                "browser": "edge",
                "label": "Microsoft Edge",
                "user_data_dir": (
                    r"C:\Users\tester\AppData\Local\Microsoft\Edge\User Data"
                ),
                "default_profile_id": "edge:Default",
                "profiles": [
                    {
                        "id": "edge:Default",
                        "label": "默认配置",
                        "directory_name": "Default",
                        "cookie_db_exists": True,
                    }
                ],
            }
        ]
        system_routes.fetch_bilibili_account_profile = lambda cookie: (
            {
                "is_login": True,
                "mid": "2233",
                "username": "测试账号",
                "level": 6,
                "avatar_url": None,
            },
            None,
        )

        client = TestClient(app)

        initial_response = client.get("/api/ai-settings")
        assert initial_response.status_code == 200
        initial_payload = initial_response.json()["data"]
        assert initial_payload["deepseek"]["provider"] == "deepseek"
        assert initial_payload["bilibili"]["provider"] == "bilibili"
        assert initial_payload["bilibili"]["browser_sources"][0]["browser"] == "edge"

        update_ai_response = client.put(
            "/api/ai-settings/deepseek",
            json={"api_key": "deepseek-runtime-key"},
        )
        assert update_ai_response.status_code == 200
        updated_ai_payload = update_ai_response.json()["data"]
        assert updated_ai_payload["api_key"] == "deepseek-runtime-key"
        assert updated_ai_payload["key_source"] == "runtime"

        update_bilibili_response = client.put(
            "/api/bilibili-settings",
            json={
                "cookie": "SESSDATA=runtime-sess; bili_jct=runtime-jct; DedeUserID=2233"
            },
        )
        assert update_bilibili_response.status_code == 200
        updated_bilibili_payload = update_bilibili_response.json()["data"]
        assert updated_bilibili_payload["cookie_configured"] is True
        assert updated_bilibili_payload["key_source"] == "runtime"
        assert updated_bilibili_payload["sessdata"] == "runtime-sess"
        assert updated_bilibili_payload["account_profile"]["mid"] == "2233"

        followup_response = client.get("/api/ai-settings")
        assert followup_response.status_code == 200
        followup_payload = followup_response.json()["data"]
        assert followup_payload["deepseek"]["api_key"] == "deepseek-runtime-key"
        assert followup_payload["bilibili"]["dede_user_id"] == "2233"
    finally:
        system_routes.discover_bilibili_browser_sources = original_discover
        system_routes.fetch_bilibili_account_profile = original_fetch_profile
        app.dependency_overrides.clear()


def test_system_bilibili_import_endpoint_returns_imported_cookie() -> None:
    session_factory = build_session_factory()
    app.dependency_overrides[get_db_session] = build_db_override(session_factory)

    original_discover = system_routes.discover_bilibili_browser_sources
    original_import = system_routes.import_bilibili_auth_from_browser
    try:
        system_routes.discover_bilibili_browser_sources = lambda: []
        system_routes.import_bilibili_auth_from_browser = lambda **_: {
            "cookie": "SESSDATA=imported-sess; bili_jct=imported-jct; DedeUserID=4455",
            "account_profile": {
                "is_login": True,
                "mid": "4455",
                "username": "导入账号",
                "level": 6,
                "avatar_url": None,
            },
            "validation_message": None,
            "import_source": {
                "browser": "edge",
                "profile_directory": "Default",
                "user_data_dir": (
                    r"C:\Users\tester\AppData\Local\Microsoft\Edge\User Data"
                ),
                "label": "Microsoft Edge / Default",
            },
        }

        client = TestClient(app)
        response = client.post(
            "/api/bilibili-settings/import-browser",
            json={"browser": "edge", "profile_directory": "Default"},
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["cookie_configured"] is True
        assert payload["sessdata"] == "imported-sess"
        assert payload["account_profile"]["mid"] == "4455"
        assert payload["import_summary"] == "Microsoft Edge / Default"
    finally:
        system_routes.discover_bilibili_browser_sources = original_discover
        system_routes.import_bilibili_auth_from_browser = original_import
        app.dependency_overrides.clear()
