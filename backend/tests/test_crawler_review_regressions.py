import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.crawler.browser_client import BilibiliBrowserClient
from app.crawler.client import BilibiliHttpClient
from app.crawler.exceptions import (
    BilibiliAntiCrawlerError,
    BilibiliParseError,
    BilibiliRequestError,
)
from app.crawler.models import SearchPageData, SearchVideoCandidate
from app.crawler.raw_archive import RawArchiveStore
from app.crawler.search_spider import BilibiliSearchSpider
from app.db.base import Base
from app.models.enums import TaskStatus
from app.models.task import CrawlTask
from app.services.crawl_pipeline_service import CrawlPipelineService
from app.testsupport import build_search_candidate


def build_settings(**overrides):
    defaults = {
        "bilibili_user_agent": "test-agent",
        "http_timeout_seconds": 5.0,
        "http_max_retries": 0,
        "https_proxy": "http://secure-proxy.example:8443",
        "http_proxy": "http://proxy.example:8080",
        "crawler_min_sleep": 0.0,
        "crawler_max_sleep": 0.0,
        "crawler_rate_limit_per_minute": 0,
        "playwright_headless": True,
        "playwright_timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory()


def test_search_keyword_keeps_fetching_until_unique_limit_is_reached() -> None:
    class FakeSearchSpider(BilibiliSearchSpider):
        def __init__(self):
            self.pages_called: list[int] = []
            self.pages = {
                1: SearchPageData(
                    keyword="AI",
                    page=1,
                    page_size=2,
                    total_results=6,
                    total_pages=3,
                    candidates=[
                        build_search_candidate("BV1A", "AI", search_rank=1),
                        build_search_candidate("BV1B", "AI", search_rank=2),
                    ],
                    raw_payload={},
                ),
                2: SearchPageData(
                    keyword="AI",
                    page=2,
                    page_size=2,
                    total_results=6,
                    total_pages=3,
                    candidates=[
                        build_search_candidate("BV1A", "AI", search_rank=3),
                        build_search_candidate("BV1C", "AI", search_rank=4),
                    ],
                    raw_payload={},
                ),
                3: SearchPageData(
                    keyword="AI",
                    page=3,
                    page_size=2,
                    total_results=6,
                    total_pages=3,
                    candidates=[
                        build_search_candidate("BV1D", "AI", search_rank=5),
                    ],
                    raw_payload={},
                ),
            }

        def search_page(self, keyword: str, *, page: int) -> SearchPageData:
            self.pages_called.append(page)
            return self.pages[page]

    spider = FakeSearchSpider()

    candidates = spider.search_keyword("AI", max_pages=3, limit=4)

    assert spider.pages_called == [1, 2, 3]
    assert {item.bvid for item in candidates} >= {"BV1A", "BV1B", "BV1C", "BV1D"}


def test_http_client_respects_proxy_toggle() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 0})
    )
    settings = build_settings()

    direct_client = BilibiliHttpClient(
        settings=settings,
        use_proxy=False,
        transport=transport,
    )
    proxied_client = BilibiliHttpClient(
        settings=settings,
        use_proxy=True,
        transport=transport,
    )

    try:
        assert direct_client.proxy_url is None
        assert proxied_client.proxy_url == "http://secure-proxy.example:8443"
    finally:
        direct_client.close()
        proxied_client.close()


def test_search_spider_uses_public_anonymous_search_requests() -> None:
    observed: dict[str, object] = {}

    class RecordingHttpClient:
        search_origin = "https://search.bilibili.com"

        def get_api_json(self, path, *, params, referer, include_auth=True, **kwargs):
            observed["path"] = path
            observed["params"] = dict(params)
            observed["referer"] = referer
            observed["include_auth"] = include_auth
            return {
                "code": 0,
                "data": {
                    "result": [],
                    "pagesize": 20,
                    "numResults": 0,
                    "numPages": 0,
                },
            }

    spider = BilibiliSearchSpider(RecordingHttpClient())

    page_data = spider.search_page("AI", page=1)

    assert page_data.total_results == 0
    assert observed["path"] == "/x/web-interface/search/type"
    assert observed["referer"] == "https://search.bilibili.com"
    assert observed["include_auth"] is False


