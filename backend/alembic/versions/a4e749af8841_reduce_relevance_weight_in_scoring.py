"""Reduce relevance weight in composite video scoring.

Revision ID: a4e749af8841
Revises: 36d5a2b1f1d8
Create Date: 2026-04-12 04:08:00.000000
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4e749af8841"
down_revision = "36d5a2b1f1d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    system_config = sa.table(
        "system_config",
        sa.column("config_key", sa.String(length=128)),
        sa.column("config_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    statement = sa.select(system_config.c.config_value).where(
        system_config.c.config_key == "analysis.scoring_weights"
    )
    current = bind.execute(statement).scalar_one_or_none()
    if current is None:
        return

    config_value = dict(current or {})
    config_value["relevance_weight"] = 0.4
    config_value["heat_weight"] = 0.6

    bind.execute(
        system_config.update()
        .where(system_config.c.config_key == "analysis.scoring_weights")
        .values(
            config_value=config_value,
            updated_at=datetime.now(timezone.utc),
        )
    )

    task_video = sa.table(
        "task_video",
        sa.column("id", sa.String(length=36)),
        sa.column("relevance_score", sa.Numeric(precision=10, scale=4)),
        sa.column("heat_score", sa.Numeric(precision=10, scale=4)),
        sa.column("composite_score", sa.Numeric(precision=10, scale=4)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    task_video_rows = bind.execute(
        sa.select(
            task_video.c.id,
            task_video.c.relevance_score,
            task_video.c.heat_score,
        )
    ).all()
    for row in task_video_rows:
        composite_score = round(
            (float(row.relevance_score or 0) * 0.4)
            + (float(row.heat_score or 0) * 0.6),
            4,
        )
        bind.execute(
            task_video.update()
            .where(task_video.c.id == row.id)
            .values(
                composite_score=Decimal(str(composite_score)),
                updated_at=datetime.now(timezone.utc),
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    system_config = sa.table(
        "system_config",
        sa.column("config_key", sa.String(length=128)),
        sa.column("config_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    statement = sa.select(system_config.c.config_value).where(
        system_config.c.config_key == "analysis.scoring_weights"
    )
    current = bind.execute(statement).scalar_one_or_none()
    if current is None:
        return

    config_value = dict(current or {})
    config_value["relevance_weight"] = 0.6
    config_value["heat_weight"] = 0.4

    bind.execute(
        system_config.update()
        .where(system_config.c.config_key == "analysis.scoring_weights")
        .values(
            config_value=config_value,
            updated_at=datetime.now(timezone.utc),
        )
    )

    task_video = sa.table(
        "task_video",
        sa.column("id", sa.String(length=36)),
        sa.column("relevance_score", sa.Numeric(precision=10, scale=4)),
        sa.column("heat_score", sa.Numeric(precision=10, scale=4)),
        sa.column("composite_score", sa.Numeric(precision=10, scale=4)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    task_video_rows = bind.execute(
        sa.select(
            task_video.c.id,
            task_video.c.relevance_score,
            task_video.c.heat_score,
        )
    ).all()
    for row in task_video_rows:
        composite_score = round(
            (float(row.relevance_score or 0) * 0.6)
            + (float(row.heat_score or 0) * 0.4),
            4,
        )
        bind.execute(
            task_video.update()
            .where(task_video.c.id == row.id)
            .values(
                composite_score=Decimal(str(composite_score)),
                updated_at=datetime.now(timezone.utc),
            )
        )
