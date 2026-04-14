"""Add keyword expansion fields to task video.

Revision ID: b56a6f7d9c21
Revises: a4e749af8841
Create Date: 2026-04-13 09:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b56a6f7d9c21"
down_revision = "a4e749af8841"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task_video") as batch_op:
        batch_op.add_column(sa.Column("matched_keywords", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("primary_matched_keyword", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(sa.Column("keyword_match_count", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_task_video_primary_matched_keyword",
            ["primary_matched_keyword"],
            unique=False,
        )

    bind = op.get_bind()
    task_video = sa.table(
        "task_video",
        sa.column("matched_keywords", sa.JSON()),
        sa.column("keyword_match_count", sa.Integer()),
    )

    bind.execute(
        task_video.update()
        .where(task_video.c.matched_keywords.is_(None))
        .values(matched_keywords=[])
    )
    bind.execute(
        task_video.update()
        .where(task_video.c.keyword_match_count.is_(None))
        .values(keyword_match_count=0)
    )

    with op.batch_alter_table("task_video") as batch_op:
        batch_op.alter_column("matched_keywords", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column(
            "keyword_match_count",
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("task_video") as batch_op:
        batch_op.drop_index("ix_task_video_primary_matched_keyword")
        batch_op.drop_column("keyword_match_count")
        batch_op.drop_column("primary_matched_keyword")
        batch_op.drop_column("matched_keywords")
