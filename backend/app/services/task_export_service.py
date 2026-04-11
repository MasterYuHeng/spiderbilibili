from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Any

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis import AiSummary
from app.schemas.task import TaskTopicRead
from app.services.task_result_service import (
    TaskVideoMetricFilters,
    TaskVideoRow,
    get_task_topics,
    get_task_video_rows,
)
from app.services.task_service import get_task_or_raise


@dataclass(slots=True)
class ExportArtifact:
    filename: str
    media_type: str
    content: bytes


@dataclass(slots=True)
class ExportTable:
    sheet_name: str
    columns: list[str]
    rows: list[dict[str, Any]]


class TaskExportService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def export_dataset(
        self,
        task_id: str,
        *,
        dataset: str,
        export_format: str,
        sort_by: str = "composite_score",
        sort_order: str = "desc",
        topic: str | None = None,
        filters: TaskVideoMetricFilters | None = None,
    ) -> ExportArtifact:
        task = get_task_or_raise(self.session, task_id)
        table = self._build_export_table(
            task.id,
            dataset=dataset,
            sort_by=sort_by,
            sort_order=sort_order,
            topic=topic,
            filters=filters,
        )

        extension = "xlsx" if export_format == "excel" else export_format
        filename = f"task-{task.id}-{dataset}.{extension}"

        if export_format == "json":
            content = self._build_json_bytes(task.id, dataset, table)
            return ExportArtifact(
                filename=filename,
                media_type="application/json; charset=utf-8",
                content=content,
            )

        if export_format == "csv":
            content = self._build_csv_bytes(table)
            return ExportArtifact(
                filename=filename,
                media_type="text/csv; charset=utf-8",
                content=content,
            )

        if export_format == "excel":
            content = self._build_excel_bytes(table)
            return ExportArtifact(
                filename=filename,
                media_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                content=content,
            )

        raise ValueError(f"Unsupported export format: {export_format}")

    def _build_export_table(
        self,
        task_id: str,
        *,
        dataset: str,
        sort_by: str,
        sort_order: str,
        topic: str | None,
        filters: TaskVideoMetricFilters | None,
    ) -> ExportTable:
        if dataset == "videos":
            return self._build_video_export_table(
                task_id,
                sort_by=sort_by,
                sort_order=sort_order,
                topic=topic,
                filters=filters,
            )
        if dataset == "topics":
            return self._build_topic_export_table(task_id, topic=topic)
        if dataset == "summaries":
            return self._build_summary_export_table(
                task_id,
                sort_by=sort_by,
                sort_order=sort_order,
                topic=topic,
                filters=filters,
            )
        raise ValueError(f"Unsupported export dataset: {dataset}")

    def _build_video_export_table(
        self,
        task_id: str,
        *,
        sort_by: str,
        sort_order: str,
        topic: str | None,
        filters: TaskVideoMetricFilters | None,
    ) -> ExportTable:
        columns = [
            "video_id",
            "bvid",
            "aid",
            "title",
            "url",
            "author_name",
            "author_mid",
            "cover_url",
            "description",
            "tags",
            "published_at",
            "duration_seconds",
            "search_rank",
            "keyword_hit_title",
            "keyword_hit_description",
            "keyword_hit_tags",
            "relevance_score",
            "heat_score",
            "composite_score",
            "is_selected",
            "view_count",
            "like_count",
            "coin_count",
            "favorite_count",
            "share_count",
            "reply_count",
            "danmaku_count",
            "like_view_ratio",
            "metrics_captured_at",
            "has_description",
            "has_subtitle",
            "language_code",
            "description_text",
            "subtitle_text",
            "combined_text",
            "summary",
            "topics",
            "primary_topic",
            "tone",
            "confidence",
            "model_name",
        ]
        task_rows = get_task_video_rows(
            self.session,
            task_id,
            sort_by=sort_by,
            sort_order=sort_order,
            topic=topic,
            filters=filters,
        )
        table_rows = [self._flatten_video_row(item) for item in task_rows]
        return ExportTable(sheet_name="videos", columns=columns, rows=table_rows)

    def _build_topic_export_table(
        self,
        task_id: str,
        *,
        topic: str | None,
    ) -> ExportTable:
        payload = get_task_topics(self.session, task_id)
        normalized_topic = topic.strip().casefold() if topic else None
        items = payload.items
        if normalized_topic:
            items = [
                item
                for item in payload.items
                if item.name.casefold() == normalized_topic
                or item.normalized_name.casefold() == normalized_topic
            ]
        columns = [
            "id",
            "name",
            "normalized_name",
            "description",
            "keywords",
            "video_count",
            "total_heat_score",
            "average_heat_score",
            "video_ratio",
            "average_engagement_rate",
            "cluster_order",
            "representative_video_id",
            "representative_bvid",
            "representative_title",
            "representative_url",
            "representative_composite_score",
        ]
        rows = [self._flatten_topic_row(item) for item in items]
        return ExportTable(sheet_name="topics", columns=columns, rows=rows)

    def _build_summary_export_table(
        self,
        task_id: str,
        *,
        sort_by: str,
        sort_order: str,
        topic: str | None,
        filters: TaskVideoMetricFilters | None,
    ) -> ExportTable:
        video_rows = get_task_video_rows(
            self.session,
            task_id,
            sort_by=sort_by,
            sort_order=sort_order,
            topic=topic,
            filters=filters,
        )
        columns = [
            "video_id",
            "bvid",
            "title",
            "url",
            "published_at",
            "composite_score",
            "summary",
            "topics",
            "primary_topic",
            "tone",
            "confidence",
            "model_name",
            "has_description",
            "has_subtitle",
            "language_code",
            "combined_text",
        ]
        rows = [
            self._flatten_summary_row(item)
            for item in video_rows
            if item.ai_summary is not None
        ]
        return ExportTable(sheet_name="summaries", columns=columns, rows=rows)

    def _build_json_bytes(
        self,
        task_id: str,
        dataset: str,
        table: ExportTable,
    ) -> bytes:
        payload: dict[str, Any] = {
            "task_id": task_id,
            "dataset": dataset,
            "items": table.rows,
        }
        if dataset == "topics":
            payload["total"] = len(table.rows)
        elif dataset == "videos":
            payload["total"] = len(table.rows)
        elif dataset == "summaries":
            payload["total"] = len(table.rows)
            payload["has_ai_summaries"] = bool(
                self.session.scalar(
                    select(func.count())
                    .select_from(AiSummary)
                    .where(AiSummary.task_id == task_id)
                )
                or 0
            )
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=_serialize_value,
        ).encode("utf-8")

    @staticmethod
    def _build_csv_bytes(table: ExportTable) -> bytes:
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=table.columns, extrasaction="ignore")
        writer.writeheader()
        for row in table.rows:
            writer.writerow(row)
        return buffer.getvalue().encode("utf-8-sig")

    @staticmethod
    def _build_excel_bytes(table: ExportTable) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = table.sheet_name
        sheet.append(table.columns)
        for row in table.rows:
            sheet.append([row.get(column) for column in table.columns])

        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    @staticmethod
    def _flatten_video_row(item: TaskVideoRow) -> dict[str, Any]:
        metrics = item.metric_snapshot
        text_content = item.text_content
        ai_summary = item.ai_summary
        return {
            "video_id": item.video.id,
            "bvid": item.video.bvid,
            "aid": item.video.aid,
            "title": item.video.title,
            "url": item.video.url,
            "author_name": item.video.author_name,
            "author_mid": item.video.author_mid,
            "cover_url": item.video.cover_url,
            "description": item.video.description,
            "tags": " | ".join(item.video.tags or []),
            "published_at": _serialize_value(item.video.published_at),
            "duration_seconds": item.video.duration_seconds,
            "search_rank": item.task_video.search_rank,
            "keyword_hit_title": item.task_video.keyword_hit_title,
            "keyword_hit_description": item.task_video.keyword_hit_description,
            "keyword_hit_tags": item.task_video.keyword_hit_tags,
            "relevance_score": _to_float(item.task_video.relevance_score),
            "heat_score": _to_float(item.task_video.heat_score),
            "composite_score": _to_float(item.task_video.composite_score),
            "is_selected": item.task_video.is_selected,
            "view_count": metrics.view_count if metrics else 0,
            "like_count": metrics.like_count if metrics else 0,
            "coin_count": metrics.coin_count if metrics else 0,
            "favorite_count": metrics.favorite_count if metrics else 0,
            "share_count": metrics.share_count if metrics else 0,
            "reply_count": metrics.reply_count if metrics else 0,
            "danmaku_count": metrics.danmaku_count if metrics else 0,
            "like_view_ratio": _calculate_like_view_ratio(metrics),
            "metrics_captured_at": _serialize_value(
                metrics.captured_at if metrics else None
            ),
            "has_description": text_content.has_description if text_content else False,
            "has_subtitle": text_content.has_subtitle if text_content else False,
            "language_code": text_content.language_code if text_content else None,
            "description_text": text_content.description_text if text_content else None,
            "subtitle_text": text_content.subtitle_text if text_content else None,
            "combined_text": text_content.combined_text if text_content else None,
            "summary": ai_summary.summary if ai_summary else None,
            "topics": " | ".join(ai_summary.topics) if ai_summary else None,
            "primary_topic": ai_summary.primary_topic if ai_summary else None,
            "tone": ai_summary.tone if ai_summary else None,
            "confidence": ai_summary.confidence if ai_summary else None,
            "model_name": ai_summary.model_name if ai_summary else None,
        }

    @staticmethod
    def _flatten_topic_row(item: TaskTopicRead) -> dict[str, Any]:
        representative = item.representative_video
        return {
            "id": item.id,
            "name": item.name,
            "normalized_name": item.normalized_name,
            "description": item.description,
            "keywords": " | ".join(item.keywords),
            "video_count": item.video_count,
            "total_heat_score": item.total_heat_score,
            "average_heat_score": item.average_heat_score,
            "video_ratio": item.video_ratio,
            "average_engagement_rate": item.average_engagement_rate,
            "cluster_order": item.cluster_order,
            "representative_video_id": (
                representative.video_id if representative else None
            ),
            "representative_bvid": representative.bvid if representative else None,
            "representative_title": representative.title if representative else None,
            "representative_url": representative.url if representative else None,
            "representative_composite_score": (
                representative.composite_score if representative else None
            ),
        }

    @staticmethod
    def _flatten_summary_row(item: TaskVideoRow) -> dict[str, Any]:
        assert item.ai_summary is not None
        text_content = item.text_content
        return {
            "video_id": item.video.id,
            "bvid": item.video.bvid,
            "title": item.video.title,
            "url": item.video.url,
            "published_at": _serialize_value(item.video.published_at),
            "composite_score": _to_float(item.task_video.composite_score),
            "summary": item.ai_summary.summary,
            "topics": " | ".join(item.ai_summary.topics),
            "primary_topic": item.ai_summary.primary_topic,
            "tone": item.ai_summary.tone,
            "confidence": _to_float(item.ai_summary.confidence),
            "model_name": item.ai_summary.model_name,
            "has_description": text_content.has_description if text_content else False,
            "has_subtitle": text_content.has_subtitle if text_content else False,
            "language_code": text_content.language_code if text_content else None,
            "combined_text": text_content.combined_text if text_content else None,
        }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _calculate_like_view_ratio(metrics: Any) -> float | None:
    if metrics is None or metrics.view_count <= 0:
        return None
    return metrics.like_count / metrics.view_count
