from __future__ import annotations

import json
import logging
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.core.config import get_settings
from app.services.monitoring import get_monitoring_redis_client

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AlertEvent:
    event_type: str
    severity: str
    title: str
    message: str
    details: dict[str, object] | None = None
    dedupe_key: str | None = None


def send_alert(event: AlertEvent) -> list[str]:
    settings = get_settings()
    if not settings.alerting_enabled:
        return []

    senders: list[tuple[str, Callable[[AlertEvent], None]]] = []
    if settings.alerting_wechat_webhook:
        senders.append(("wechat", _send_wechat_alert))
    if settings.alerting_dingtalk_webhook:
        senders.append(("dingtalk", _send_dingtalk_alert))
    if settings.alerting_email_enabled and settings.alert_email_recipients:
        senders.append(("email", _send_email_alert))

    if not senders:
        return []

    dedupe_cache_key = _build_dedupe_cache_key(event)
    if _claim_duplicate_alert(dedupe_cache_key):
        return []

    delivered_via: list[str] = []
    for channel_name, sender in senders:
        try:
            sender(event)
        except Exception:
            logger.exception(
                "Failed to deliver alert via %s for event %s.",
                channel_name,
                event.event_type,
            )
            continue
        delivered_via.append(channel_name)

    if not delivered_via:
        _clear_duplicate_alert_claim(dedupe_cache_key)
    return delivered_via


def _build_dedupe_cache_key(event: AlertEvent) -> str:
    settings = get_settings()
    dedupe_key = event.dedupe_key or event.event_type
    return f"{settings.monitoring_redis_prefix}:alerts:{dedupe_key}"


def _claim_duplicate_alert(dedupe_cache_key: str) -> bool:
    settings = get_settings()
    try:
        client = get_monitoring_redis_client()
        if client.set(
            dedupe_cache_key,
            "1",
            nx=True,
            ex=settings.alerting_dedupe_window_seconds,
        ):
            return False
        return True
    except Exception:
        return False


def _clear_duplicate_alert_claim(dedupe_cache_key: str) -> None:
    try:
        client = get_monitoring_redis_client()
        client.delete(dedupe_cache_key)
    except Exception:
        return


def _send_wechat_alert(event: AlertEvent) -> None:
    settings = get_settings()
    content = _build_markdown_message(event)
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }
    with httpx.Client(timeout=settings.alerting_request_timeout_seconds) as client:
        client.post(settings.alerting_wechat_webhook, json=payload).raise_for_status()


def _send_dingtalk_alert(event: AlertEvent) -> None:
    settings = get_settings()
    content = _build_markdown_message(event)
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": event.title, "text": content},
    }
    with httpx.Client(timeout=settings.alerting_request_timeout_seconds) as client:
        client.post(settings.alerting_dingtalk_webhook, json=payload).raise_for_status()


def _send_email_alert(event: AlertEvent) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["Subject"] = f"[{event.severity.upper()}] {event.title}"
    message["From"] = settings.alerting_email_from or settings.alerting_email_username
    message["To"] = ", ".join(settings.alert_email_recipients)
    message.set_content(_build_text_message(event))

    with smtplib.SMTP(
        settings.alerting_email_smtp_host,
        settings.alerting_email_smtp_port,
        timeout=settings.alerting_request_timeout_seconds,
    ) as smtp:
        if settings.alerting_email_use_tls:
            smtp.starttls()
        if settings.alerting_email_username:
            smtp.login(
                settings.alerting_email_username,
                settings.alerting_email_password,
            )
        smtp.send_message(message)


def _build_markdown_message(event: AlertEvent) -> str:
    lines = [
        f"## {event.title}",
        "",
        f"- Severity: `{event.severity}`",
        f"- Event: `{event.event_type}`",
        "",
        event.message,
    ]
    if event.details:
        lines.extend(
            [
                "",
                "```json",
                json.dumps(event.details, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    return "\n".join(lines)


def _build_text_message(event: AlertEvent) -> str:
    lines = [
        event.title,
        "",
        f"Severity: {event.severity}",
        f"Event: {event.event_type}",
        "",
        event.message,
    ]
    if event.details:
        lines.extend(
            [
                "",
                json.dumps(event.details, ensure_ascii=False, indent=2),
            ]
        )
    return "\n".join(lines)
