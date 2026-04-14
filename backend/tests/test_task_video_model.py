from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.bootstrap import bootstrap_system_configs
from app.models.enums import TaskStatus
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    bootstrap_system_configs(session, commit=True)
    return session


def test_task_video_keyword_expansion_fields_default_safely() -> None:
    session = build_session()

    task = CrawlTask(
        keyword="和平精英",
        status=TaskStatus.PENDING,
        requested_video_limit=10,
        max_pages=2,
        min_sleep_seconds=Decimal("0.10"),
        max_sleep_seconds=Decimal("0.20"),
        enable_proxy=False,
        source_ip_strategy="local_sleep",
    )
    video = Video(
        bvid="BV1synonym",
        aid=1001,
        title="和平精英内容示例",
        url="https://www.bilibili.com/video/BV1synonym",
    )
    session.add_all([task, video])
    session.flush()

    task_video = TaskVideo(task_id=task.id, video_id=video.id)
    session.add(task_video)
    session.commit()
    session.refresh(task_video)

    assert task_video.matched_keywords == []
    assert task_video.primary_matched_keyword is None
    assert task_video.keyword_match_count == 0
