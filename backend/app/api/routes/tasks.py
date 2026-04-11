from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.enums import TaskStatus
from app.schemas.common import ApiResponse
from app.schemas.task import (
    TaskAcceptanceCheckRead,
    TaskAcceptancePayload,
    TaskAcceptanceSectionRead,
    TaskAnalysisPayload,
    TaskBulkDeletePayload,
    TaskCreatePayload,
    TaskCreateRequest,
    TaskDeletePayload,
    TaskDetail,
    TaskListPayload,
    TaskProgressPayload,
    TaskReportPayload,
    TaskRestorePayload,
    TaskTopicListPayload,
    TaskVideoListPayload,
)
from app.services.task_acceptance_service import TaskAcceptanceService
from app.services.task_export_service import TaskExportService
from app.services.task_report_service import TaskReportService
from app.services.task_result_service import (
    TaskVideoMetricFilters,
    get_task_analysis,
    get_task_topics,
    list_task_videos,
)
from app.services.task_service import (
    cancel_crawl_task,
    create_crawl_task,
    delete_all_crawl_tasks,
    delete_crawl_task,
    empty_task_trash,
    get_task_detail_with_logs,
    get_task_progress,
    list_crawl_tasks,
    permanently_delete_crawl_task,
    pause_crawl_task,
    restore_crawl_task,
    resume_crawl_task,
    retry_crawl_task,
)
from app.utils.responses import success_response

router = APIRouter(prefix="/tasks")
DbSession = Annotated[Session, Depends(get_db_session)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int | None, Query(ge=1)]
LogLimit = Annotated[int | None, Query(ge=1, le=1000)]
TaskStatusQuery = Annotated[TaskStatus | None, Query(alias="status")]
VideoSortBy = Annotated[
    Literal[
        "composite_score",
        "heat_score",
        "relevance_score",
        "published_at",
        "view_count",
        "like_count",
        "coin_count",
        "favorite_count",
        "share_count",
        "reply_count",
        "danmaku_count",
        "like_view_ratio",
    ],
    Query(),
]
SortOrder = Annotated[Literal["desc", "asc"], Query()]
TopicQuery = Annotated[str | None, Query(min_length=1)]
ExportDataset = Annotated[Literal["videos", "topics", "summaries"], Query()]
ExportFormat = Annotated[Literal["json", "csv", "excel"], Query(alias="format")]
MetricIntQuery = Annotated[int | None, Query(ge=0)]
MetricFloatQuery = Annotated[float | None, Query(ge=0)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TaskCreatePayload],
    summary="Create crawl task",
)
def create_task(
    payload: TaskCreateRequest,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskCreatePayload]:
    task, dispatch = create_crawl_task(session, payload)
    request_id = getattr(request.state, "request_id", None)
    return success_response(
        TaskCreatePayload(task=task, dispatch=dispatch),
        status_code=status.HTTP_201_CREATED,
        request_id=request_id,
    )


