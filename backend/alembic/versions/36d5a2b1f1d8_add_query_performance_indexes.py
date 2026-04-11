"""add query performance indexes

Revision ID: 36d5a2b1f1d8
Revises: 997b26573843
Create Date: 2026-04-07 14:20:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "36d5a2b1f1d8"
down_revision: Union[str, Sequence[str], None] = "997b26573843"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_crawl_task_log_task_id_created_at",
        "crawl_task_log",
        ["task_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_task_video_task_id_composite_score_search_rank",
        "task_video",
        ["task_id", "composite_score", "search_rank"],
        unique=False,
    )
    op.create_index(
        "ix_task_video_task_id_heat_score",
        "task_video",
        ["task_id", "heat_score"],
        unique=False,
    )
    op.create_index(
        "ix_topic_cluster_task_id_cluster_order",
        "topic_cluster",
        ["task_id", "cluster_order"],
        unique=False,
    )
    op.create_index(
        "ix_topic_video_relation_task_id_video_id",
        "topic_video_relation",
        ["task_id", "video_id"],
        unique=False,
    )
    op.create_index(
        "ix_topic_video_relation_task_id_topic_cluster_id",
        "topic_video_relation",
        ["task_id", "topic_cluster_id"],
        unique=False,
    )
    op.create_index(
        "ix_video_metric_snapshot_task_video_captured_created",
        "video_metric_snapshot",
        ["task_id", "video_id", "captured_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_video_metric_snapshot_task_video_captured_created",
        table_name="video_metric_snapshot",
    )
    op.drop_index(
        "ix_topic_video_relation_task_id_topic_cluster_id",
        table_name="topic_video_relation",
    )
    op.drop_index(
        "ix_topic_video_relation_task_id_video_id",
        table_name="topic_video_relation",
    )
    op.drop_index(
        "ix_topic_cluster_task_id_cluster_order",
        table_name="topic_cluster",
    )
    op.drop_index(
        "ix_task_video_task_id_heat_score",
        table_name="task_video",
    )
    op.drop_index(
        "ix_task_video_task_id_composite_score_search_rank",
        table_name="task_video",
    )
    op.drop_index(
        "ix_crawl_task_log_task_id_created_at",
        table_name="crawl_task_log",
    )
