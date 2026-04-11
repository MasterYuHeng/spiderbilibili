from __future__ import annotations

import argparse
import json

import _backend_bootstrap  # noqa: F401

from app.db.session import get_session_factory
from app.services.task_service import retry_crawl_task


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clone a failed or partial task and enqueue it for retry.",
    )
    parser.add_argument("--task-id", required=True, help="The source task ID to retry.")
    args = parser.parse_args()

    session_factory = get_session_factory()
    with session_factory() as session:
        detail, dispatch = retry_crawl_task(session, args.task_id)

    payload = {
        "retried_from_task_id": args.task_id,
        "new_task_id": detail.id,
        "status": detail.status,
        "celery_task_id": dispatch.celery_task_id,
        "task_name": dispatch.task_name,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
