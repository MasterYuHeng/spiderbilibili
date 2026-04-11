from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    PARTIAL_SUCCESS = "partial_success"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TaskStage(StrEnum):
    TASK = "task"
    SEARCH = "search"
    DETAIL = "detail"
    SUBTITLE = "subtitle"
    TEXT = "text"
    AI = "ai"
    TOPIC = "topic"
    AUTHOR = "author"
    REPORT = "report"
    EXPORT = "export"


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_cls]
