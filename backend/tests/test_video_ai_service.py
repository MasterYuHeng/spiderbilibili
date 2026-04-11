from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.bootstrap import bootstrap_system_configs
from app.models.analysis import AiSummary
from app.models.enums import TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video, VideoTextContent
from app.schemas.analysis import VideoAiSummaryDraft
from app.services import video_ai_service as video_ai_service_module
from app.services.ai_client import AiPromptBundle, AiStructuredResponse
from app.services.video_ai_service import VideoAiService


class FakeAiClient:
    def __init__(
        self,
        *,
        payload: VideoAiSummaryDraft | None = None,
        error: Exception | None = None,
    ):
        self.payload = payload
        self.error = error
        self.prompts: list[AiPromptBundle] = []

    def is_available(self) -> bool:
        return True

    def generate_summary(self, prompt: AiPromptBundle) -> AiStructuredResponse:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        default_payload = VideoAiSummaryDraft(
            summary="这是一段足够长的默认摘要内容，用于通过质量控制并完成单元测试。",
            topics=["AI", "产品分析", "案例拆解"],
            primary_topic="AI",
            tone="neutral",
            confidence=0.88,
        )
        return AiStructuredResponse(
            payload=self.payload or default_payload,
            raw_content='{"summary":"ok"}',
            model_name="gpt-test",
        )


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    bootstrap_system_configs(session, commit=True)
    return session


def seed_task_with_text(session: Session) -> tuple[CrawlTask, Video]:
    task = CrawlTask(
        keyword="AI",
        status=TaskStatus.RUNNING,
        requested_video_limit=5,
        max_pages=2,
        min_sleep_seconds=Decimal("0.01"),
        max_sleep_seconds=Decimal("0.01"),
        enable_proxy=False,
        source_ip_strategy="local_sleep",
    )
    session.add(task)
    session.flush()

    video = Video(
        bvid="BV1ai",
        aid=1,
        title="AI 示例视频",
        url="https://www.bilibili.com/video/BV1ai",
        author_name="测试UP",
        description="这是一段关于 AI 产品趋势的视频简介。",
        tags=["AI", "产品"],
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
            relevance_score=Decimal("0.9"),
            heat_score=Decimal("0.8"),
            composite_score=Decimal("0.86"),
            is_selected=True,
        )
    )
    session.add(
        VideoTextContent(
            task_id=task.id,
            video_id=video.id,
            has_description=True,
            has_subtitle=True,
            description_text="这是一段关于 AI 产品趋势的视频简介。",
            subtitle_text="字幕补充了产品落地案例和市场观察。",
            combined_text=(
                "Video Description:\n这是一段关于 AI 产品趋势的视频简介。\n\n"
                "Video Subtitle:\n字幕补充了产品落地案例和市场观察。"
            ),
            combined_text_hash="hash-ai",
            language_code="zh-CN",
        )
    )
    session.commit()
    return task, video


def append_task_video(
    session: Session,
    task: CrawlTask,
    *,
    bvid: str,
    title: str,
    rank: int,
) -> Video:
    video = Video(
        bvid=bvid,
        aid=rank + 1,
        title=title,
        url=f"https://www.bilibili.com/video/{bvid}",
        author_name="测试UP",
        description="补充视频简介",
        tags=["AI", "产品"],
    )
    session.add(video)
    session.flush()

    session.add(
        TaskVideo(
            task_id=task.id,
            video_id=video.id,
            search_rank=rank,
            keyword_hit_title=True,
            keyword_hit_description=True,
            keyword_hit_tags=True,
            relevance_score=Decimal("0.88"),
            heat_score=Decimal("0.76"),
            composite_score=Decimal("0.82"),
            is_selected=True,
        )
    )
    session.add(
        VideoTextContent(
            task_id=task.id,
            video_id=video.id,
            has_description=True,
            has_subtitle=False,
            description_text="补充视频简介",
            subtitle_text=None,
            combined_text="Video Description:\n补充视频简介",
            combined_text_hash=f"hash-{bvid}",
            language_code="zh-CN",
        )
    )
    session.commit()
    return video


def test_video_ai_service_persists_structured_summary() -> None:
    with build_session() as session:
        task, video = seed_task_with_text(session)
        service = VideoAiService(
            session,
            ai_client=FakeAiClient(
                payload=VideoAiSummaryDraft(
                    summary=(
                        "该视频总结了 AI 产品趋势、落地案例和市场变化，"
                        "适合快速理解当前主线内容与核心观点。"
                    ),
                    topics=["AI", "产品趋势", "案例"],
                    primary_topic="AI",
                    tone="neutral",
                    confidence=0.92,
                )
            ),
        )

        result = service.analyze_task(task, batch_size=1)

        stored = session.scalar(
            select(AiSummary).where(
                AiSummary.task_id == task.id,
                AiSummary.video_id == video.id,
            )
        )

        assert result.success_count == 1
        assert result.failure_count == 0
        assert result.fallback_count == 0
        assert result.cached_count == 0
        assert result.clipped_count == 0
        assert task.analyzed_videos == 1
        assert stored is not None
        assert stored.primary_topic == "AI"
        assert stored.model_name == "gpt-test"
        assert stored.raw_response["used_fallback"] is False