@router.post(
    "/{task_id}/retry",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TaskCreatePayload],
    summary="Retry crawl task",
)
def retry_task(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskCreatePayload]:
    task, dispatch = retry_crawl_task(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(
        TaskCreatePayload(task=task, dispatch=dispatch),
        status_code=status.HTTP_201_CREATED,
        request_id=request_id,
    )


@router.post(
    "/{task_id}/pause",
    response_model=ApiResponse[TaskDetail],
    summary="Pause crawl task",
)
def pause_task(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskDetail]:
    payload = pause_crawl_task(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.post(
    "/{task_id}/resume",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TaskCreatePayload],
    summary="Resume paused crawl task",
)
def resume_task(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskCreatePayload]:
    task, dispatch = resume_crawl_task(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(
        TaskCreatePayload(task=task, dispatch=dispatch),
        status_code=status.HTTP_201_CREATED,
        request_id=request_id,
    )


@router.post(
    "/{task_id}/cancel",
    response_model=ApiResponse[TaskDetail],
    summary="Cancel crawl task",
)
def cancel_task(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskDetail]:
    payload = cancel_crawl_task(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.delete(
    "",
    response_model=ApiResponse[TaskBulkDeletePayload],
    summary="Move all deletable crawl tasks to trash",
)
def delete_all_tasks(
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskBulkDeletePayload]:
    payload = delete_all_crawl_tasks(session)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "",
    response_model=ApiResponse[TaskListPayload],
    summary="List crawl tasks",
)
def list_tasks(
    request: Request,
    session: DbSession,
    page: PageNumber = 1,
    page_size: PageSize = None,
    task_status: TaskStatusQuery = None,
) -> ApiResponse[TaskListPayload]:
    payload = list_crawl_tasks(
        session,
        page=page,
        page_size=page_size,
        status=task_status,
    )
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/trash",
    response_model=ApiResponse[TaskListPayload],
    summary="List trashed crawl tasks",
)
def list_trashed_tasks(
    request: Request,
    session: DbSession,
    page: PageNumber = 1,
    page_size: PageSize = None,
    task_status: TaskStatusQuery = None,
) -> ApiResponse[TaskListPayload]:
    payload = list_crawl_tasks(
        session,
        page=page,
        page_size=page_size,
        status=task_status,
        deleted_only=True,
    )
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.post(
    "/{task_id}/restore",
    response_model=ApiResponse[TaskRestorePayload],
    summary="Restore crawl task from trash",
)
def restore_task(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskRestorePayload]:
    payload = restore_crawl_task(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.delete(
    "/{task_id}/permanent",
    response_model=ApiResponse[TaskDeletePayload],
    summary="Permanently delete a trashed crawl task",
)
def permanently_delete_task(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskDeletePayload]:
    payload = permanently_delete_crawl_task(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.delete(
    "/trash",
    response_model=ApiResponse[TaskBulkDeletePayload],
    summary="Permanently delete all trashed crawl tasks",
)
def empty_trash(
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskBulkDeletePayload]:
    payload = empty_task_trash(session)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.delete(
    "/{task_id}",
    response_model=ApiResponse[TaskDeletePayload],
    summary="Delete crawl task",
)
def delete_task(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskDeletePayload]:
    payload = delete_crawl_task(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/{task_id}",
    response_model=ApiResponse[TaskDetail],
    summary="Get crawl task detail",
)
def get_task(
    task_id: str,
    request: Request,
    session: DbSession,
    log_limit: LogLimit = None,
) -> ApiResponse[TaskDetail]:
    payload = get_task_detail_with_logs(session, task_id, log_limit=log_limit)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/{task_id}/progress",
    response_model=ApiResponse[TaskProgressPayload],
    summary="Get crawl task progress",
)
def get_task_progress_endpoint(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskProgressPayload]:
    payload = get_task_progress(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/{task_id}/acceptance",
    response_model=ApiResponse[TaskAcceptancePayload],
    summary="Get task stage 15 acceptance report",
)
def get_task_acceptance_endpoint(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskAcceptancePayload]:
    report = TaskAcceptanceService(session).build_report(task_id)
    payload = TaskAcceptancePayload(
        task_id=report.task_id,
        task_status=report.task_status,
        overall_status=report.overall_status,
        sections=[
            TaskAcceptanceSectionRead(
                name=name,
                checks=[
                    TaskAcceptanceCheckRead.model_validate(asdict(check))
                    for check in checks
                ],
            )
            for name, checks in report.sections.items()
        ],
    )
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/{task_id}/report",
    response_model=ApiResponse[TaskReportPayload],
    summary="Get task hotspot analysis report",
)
def get_task_report_endpoint(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskReportPayload]:
    payload = TaskReportService(session).build_report(task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/{task_id}/videos",
    response_model=ApiResponse[TaskVideoListPayload],
    summary="List crawl task videos",
)
def get_task_videos_endpoint(
    task_id: str,
    request: Request,
    session: DbSession,
    page: PageNumber = 1,
    page_size: PageSize = None,
    sort_by: VideoSortBy = "composite_score",
    sort_order: SortOrder = "desc",
    topic: TopicQuery = None,
    min_view_count: MetricIntQuery = None,
    max_view_count: MetricIntQuery = None,
    min_like_count: MetricIntQuery = None,
    max_like_count: MetricIntQuery = None,
    min_coin_count: MetricIntQuery = None,
    max_coin_count: MetricIntQuery = None,
    min_favorite_count: MetricIntQuery = None,
    max_favorite_count: MetricIntQuery = None,
    min_share_count: MetricIntQuery = None,
    max_share_count: MetricIntQuery = None,
    min_reply_count: MetricIntQuery = None,
    max_reply_count: MetricIntQuery = None,
    min_danmaku_count: MetricIntQuery = None,
    max_danmaku_count: MetricIntQuery = None,
    min_relevance_score: MetricFloatQuery = None,
    max_relevance_score: MetricFloatQuery = None,
    min_heat_score: MetricFloatQuery = None,
    max_heat_score: MetricFloatQuery = None,
    min_composite_score: MetricFloatQuery = None,
    max_composite_score: MetricFloatQuery = None,
    min_like_view_ratio: MetricFloatQuery = None,
    max_like_view_ratio: MetricFloatQuery = None,
) -> ApiResponse[TaskVideoListPayload]:
    payload = list_task_videos(
        session,
        task_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        topic=topic,
        filters=TaskVideoMetricFilters(
            min_view_count=min_view_count,
            max_view_count=max_view_count,
            min_like_count=min_like_count,
            max_like_count=max_like_count,
            min_coin_count=min_coin_count,
            max_coin_count=max_coin_count,
            min_favorite_count=min_favorite_count,
            max_favorite_count=max_favorite_count,
            min_share_count=min_share_count,
            max_share_count=max_share_count,
            min_reply_count=min_reply_count,
            max_reply_count=max_reply_count,
            min_danmaku_count=min_danmaku_count,
            max_danmaku_count=max_danmaku_count,
            min_relevance_score=min_relevance_score,
            max_relevance_score=max_relevance_score,
            min_heat_score=min_heat_score,
            max_heat_score=max_heat_score,
            min_composite_score=min_composite_score,
            max_composite_score=max_composite_score,
            min_like_view_ratio=min_like_view_ratio,
            max_like_view_ratio=max_like_view_ratio,
        ),
    )
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/{task_id}/topics",
    response_model=ApiResponse[TaskTopicListPayload],
    summary="List crawl task topics",
)
def get_task_topics_endpoint(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskTopicListPayload]:
    payload = get_task_topics(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/{task_id}/analysis",
    response_model=ApiResponse[TaskAnalysisPayload],
    summary="Get crawl task analysis",
)
def get_task_analysis_endpoint(
    task_id: str,
    request: Request,
    session: DbSession,
) -> ApiResponse[TaskAnalysisPayload]:
    payload = get_task_analysis(session, task_id)
    request_id = getattr(request.state, "request_id", None)
    return success_response(payload, request_id=request_id)