def test_http_client_includes_bilibili_login_cookie_header() -> None:
    observed_cookie_header: dict[str, str | None] = {"value": None}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_cookie_header["value"] = request.headers.get("Cookie")
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = BilibiliHttpClient(
        settings=build_settings(
            bilibili_cookie="SESSDATA=raw-session; bili_jct=raw-jct",
            bilibili_dedeuserid="123456",
            http_proxy="",
            https_proxy="",
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        client.get_api_json("/x/test")
    finally:
        client.close()

    assert observed_cookie_header["value"] is not None
    assert "SESSDATA=raw-session" in observed_cookie_header["value"]
    assert "bili_jct=raw-jct" in observed_cookie_header["value"]
    assert "DedeUserID=123456" in observed_cookie_header["value"]


def test_http_client_can_send_public_request_without_bilibili_login_cookie() -> None:
    observed_cookie_header: dict[str, str | None] = {"value": None}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_cookie_header["value"] = request.headers.get("Cookie")
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = BilibiliHttpClient(
        settings=build_settings(
            bilibili_cookie="SESSDATA=raw-session; bili_jct=raw-jct",
            bilibili_dedeuserid="123456",
            http_proxy="",
            https_proxy="",
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        client.get_api_json("/x/test", include_auth=False)
    finally:
        client.close()

    assert observed_cookie_header["value"] is None


def test_http_client_uses_exponential_backoff() -> None:
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = BilibiliHttpClient(
        settings=build_settings(
            http_max_retries=1,
            http_proxy="",
            https_proxy="",
            crawler_backoff_base_seconds=2.0,
            crawler_backoff_max_seconds=10.0,
            crawler_backoff_jitter_seconds=0.0,
        ),
        transport=httpx.MockTransport(handler),
        sleep_func=sleep_calls.append,
    )

    try:
        payload = client.get_api_json("/x/test")
    finally:
        client.close()

    assert payload["code"] == 0
    assert sleep_calls == [2.0]


def test_http_client_opens_circuit_breaker_after_repeated_anti_crawler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        request_calls["count"] += 1
        return httpx.Response(429, json={"code": 429})

    monotonic_time = {"value": 10.0}
    monkeypatch.setattr(
        "app.crawler.client.time.monotonic",
        lambda: monotonic_time["value"],
    )

    client = BilibiliHttpClient(
        settings=build_settings(
            http_max_retries=0,
            http_proxy="",
            https_proxy="",
            crawler_circuit_breaker_failure_threshold=1,
            crawler_circuit_breaker_recovery_seconds=60.0,
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        with pytest.raises(BilibiliAntiCrawlerError):
            client.get_api_json("/x/test")

        with pytest.raises(BilibiliAntiCrawlerError, match="circuit breaker is open"):
            client.get_api_json("/x/test")
    finally:
        client.close()

    assert request_calls["count"] == 1


def test_http_client_enforces_rate_limit_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = {"value": 0.0}
    sleep_calls: list[float] = []

    def fake_monotonic() -> float:
        return current_time["value"]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        current_time["value"] += seconds

    monkeypatch.setattr("app.crawler.client.time.monotonic", fake_monotonic)
    client = BilibiliHttpClient(
        settings=build_settings(
            crawler_rate_limit_per_minute=2,
            http_proxy="",
            https_proxy="",
        ),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": 0, "data": {}})
        ),
        sleep_func=fake_sleep,
    )

    try:
        client.get_api_json("/x/test")
        client.get_api_json("/x/test")
        client.get_api_json("/x/test")
    finally:
        client.close()

    assert sleep_calls == [30.0, 30.0]


def test_http_client_can_skip_throttle_for_ephemeral_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = {"value": 0.0}
    sleep_calls: list[float] = []

    def fake_monotonic() -> float:
        return current_time["value"]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        current_time["value"] += seconds

    monkeypatch.setattr("app.crawler.client.time.monotonic", fake_monotonic)
    client = BilibiliHttpClient(
        settings=build_settings(
            crawler_rate_limit_per_minute=1,
            crawler_min_sleep=2.0,
            crawler_max_sleep=2.0,
            http_proxy="",
            https_proxy="",
        ),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": 0, "data": {}})
        ),
        sleep_func=fake_sleep,
    )

    try:
        client.get_api_json("/x/test")
        client.get_text("/x/test", skip_throttle=True)
    finally:
        client.close()

    assert sleep_calls == []


def test_http_client_preserves_presigned_url_query_string() -> None:
    client = BilibiliHttpClient(
        settings=build_settings(http_proxy="", https_proxy=""),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": 0, "data": {}})
        ),
    )
    captured: dict[str, object] = {}

    def fake_get(url: str, *, params=None, headers=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return httpx.Response(200, json={"code": 0, "data": {}})

    client.client.get = fake_get  # type: ignore[method-assign]

    try:
        client.get_text(
            "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/demo?auth_key=abc123",
            referer="https://www.bilibili.com/video/BV1demo",
            skip_throttle=True,
        )
    finally:
        client.close()

    assert captured["url"] == (
        "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/demo?auth_key=abc123"
    )
    assert captured["params"] is None


def test_browser_client_wraps_status_and_parse_failures() -> None:
    class FakePage:
        def __init__(self, payload):
            self.payload = payload

        def goto(self, referer: str, wait_until: str) -> None:
            return None

        def evaluate(self, script: str, url: str):
            return self.payload

        def close(self) -> None:
            return None

    class FakeContext:
        def __init__(self, payload):
            self.payload = payload

        def new_page(self) -> FakePage:
            return FakePage(self.payload)

    settings = build_settings()

    failing_client = BilibiliBrowserClient(settings=settings, use_proxy=True)
    failing_client._auth_context = FakeContext({"status": 500, "text": "oops"})
    assert (
        failing_client._build_launch_kwargs()["proxy"]["server"]
        == "http://secure-proxy.example:8443"
    )
    with pytest.raises(BilibiliRequestError):
        failing_client.fetch_api_json("https://api.bilibili.com/x/test")

    parsing_client = BilibiliBrowserClient(settings=settings, use_proxy=False)
    parsing_client._auth_context = FakeContext({"status": 200, "text": "not-json"})
    with pytest.raises(BilibiliParseError):
        parsing_client.fetch_api_json("https://api.bilibili.com/x/test")


def test_browser_client_applies_bilibili_login_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeContext:
        def add_cookies(self, cookies) -> None:
            captured["cookies"] = cookies

        def set_default_timeout(self, timeout: float) -> None:
            captured["timeout"] = timeout

    class FakeBrowser:
        def new_context(self, **kwargs):
            captured["context_kwargs"] = kwargs
            return FakeContext()

    class FakeChromium:
        def launch(self, **kwargs):
            captured["launch_kwargs"] = kwargs
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

        def stop(self) -> None:
            return None

    monkeypatch.setattr(
        "app.crawler.browser_client.sync_playwright",
        lambda: SimpleNamespace(start=lambda: FakePlaywright()),
    )

    client = BilibiliBrowserClient(
        settings=build_settings(
            bilibili_cookie="SESSDATA=raw-session; bili_jct=raw-jct",
            bilibili_buvid3="buvid3-value",
        ),
        use_proxy=False,
    )

    context = client._get_context()

    assert context is not None
    assert captured["timeout"] == 5000.0
    cookies = captured["cookies"]
    assert isinstance(cookies, list)
    assert any(
        item["name"] == "SESSDATA"
        and item["value"] == "raw-session"
        and item["domain"] == ".bilibili.com"
        for item in cookies
    )
    assert any(
        item["name"] == "bili_jct" and item["value"] == "raw-jct" for item in cookies
    )
    assert any(
        item["name"] == "buvid3" and item["value"] == "buvid3-value" for item in cookies
    )


def test_browser_client_can_build_anonymous_context_without_login_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {"cookie_calls": 0}

    class FakeContext:
        def add_cookies(self, cookies) -> None:
            captured["cookie_calls"] = int(captured["cookie_calls"]) + 1
            captured["cookies"] = cookies

        def set_default_timeout(self, timeout: float) -> None:
            captured.setdefault("timeouts", []).append(timeout)

    class FakeBrowser:
        def new_context(self, **kwargs):
            captured.setdefault("contexts", []).append(kwargs)
            return FakeContext()

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

        def stop(self) -> None:
            return None

    monkeypatch.setattr(
        "app.crawler.browser_client.sync_playwright",
        lambda: SimpleNamespace(start=lambda: FakePlaywright()),
    )

    client = BilibiliBrowserClient(
        settings=build_settings(
            bilibili_cookie="SESSDATA=raw-session; bili_jct=raw-jct",
        ),
        use_proxy=False,
    )

    anonymous_context = client._get_context(include_auth_cookies=False)

    assert anonymous_context is not None
    assert captured["cookie_calls"] == 0
    assert captured["contexts"] == [
        {
            "user_agent": build_settings().bilibili_user_agent,
            "locale": "zh-CN",
        }
    ]


def test_crawl_pipeline_service_passes_task_proxy_flag_to_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, bool] = {}

    class RecordingHttpClient:
        def __init__(
            self,
            *,
            settings,
            min_sleep_seconds,
            max_sleep_seconds,
            use_proxy,
        ):
            calls["http_use_proxy"] = use_proxy

        def close(self) -> None:
            return None

    class RecordingBrowserClient:
        def __init__(self, *, settings, use_proxy):
            calls["browser_use_proxy"] = use_proxy

        def close(self) -> None:
            return None

    class StubSearchSpider:
        def __init__(self, http_client, *, browser_client, raw_archive):
            return None

        def search_keyword(self, keyword: str, *, max_pages: int, limit: int):
            return []

    class StubDetailSpider:
        def __init__(self, http_client, *, browser_client, raw_archive):
            return None

    class StubSubtitleSpider:
        def __init__(self, http_client, *, browser_client, raw_archive):
            return None

    monkeypatch.setattr(
        "app.services.crawl_pipeline_service.BilibiliHttpClient",
        RecordingHttpClient,
    )
    monkeypatch.setattr(
        "app.services.crawl_pipeline_service.BilibiliBrowserClient",
        RecordingBrowserClient,
    )
    monkeypatch.setattr(
        "app.services.crawl_pipeline_service.BilibiliSearchSpider",
        StubSearchSpider,
    )
    monkeypatch.setattr(
        "app.services.crawl_pipeline_service.BilibiliDetailSpider",
        StubDetailSpider,
    )
    monkeypatch.setattr(
        "app.services.crawl_pipeline_service.BilibiliSubtitleSpider",
        StubSubtitleSpider,
    )

    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=2,
            max_pages=1,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.02"),
            enable_proxy=True,
            source_ip_strategy="proxy_pool",
        )
        session.add(task)
        session.commit()

        service = CrawlPipelineService(session)
        result = service.run_task(task)
        service.close()

        assert result.candidate_count == 0
        assert calls["http_use_proxy"] is True
        assert calls["browser_use_proxy"] is True


def test_raw_archive_store_skips_directory_creation_when_disabled() -> None:
    temp_dir = Path(tempfile.mkdtemp())
    settings = build_settings(
        crawler_save_raw_payloads=False,
        crawler_raw_data_dir=str(temp_dir),
    )

    store = RawArchiveStore("task-raw-disabled", settings=settings)

    assert store.root_dir is None
    assert store.save_json("search", "page_1", {"code": 0}) is None
    assert list(temp_dir.iterdir()) == []


def test_crawl_pipeline_service_uses_video_level_concurrency() -> None:
    max_inflight = {"value": 0}
    state = {"current": 0}
    lock = threading.Lock()

    class StubSearchSpider:
        def search_keyword(self, keyword: str, *, max_pages: int, limit: int):
            return [
                build_search_candidate("BV1A", "AI", search_rank=1),
                build_search_candidate("BV1B", "AI", search_rank=2),
                build_search_candidate("BV1C", "AI", search_rank=3),
            ]

    http_client = SimpleNamespace(
        settings=build_settings(crawler_concurrency=3),
        close=lambda: None,
    )
    browser_client = SimpleNamespace(close=lambda: None)

    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=3,
            max_pages=1,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()

        service = CrawlPipelineService(
            session,
            http_client=http_client,
            browser_client=browser_client,
            search_spider=StubSearchSpider(),
            detail_spider=SimpleNamespace(),
            subtitle_spider=SimpleNamespace(),
            raw_archive=SimpleNamespace(root_dir=None),
        )
        service.storage_service.reset_task_outputs = lambda task: None
        service.storage_service.persist_scored_video = lambda task, scored_video: None

        def fake_crawl_candidate_http_only(
            task,
            candidate: SearchVideoCandidate,
            scoring_weights,
        ):
            with lock:
                state["current"] += 1
                max_inflight["value"] = max(max_inflight["value"], state["current"])
            try:
                time.sleep(0.02)
                detail = SimpleNamespace(
                    bvid=candidate.bvid,
                    title=f"{candidate.bvid} 标题",
                    author_name="UP主",
                    url=f"https://www.bilibili.com/video/{candidate.bvid}",
                    published_at=None,
                    duration_seconds=120,
                    description="描述",
                    tags=["AI"],
                    metrics=SimpleNamespace(
                        view_count=10,
                        like_count=2,
                        coin_count=1,
                        favorite_count=1,
                        share_count=0,
                        reply_count=0,
                        danmaku_count=0,
                    ),
                )
                subtitle = SimpleNamespace(
                    language_code="zh-CN",
                    language_name="中文",
                    segments=[SimpleNamespace(content="字幕")],
                    combined_text="字幕",
                )
                return SimpleNamespace(
                    bundle=SimpleNamespace(
                        candidate=candidate,
                        detail=detail,
                        subtitle=subtitle,
                    ),
                    keyword_hit_title=True,
                    keyword_hit_description=True,
                    keyword_hit_tags=True,
                    relevance_score=0.8,
                    heat_score=0.7,
                    composite_score=0.75,
                )
            finally:
                with lock:
                    state["current"] -= 1

        service._crawl_candidate_http_only = fake_crawl_candidate_http_only

        result = service.run_task(task)
        service.close()

    assert result.video_concurrency == 3
    assert max_inflight["value"] >= 2


def test_crawl_pipeline_service_retries_browser_fallback_sequentially() -> None:
    threaded_calls: list[str] = []
    fallback_threads: list[str] = []

    class StubSearchSpider:
        def search_keyword(self, keyword: str, *, max_pages: int, limit: int):
            return [
                build_search_candidate("BV1A", "AI", search_rank=1),
                build_search_candidate("BV1B", "AI", search_rank=2),
            ]

    http_client = SimpleNamespace(
        settings=build_settings(crawler_concurrency=2),
        close=lambda: None,
    )
    browser_client = SimpleNamespace(close=lambda: None)

    with build_session() as session:
        task = CrawlTask(
            keyword="AI",
            status=TaskStatus.RUNNING,
            requested_video_limit=2,
            max_pages=1,
            min_sleep_seconds=Decimal("0.01"),
            max_sleep_seconds=Decimal("0.01"),
            enable_proxy=False,
            source_ip_strategy="local_sleep",
        )
        session.add(task)
        session.commit()

        service = CrawlPipelineService(
            session,
            http_client=http_client,
            browser_client=browser_client,
            search_spider=StubSearchSpider(),
            detail_spider=SimpleNamespace(),
            subtitle_spider=SimpleNamespace(),
            raw_archive=SimpleNamespace(root_dir=None),
        )
        service.storage_service.reset_task_outputs = lambda task: None
        service.storage_service.persist_scored_video = lambda task, scored_video: None

        def fake_http_only(task, candidate: SearchVideoCandidate, scoring_weights):
            threaded_calls.append(threading.current_thread().name)
            raise BilibiliRequestError("http failed")

        def fake_browser_fallback(
            task,
            candidate: SearchVideoCandidate,
            scoring_weights,
        ):
            fallback_threads.append(threading.current_thread().name)
            detail = SimpleNamespace(
                bvid=candidate.bvid,
                title=f"{candidate.bvid} 标题",
                author_name="UP主",
                url=f"https://www.bilibili.com/video/{candidate.bvid}",
                published_at=None,
                duration_seconds=120,
                description="描述",
                tags=["AI"],
                metrics=SimpleNamespace(
                    view_count=10,
                    like_count=2,
                    coin_count=1,
                    favorite_count=1,
                    share_count=0,
                    reply_count=0,
                    danmaku_count=0,
                ),
            )
            return SimpleNamespace(
                bundle=SimpleNamespace(
                    candidate=candidate,
                    detail=detail,
                    subtitle=None,
                ),
                keyword_hit_title=True,
                keyword_hit_description=True,
                keyword_hit_tags=True,
                relevance_score=0.8,
                heat_score=0.7,
                composite_score=0.75,
            )

        service._crawl_candidate_http_only = fake_http_only
        service._crawl_candidate = fake_browser_fallback

        result = service.run_task(task)
        service.close()

    assert result.success_count == 2
    assert all(name != "MainThread" for name in threaded_calls)
    assert fallback_threads == ["MainThread", "MainThread"]
