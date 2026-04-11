from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.configure(extra={"request_id": "-"})
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        enqueue=False,
        backtrace=False,
        diagnose=settings.app_debug,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "| <level>{level: <8}</level> "
            "| <cyan>{extra[request_id]}</cyan> "
            "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "- <level>{message}</level>"
        ),
    )
    logger.add(
        log_dir / "app.log",
        level=settings.log_level.upper(),
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        encoding="utf-8",
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )


def get_logger(name: str, request_id: str | None = None):
    return logger.bind(request_id=request_id or "-", name=name)