def test_video_ai_service_filters_generic_topics_and_caps_topic_count() -> None:
    with build_session() as session:
        task, video = seed_task_with_text(session)
        service = VideoAiService(
            session,
            ai_client=FakeAiClient(
                payload=VideoAiSummaryDraft(
                    summary="这段摘要足够长，可以用于测试主题过滤、去重和数量上限控制。",
                    topics=[
                        "unclassified",
                        "AI对决",
                        "AI 对决",
                        "其他",
                        "AI玩法",
                        "AI玩法解析",
                        "未知",
                        "AI竞技",
                        "AI竞技赛",
                        "AI对战",
                        "AI对抗",
                        "杂项",
                        "AI游戏",
                    ],
                    primary_topic="AI对决",
                    tone="neutral",
                    confidence=0.91,
                )
            ),
        )

        service.analyze_task(task, batch_size=1)

        stored = session.scalar(
            select(AiSummary).where(
                AiSummary.task_id == task.id,
                AiSummary.video_id == video.id,
            )
        )

        assert stored is not None
        assert "unclassified" not in stored.topics
        assert "其他" not in stored.topics
        assert "未知" not in stored.topics
        assert len(stored.topics) <= 10
        assert stored.primary_topic == stored.topics[0]


def test_video_ai_service_falls_back_when_ai_client_fails() -> None:
    with build_session() as session:
        task, video = seed_task_with_text(session)
        service = VideoAiService(
            session,
            ai_client=FakeAiClient(error=RuntimeError("upstream timeout")),
        )

        result = service.analyze_task(task, batch_size=1)

        stored = session.scalar(
            select(AiSummary).where(
                AiSummary.task_id == task.id,
                AiSummary.video_id == video.id,
            )
        )

        assert result.success_count == 1
        assert result.failure_count == 0
        assert result.fallback_count == 1
        assert result.cached_count == 0
        assert stored is not None
        assert stored.model_name == "heuristic-fallback"
        assert stored.raw_response["used_fallback"] is True
        assert stored.primary_topic != "unclassified"
        assert stored.summary.startswith("视频《AI 示例视频》主要围绕")


def test_video_ai_service_reuses_cached_summary_for_unchanged_text() -> None:
    with build_session() as session:
        task, video = seed_task_with_text(session)
        text_content = session.scalar(
            select(VideoTextContent).where(
                VideoTextContent.task_id == task.id,
                VideoTextContent.video_id == video.id,
            )
        )
        assert text_content is not None
        session.add(
            AiSummary(
                task_id=task.id,
                video_id=video.id,
                text_content_id=text_content.id,
                summary="已存在的摘要内容足够长，应该被复用而不是重复调用模型。",
                topics=["AI", "复用", "缓存"],
                primary_topic="AI",
                tone="neutral",
                confidence=Decimal("0.81"),
                model_name="cached-model",
                prompt_version="v1",
                raw_response={"used_fallback": False},
            )
        )
        session.commit()

        fake_ai_client = FakeAiClient()
        service = VideoAiService(session, ai_client=fake_ai_client)

        result = service.analyze_task(task, batch_size=1)

        stored = session.scalar(
            select(AiSummary).where(
                AiSummary.task_id == task.id,
                AiSummary.video_id == video.id,
            )
        )

        assert result.total_count == 1
        assert result.cached_count == 1
        assert result.success_count == 0
        assert task.analyzed_videos == 1
        assert fake_ai_client.prompts == []
        assert stored is not None
        assert stored.model_name == "cached-model"


def test_video_ai_service_clips_long_input_before_sending_to_ai() -> None:
    with build_session() as session:
        task, video = seed_task_with_text(session)
        text_content = session.scalar(
            select(VideoTextContent).where(
                VideoTextContent.task_id == task.id,
                VideoTextContent.video_id == video.id,
            )
        )
        assert text_content is not None
        text_content.combined_text = (
            "Video Title:\nAI 示例视频\n\n"
            f"Video Description:\n{'产品趋势' * 180}\n\n"
            f"Video Search Summary:\n{'搜索摘要' * 180}\n\n"
            f"Video Subtitle:\n{'字幕内容' * 500}"
        )
        session.commit()

        fake_ai_client = FakeAiClient()
        service = VideoAiService(session, ai_client=fake_ai_client)
        service.settings.ai_input_char_limit = 600

        result = service.analyze_task(task, batch_size=1)

        assert result.success_count == 1
        assert result.clipped_count == 1
        assert fake_ai_client.prompts
        assert len(fake_ai_client.prompts[0].user_prompt) < len(
            text_content.combined_text
        )


def test_video_ai_service_loads_summary_defaults_once_per_task(
    monkeypatch,
) -> None:
    with build_session() as session:
        task, _ = seed_task_with_text(session)
        append_task_video(
            session,
            task,
            bvid="BV1extra",
            title="第二个 AI 视频",
            rank=2,
        )

        summary_calls = {"count": 0}
        quality_calls = {"count": 0}
        original_summary_defaults = video_ai_service_module.get_ai_summary_defaults
        original_quality_defaults = (
            video_ai_service_module.get_ai_quality_control_defaults
        )

        def counted_summary_defaults(session, settings):
            summary_calls["count"] += 1
            return original_summary_defaults(session, settings)

        def counted_quality_defaults(session):
            quality_calls["count"] += 1
            return original_quality_defaults(session)

        monkeypatch.setattr(
            "app.services.video_ai_service.get_ai_summary_defaults",
            counted_summary_defaults,
        )
        monkeypatch.setattr(
            "app.services.video_ai_service.get_ai_quality_control_defaults",
            counted_quality_defaults,
        )

        result = VideoAiService(session, ai_client=FakeAiClient()).analyze_task(
            task,
            batch_size=2,
        )

    assert result.success_count == 2
    assert summary_calls["count"] == 1
    assert quality_calls["count"] == 1
