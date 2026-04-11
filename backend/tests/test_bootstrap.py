from __future__ import annotations

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.bootstrap import DEFAULT_SYSTEM_CONFIGS, bootstrap_system_configs
from app.models.analysis import SystemConfig
from app.models.base import Base
from app.models.enums import TaskStatus
from app.models.task import CrawlTask


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def test_bootstrap_system_configs_is_idempotent() -> None:
    with build_session() as session:
        first_run = bootstrap_system_configs(session, commit=False)
        session.commit()

        second_run = bootstrap_system_configs(session, commit=False)
        session.commit()

        rows = session.scalars(
            select(SystemConfig).order_by(SystemConfig.config_key)
        ).all()

    assert first_run == len(DEFAULT_SYSTEM_CONFIGS)
    assert second_run == len(DEFAULT_SYSTEM_CONFIGS)
    assert len(rows) == len(DEFAULT_SYSTEM_CONFIGS)
    assert {row.config_key for row in rows} >= {
        "ai.batch_defaults",
        "ai.quality_control",
        "ai.summary_defaults",
    }


def test_task_status_persists_enum_value() -> None:
    with build_session() as session:
        task = CrawlTask(keyword="keyword", status=TaskStatus.PENDING)
        session.add(task)
        session.commit()

        stored_value = session.execute(
            text("SELECT status FROM crawl_task")
        ).scalar_one()

    assert stored_value == TaskStatus.PENDING.value
