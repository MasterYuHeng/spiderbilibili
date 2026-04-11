from types import SimpleNamespace

from app.services.alerting import AlertEvent, send_alert


class FakeRedis:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.deleted_keys: list[str] = []
        self.set_calls: list[tuple[str, str, bool, int]] = []

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        self.set_calls.append((key, value, nx, ex))
        return not self.duplicate

    def delete(self, key: str) -> int:
        self.deleted_keys.append(key)
        return 1


def build_settings() -> SimpleNamespace:
    return SimpleNamespace(
        alerting_enabled=True,
        alerting_wechat_webhook="https://wechat.example",
        alerting_dingtalk_webhook="https://dingtalk.example",
        alerting_email_enabled=False,
        alert_email_recipients=[],
        alerting_dedupe_window_seconds=900,
        monitoring_redis_prefix="spiderbilibili:monitoring",
    )


def test_send_alert_continues_when_one_channel_fails(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr("app.services.alerting.get_settings", build_settings)
    monkeypatch.setattr(
        "app.services.alerting.get_monitoring_redis_client",
        lambda: fake_redis,
    )
    monkeypatch.setattr(
        "app.services.alerting._send_wechat_alert",
        lambda event: (_ for _ in ()).throw(RuntimeError("wechat down")),
    )

    delivered_events: list[str] = []

    def record_dingtalk(event: AlertEvent) -> None:
        delivered_events.append(event.event_type)

    monkeypatch.setattr(
        "app.services.alerting._send_dingtalk_alert",
        record_dingtalk,
    )

    delivered_via = send_alert(
        AlertEvent(
            event_type="task_terminal_status",
            severity="warning",
            title="task warning",
            message="worker missing",
        )
    )

    assert delivered_via == ["dingtalk"]
    assert delivered_events == ["task_terminal_status"]
    assert fake_redis.deleted_keys == []


def test_send_alert_releases_dedupe_claim_when_all_channels_fail(
    monkeypatch,
) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr("app.services.alerting.get_settings", build_settings)
    monkeypatch.setattr(
        "app.services.alerting.get_monitoring_redis_client",
        lambda: fake_redis,
    )
    monkeypatch.setattr(
        "app.services.alerting._send_wechat_alert",
        lambda event: (_ for _ in ()).throw(RuntimeError("wechat down")),
    )
    monkeypatch.setattr(
        "app.services.alerting._send_dingtalk_alert",
        lambda event: (_ for _ in ()).throw(RuntimeError("dingtalk down")),
    )

    delivered_via = send_alert(
        AlertEvent(
            event_type="task_terminal_status",
            severity="critical",
            title="task failed",
            message="pipeline failed",
        )
    )

    assert delivered_via == []
    assert fake_redis.deleted_keys == [
        "spiderbilibili:monitoring:alerts:task_terminal_status"
    ]