@router.get(
    "/{task_id}/export",
    summary="Export crawl task results",
)
def export_task_results_endpoint(
    task_id: str,
    request: Request,
    session: DbSession,
    dataset: ExportDataset = "videos",
    export_format: ExportFormat = "json",
    sort_by: VideoSortBy = "composite_score",
    sort_order: SortOrder = "desc",
    topic: TopicQuery = None,
    min_view_count: MetricIntQuery = None,
    max_view_count: MetricIntQuery = None,
    min_like_count: MetricIntQuery = None,
    max_like_count: MetricIntQuery = None,
    min_coin_count: MetricIntQuery = None,
    max_coin_count: MetricIntQuery = None,
    min_favorite_count: MetricIntQuery = None,
    max_favorite_count: MetricIntQuery = None,
    min_share_count: MetricIntQuery = None,
    max_share_count: MetricIntQuery = None,
    min_reply_count: MetricIntQuery = None,
    max_reply_count: MetricIntQuery = None,
    min_danmaku_count: MetricIntQuery = None,
    max_danmaku_count: MetricIntQuery = None,
    min_relevance_score: MetricFloatQuery = None,
    max_relevance_score: MetricFloatQuery = None,
    min_heat_score: MetricFloatQuery = None,
    max_heat_score: MetricFloatQuery = None,
    min_composite_score: MetricFloatQuery = None,
    max_composite_score: MetricFloatQuery = None,
    min_like_view_ratio: MetricFloatQuery = None,
    max_like_view_ratio: MetricFloatQuery = None,
) -> Response:
    artifact = TaskExportService(session).export_dataset(
        task_id,
        dataset=dataset,
        export_format=export_format,
        sort_by=sort_by,
        sort_order=sort_order,
        topic=topic,
        filters=TaskVideoMetricFilters(
            min_view_count=min_view_count,
            max_view_count=max_view_count,
            min_like_count=min_like_count,
            max_like_count=max_like_count,
            min_coin_count=min_coin_count,
            max_coin_count=max_coin_count,
            min_favorite_count=min_favorite_count,
            max_favorite_count=max_favorite_count,
            min_share_count=min_share_count,
            max_share_count=max_share_count,
            min_reply_count=min_reply_count,
            max_reply_count=max_reply_count,
            min_danmaku_count=min_danmaku_count,
            max_danmaku_count=max_danmaku_count,
            min_relevance_score=min_relevance_score,
            max_relevance_score=max_relevance_score,
            min_heat_score=min_heat_score,
            max_heat_score=max_heat_score,
            min_composite_score=min_composite_score,
            max_composite_score=max_composite_score,
            min_like_view_ratio=min_like_view_ratio,
            max_like_view_ratio=max_like_view_ratio,
        ),
    )
    request_id = getattr(request.state, "request_id", None)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "X-Request-ID": request_id or "",
        },
    )
