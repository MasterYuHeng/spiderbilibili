from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.base import utc_now
from app.models.enums import TaskStage
from app.schemas.task import TaskAnalysisPayload, TaskAnalysisWeightsUpdateRequest
from app.services.analysis_weight_service import (
    build_metric_weight_storage_payload,
    get_metric_spec,
    resolve_metric_weight_map,
)
from app.services.task_log_service import create_task_log
from app.services.task_report_service import TaskReportService
from app.services.task_result_service import get_task_analysis
from app.services.task_service import get_task_or_raise
from app.services.task_state_machine import is_terminal_status
from app.services.statistics_service import StatisticsService


def update_task_analysis_weights(
    session: Session,
    task_id: str,
    payload: TaskAnalysisWeightsUpdateRequest,
) -> TaskAnalysisPayload:
    task = get_task_or_raise(session, task_id)
    if not is_terminal_status(task.status):
        raise ValidationError("只能在任务执行完成后修改分析权重并重新分析。")

    raw_weight_map = resolve_metric_weight_map(task.extra_params)
    updated_metric_keys = _merge_updated_metric_weights(raw_weight_map, payload)
    updated_at = utc_now()

    extra_params = dict(task.extra_params or {})
    extra_params["analysis_metric_weights"] = {
        "updated_at": updated_at.isoformat(),
        "metrics": build_metric_weight_storage_payload(raw_weight_map),
    }
    task.extra_params = extra_params
    session.commit()

    create_task_log(
        session,
        task=task,
        stage=TaskStage.TOPIC,
        message="Confirmed custom analysis metric weights and restarted analysis generation.",
        payload={
            "updated_metric_keys": updated_metric_keys,
            "updated_at": updated_at.isoformat(),
        },
    )
    session.commit()

    statistics_result = StatisticsService(session).generate_and_persist(task)
    report_result = TaskReportService(session).generate_and_persist(
        task,
        status_override=task.status.value,
    )

    refreshed_extra_params = dict(task.extra_params or {})
    pipeline_progress = dict(refreshed_extra_params.get("pipeline_progress", {}))
    pipeline_progress.update(
        {
            "current_phase": "completed",
            "analysis_weight_updated_at": updated_at.isoformat(),
            "report_generated_at": report_result.generated_at.isoformat(),
            "hot_topic_count": len(statistics_result.advanced.hot_topics),
        }
    )
    refreshed_extra_params["pipeline_progress"] = pipeline_progress
    task.extra_params = refreshed_extra_params

    create_task_log(
        session,
        task=task,
        stage=TaskStage.REPORT,
        message="Re-generated analysis snapshot and task report after metric weight update.",
        payload={
            "updated_metric_keys": updated_metric_keys,
            "analysis_generated_at": (
                task.extra_params.get("analysis_snapshot", {}) if isinstance(task.extra_params, dict) else {}
            ).get("generated_at"),
            "report_generated_at": report_result.generated_at.isoformat(),
        },
    )
    session.commit()
    return get_task_analysis(session, task.id)


def _merge_updated_metric_weights(
    raw_weight_map: dict[str, dict[str, float]],
    payload: TaskAnalysisWeightsUpdateRequest,
) -> list[str]:
    if not payload.metrics:
        raise ValidationError("至少需要提交一个指标权重配置。")

    updated_metric_keys: list[str] = []
    seen_metric_keys: set[str] = set()
    for metric in payload.metrics:
        metric_key = metric.metric_key.strip()
        if not metric_key:
            raise ValidationError("metric_key 不能为空。")
        if metric_key in seen_metric_keys:
            raise ValidationError(f"指标 {metric_key} 在一次提交中重复出现。")
        seen_metric_keys.add(metric_key)

        spec = get_metric_spec(metric_key)
        if spec is None:
            raise ValidationError(f"不支持的指标权重配置：{metric_key}。")

        provided_weights: dict[str, float] = {}
        seen_component_keys: set[str] = set()
        for component in metric.components:
            component_key = component.key.strip()
            if component_key in seen_component_keys:
                raise ValidationError(
                    f"指标 {metric_key} 的权重分量 {component_key} 重复出现。"
                )
            seen_component_keys.add(component_key)
            provided_weights[component_key] = float(component.weight)

        required_component_keys = {component.key for component in spec.components}
        if set(provided_weights) != required_component_keys:
            expected = "、".join(component.key for component in spec.components)
            raise ValidationError(
                f"指标 {metric_key} 必须完整提交以下分量：{expected}。"
            )

        if sum(provided_weights.values()) <= 0:
            raise ValidationError(f"指标 {metric_key} 的权重和必须大于 0。")

        raw_weight_map[metric_key] = provided_weights
        updated_metric_keys.append(metric_key)

    return updated_metric_keys
