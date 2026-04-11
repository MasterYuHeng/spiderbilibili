from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.task import CrawlTask
from app.schemas.task import TaskTopicRead
from app.services.task_log_service import get_task_log_count
from app.services.task_result_service import (
    TaskVideoRow,
    get_task_topics,
    get_task_video_rows,
)
from app.services.task_service import get_task_or_raise
from app.services.task_state_machine import is_terminal_status

PASS = "pass"
WARN = "warn"
FAIL = "fail"


@dataclass(slots=True)
class AcceptanceCheck:
    code: str
    title: str
    status: str
    message: str
    actual: Any | None = None
    expected: Any | None = None


@dataclass(slots=True)
class TaskAcceptanceReport:
    task_id: str
    task_status: str
    overall_status: str
    sections: dict[str, list[AcceptanceCheck]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_status": self.task_status,
            "overall_status": self.overall_status,
            "sections": {
                name: [asdict(item) for item in checks]
                for name, checks in self.sections.items()
            },
        }


class TaskAcceptanceService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def build_report(self, task_id: str) -> TaskAcceptanceReport:
        task = get_task_or_raise(self.session, task_id)
        video_rows = get_task_video_rows(self.session, task.id)
        topics = get_task_topics(self.session, task.id).items

        sections = {
            "functional": self._build_functional_checks(task, video_rows, topics),
            "data": self._build_data_checks(video_rows, topics),
            "stability": self._build_stability_checks(task),
            "compliance": self._build_compliance_checks(task),
        }

        statuses = [check.status for checks in sections.values() for check in checks]
        if FAIL in statuses:
            overall_status = FAIL
        elif WARN in statuses:
            overall_status = WARN
        else:
            overall_status = PASS

        return TaskAcceptanceReport(
            task_id=task.id,
            task_status=task.status.value,
            overall_status=overall_status,
            sections=sections,
        )

    def _build_functional_checks(
        self,
        task: CrawlTask,
        video_rows: list[TaskVideoRow],
        topics: list[TaskTopicRead],
    ) -> list[AcceptanceCheck]:
        ai_count = sum(1 for row in video_rows if row.ai_summary is not None)
        checks = [
            AcceptanceCheck(
                code="task-status-visible",
                title="Task status is visible",
                status=PASS,
                message="Task detail and progress payloads are available.",
                actual=task.status.value,
            ),
            self._count_check(
                code="task-videos-available",
                title="Video results are available",
                count=len(video_rows),
                success_message="At least one task video result is available.",
                empty_message="The task does not have any video result yet.",
            ),
            self._count_check(
                code="task-ai-summaries-available",
                title="AI summaries are available",
                count=ai_count,
                success_message="At least one AI summary is available.",
                empty_message="The task does not have AI summaries yet.",
            ),
            self._count_check(
                code="task-topics-available",
                title="Topic stats are available",
                count=len(topics),
                success_message="At least one topic cluster is available.",
                empty_message="The task does not have topic clusters yet.",
            ),
        ]

        checks.append(
            AcceptanceCheck(
                code="task-export-ready",
                title="Export path is ready",
                status=PASS if video_rows else WARN,
                message=(
                    "Videos, topics, and summaries can be exported for this task."
                    if video_rows
                    else "Export logic exists, but the task does not have data yet."
                ),
                actual=len(video_rows),
            )
        )
        return checks

    def _build_data_checks(
        self,
        video_rows: list[TaskVideoRow],
        topics: list[TaskTopicRead],
    ) -> list[AcceptanceCheck]:
        if not video_rows:
            return [
                AcceptanceCheck(
                    code="data-unavailable",
                    title="Task data is unavailable",
                    status=WARN,
                    message="The task has no videos, so data acceptance cannot run.",
                )
            ]

        duplicate_video_count = len(video_rows) - len(
            {row.video.id for row in video_rows}
        )
        topic_name_ratio = (
            self._ratio(bool(topic.name.strip()) for topic in topics) if topics else 0.0
        )
        topic_desc_ratio = (
            self._ratio(bool((topic.description or "").strip()) for topic in topics)
            if topics
            else 0.0
        )
        heat_scores = [
            float(row.task_video.heat_score)
            for row in video_rows
            if row.task_video.heat_score is not None
        ]
        composite_scores = [
            float(row.task_video.composite_score)
            for row in video_rows
            if row.task_video.composite_score is not None
        ]
        score_is_valid = all(
            row.task_video.heat_score is not None
            and row.task_video.composite_score is not None
            and float(row.task_video.heat_score) >= 0
            and float(row.task_video.composite_score) >= 0
            for row in video_rows
        )

        return [
            self._ratio_check(
                code="video-bvid-completeness",
                title="BVID completeness",
                ratio=self._ratio(bool(row.video.bvid) for row in video_rows),
                threshold=1.0,
            ),
            self._ratio_check(
                code="video-title-completeness",
                title="Video title completeness",
                ratio=self._ratio(
                    bool((row.video.title or "").strip()) for row in video_rows
                ),
                threshold=1.0,
            ),
            self._ratio_check(
                code="video-url-completeness",
                title="Video URL completeness",
                ratio=self._ratio(
                    bool((row.video.url or "").strip()) for row in video_rows
                ),
                threshold=1.0,
            ),
            self._ratio_check(
                code="video-publish-time-completeness",
                title="Publish time completeness",
                ratio=self._ratio(
                    row.video.published_at is not None for row in video_rows
                ),
                threshold=0.8,
            ),
            self._ratio_check(
                code="video-author-completeness",
                title="Author completeness",
                ratio=self._ratio(
                    bool((row.video.author_name or "").strip()) for row in video_rows
                ),
                threshold=0.8,
            ),
            AcceptanceCheck(
                code="topic-readability",
                title="Topic readability",
                status=(
                    PASS
                    if topics
                    and topic_name_ratio >= 1.0
                    and topic_desc_ratio >= 0.5
                    else WARN
                ),
                message=(
                    "Topic names are present and most topics have descriptions."
                    if topics
                    and topic_name_ratio >= 1.0
                    and topic_desc_ratio >= 0.5
                    else (
                        "Topics are not available yet."
                        if not topics
                        else "Topics exist, but descriptions should be improved."
                    )
                ),
                actual={
                    "topic_count": len(topics),
                    "named_ratio": round(topic_name_ratio, 4),
                    "described_ratio": round(topic_desc_ratio, 4),
                },
            ),
            AcceptanceCheck(
                code="heat-score-validity",
                title="Heat score validity",
                status=PASS if score_is_valid else FAIL,
                message=(
                    "All rows have non-negative heat and composite scores."
                    if score_is_valid
                    else "Some rows have missing or invalid scores."
                ),
                actual={
                    "mean_heat_score": (
                        round(mean(heat_scores), 4) if heat_scores else None
                    ),
                    "mean_composite_score": (
                        round(mean(composite_scores), 4)
                        if composite_scores
                        else None
                    ),
                },
            ),
            AcceptanceCheck(
                code="video-dedupe",
                title="Video dedupe",
                status=PASS if duplicate_video_count == 0 else FAIL,
                message=(
                    "No duplicate task videos were detected."
                    if duplicate_video_count == 0
                    else "Duplicate task videos were detected."
                ),
                actual={
                    "video_rows": len(video_rows),
                    "duplicate_video_count": duplicate_video_count,
                },
            ),
        ]

    def _build_stability_checks(self, task: CrawlTask) -> list[AcceptanceCheck]:
        log_count = get_task_log_count(self.session, task.id)
        retryable = task.status.value in {"failed", "cancelled", "partial_success"}

        return [
            AcceptanceCheck(
                code="task-logs-complete",
                title="Task logs are present",
                status=PASS if log_count > 0 else FAIL,
                message=(
                    "Task logs are present."
                    if log_count > 0
                    else "Task logs are missing."
                ),
                actual=log_count,
            ),
            AcceptanceCheck(
                code="task-terminal-state",
                title="Terminal state reached",
                status=PASS if is_terminal_status(task.status) else WARN,
                message=(
                    "The task has reached a terminal state."
                    if is_terminal_status(task.status)
                    else "The task is still running."
                ),
                actual=task.status.value,
            ),
            AcceptanceCheck(
                code="task-retry-available",
                title="Retry path is available",
                status=PASS if retryable or task.status.value == "success" else WARN,
                message=(
                    "The task can be retried."
                    if retryable
                    else "The task does not currently require retry."
                ),
                actual=task.status.value,
            ),
        ]

    def _build_compliance_checks(self, task: CrawlTask) -> list[AcceptanceCheck]:
        proxy_strategy_is_valid = (
            (not task.enable_proxy and task.source_ip_strategy == "local_sleep")
            or (
                task.enable_proxy
                and task.source_ip_strategy
                in {"proxy_pool", "custom_proxy", "local_sleep"}
            )
        )

        return [
            AcceptanceCheck(
                code="crawler-rate-limit-configured",
                title="Crawler rate limit is configured",
                status=(
                    PASS
                    if self.settings.crawler_rate_limit_per_minute > 0
                    else FAIL
                ),
                message=(
                    "Crawler rate limit is configured."
                    if self.settings.crawler_rate_limit_per_minute > 0
                    else "Crawler rate limit must be greater than zero."
                ),
                actual=self.settings.crawler_rate_limit_per_minute,
            ),
            AcceptanceCheck(
                code="crawler-sleep-window-valid",
                title="Crawler sleep window is valid",
                status=(
                    PASS
                    if task.min_sleep_seconds <= task.max_sleep_seconds
                    else FAIL
                ),
                message=(
                    "Task sleep window is valid."
                    if task.min_sleep_seconds <= task.max_sleep_seconds
                    else "Task sleep window is invalid."
                ),
                actual={
                    "min_sleep_seconds": float(task.min_sleep_seconds),
                    "max_sleep_seconds": float(task.max_sleep_seconds),
                },
            ),
            AcceptanceCheck(
                code="proxy-strategy-controlled",
                title="Proxy strategy is controlled",
                status=PASS if proxy_strategy_is_valid else FAIL,
                message=(
                    "Proxy strategy is within the allowed set."
                    if proxy_strategy_is_valid
                    else "Proxy strategy is outside the allowed set."
                ),
                actual={
                    "enable_proxy": task.enable_proxy,
                    "source_ip_strategy": task.source_ip_strategy,
                },
            ),
        ]

    @staticmethod
    def _ratio(values: Any) -> float:
        materialized = list(values)
        if not materialized:
            return 0.0
        return sum(1 for value in materialized if value) / len(materialized)

    def _ratio_check(
        self,
        *,
        code: str,
        title: str,
        ratio: float,
        threshold: float,
    ) -> AcceptanceCheck:
        status = PASS if ratio >= threshold else WARN
        return AcceptanceCheck(
            code=code,
            title=title,
            status=status,
            message=(
                f"{title} meets the target threshold."
                if status == PASS
                else f"{title} is below the recommended threshold."
            ),
            actual=round(ratio, 4),
            expected=threshold,
        )

    @staticmethod
    def _count_check(
        *,
        code: str,
        title: str,
        count: int,
        success_message: str,
        empty_message: str,
    ) -> AcceptanceCheck:
        return AcceptanceCheck(
            code=code,
            title=title,
            status=PASS if count > 0 else WARN,
            message=success_message if count > 0 else empty_message,
            actual=count,
        )
