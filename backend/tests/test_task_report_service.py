from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.bootstrap import bootstrap_system_configs
from app.models.analysis import AiSummary, TopicCluster, TopicVideoRelation
from app.models.enums import TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video, VideoMetricSnapshot, VideoTextContent
from app.services.ai_client import AiJsonResponse
from app.services.task_report_service import TaskReportService


class FakeReportAiClient:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.default_model = "gpt-test"
        self.fallback_model = "gpt-fallback"

    def is_available(self) -> bool:
        return self.available

    def generate_json(self, prompt):
        return AiJsonResponse(
            payload={
                "outputs": [
                    {
                        "key": "melon_reader",
                        "content": "这是吃瓜版结果，直接告诉网友现在最热的是哪个话题。",
                    },
                    {
                        "key": "pro_analyst",
                        "content": "这是专业版结果，强调证据、结构和数据口径。",
                    },
                    {
                        "key": "ops_planning",
                        "content": "这是运营版结果，说明该追哪条热点和怎么做选题。",
                    },
                ]
            },
            raw_content='{"outputs":[]}',
            model_name="gpt-test",
        )


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = factory()
    bootstrap_system_configs(session, commit=True)
    return session


def seed_report_task(session: Session) -> str:
    task = CrawlTask(
        keyword="AI",
        status=TaskStatus.SUCCESS,
        requested_video_limit=10,
        max_pages=3,
        min_sleep_seconds=Decimal("1.00"),
        max_sleep_seconds=Decimal("2.00"),
        enable_proxy=False,
        source_ip_strategy="local_sleep",
        extra_params={
            "task_options": {
                "crawl_mode": "keyword",
                "search_scope": "site",
                "enable_keyword_synonym_expansion": True,
                "keyword_synonym_count": 1,
            },
            "keyword_expansion": {
                "source_keyword": "AI",
                "enabled": True,
                "requested_synonym_count": 1,
                "generated_synonyms": ["AIGC"],
                "expanded_keywords": ["AI", "AIGC"],
                "status": "success",
                "model_name": "gpt-expand",
                "error_message": None,
                "generated_at": "2026-04-09T00:00:00Z",
            },
            "crawl_stats": {
                "search_keywords_used": ["AI", "AIGC"],
                "expanded_keyword_count": 1,
            },
        },
    )
    session.add(task)
    session.flush()

    video = Video(
        bvid="BV1report",
        aid=123,
        title="AI 报告样本",
        url="https://www.bilibili.com/video/BV1report",
        author_name="Report UP",
        description="AI report demo",
        tags=["AI", "分析"],
        published_at=datetime(2026, 4, 9, tzinfo=timezone.utc),
        duration_seconds=240,
    )
    session.add(video)
    session.flush()

    session.add(
        TaskVideo(
            task_id=task.id,
            video_id=video.id,
            search_rank=1,
            keyword_hit_title=True,
            keyword_hit_description=True,
            keyword_hit_tags=True,
            relevance_score=Decimal("0.92"),
            heat_score=Decimal("0.88"),
            composite_score=Decimal("0.90"),
            is_selected=True,
        )
    )
    session.add(
        VideoMetricSnapshot(
            task_id=task.id,
            video_id=video.id,
            view_count=10000,
            like_count=900,
            coin_count=120,
            favorite_count=300,
            share_count=80,
            reply_count=60,
            danmaku_count=40,
            metrics_payload={"source": "report-test"},
        )
    )
    text_content = VideoTextContent(
        task_id=task.id,
        video_id=video.id,
        has_description=True,
        has_subtitle=True,
        description_text="AI report demo",
        subtitle_text="AI report subtitle",
        combined_text=(
            "Video Description:\nAI report demo\n\n"
            "Video Subtitle:\nAI report subtitle"
        ),
        combined_text_hash="report-hash",
        language_code="zh-CN",
    )
    session.add(text_content)
    session.flush()

    ai_summary = AiSummary(
        task_id=task.id,
        video_id=video.id,
        text_content_id=text_content.id,
        summary="AI 热点分析视频。",
        topics=["AI", "热点分析"],
        primary_topic="AI",
        tone="neutral",
        confidence=Decimal("0.95"),
        model_name="gpt-test",
        raw_response={"ok": True},
    )
    session.add(ai_summary)
    session.flush()

    topic = TopicCluster(
        task_id=task.id,
        name="AI",
        normalized_name="ai",
        description="AI 热点主题",
        keywords=["AI", "热点"],
        video_count=1,
        total_heat_score=Decimal("0.88"),
        average_heat_score=Decimal("0.88"),
        cluster_order=1,
    )
    session.add(topic)
    session.flush()

    session.add(
        TopicVideoRelation(
            task_id=task.id,
            topic_cluster_id=topic.id,
            video_id=video.id,
            ai_summary_id=ai_summary.id,
            relevance_score=Decimal("0.90"),
            is_primary=True,
        )
    )
    session.commit()
    return task.id


def test_task_report_service_returns_ai_outputs_when_ai_available() -> None:
    session = build_session()
    try:
        task_id = seed_report_task(session)
        report = TaskReportService(
            session, ai_client=FakeReportAiClient()
        ).build_report(task_id)

        assert report.ai_outputs[0].key == "melon_reader"
        assert report.ai_outputs[0].generation_mode == "ai"
        assert report.ai_outputs[0].model_name == "gpt-test"
        assert report.keyword_expansion is not None
        assert report.keyword_expansion.status == "success"
        assert report.search_keywords_used == ["AI", "AIGC"]
        assert report.expanded_keyword_count == 1
        assert "实际搜索词：AI、AIGC" in report.report_markdown
        assert "吃瓜版结果" in report.ai_outputs[0].content
    finally:
        session.close()


def test_task_report_service_can_persist_and_reuse_report_snapshot() -> None:
    session = build_session()
    try:
        task_id = seed_report_task(session)
        task = session.get(CrawlTask, task_id)
        assert task is not None

        service = TaskReportService(session, ai_client=FakeReportAiClient())
        generated = service.generate_and_persist(task)
        session.refresh(task)

        assert task.extra_params["report_snapshot"]["task_id"] == task_id

        cached = service.build_report(task_id)
        assert cached.task_id == generated.task_id
        assert cached.status == task.status.value
        assert cached.generated_at == generated.generated_at
        assert cached.sections[0].title == generated.sections[0].title
        assert cached.search_keywords_used == ["AI", "AIGC"]
    finally:
        session.close()


def test_task_report_service_falls_back_when_ai_unavailable() -> None:
    session = build_session()
    try:
        task_id = seed_report_task(session)
        report = TaskReportService(
            session, ai_client=FakeReportAiClient(available=False)
        ).build_report(task_id)

        assert report.ai_outputs[0].generation_mode == "fallback"
        assert report.ai_outputs[0].model_name is None
        assert "最终结果如下" in report.ai_outputs[0].content
    finally:
        session.close()
