from __future__ import annotations

import argparse
from pathlib import Path

import _backend_bootstrap  # noqa: F401

from app.db.session import get_session_factory
from app.services.task_export_service import TaskExportService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export task datasets without calling the HTTP API.",
    )
    parser.add_argument("--task-id", required=True, help="Task ID to export.")
    parser.add_argument(
        "--dataset",
        choices=("videos", "topics", "summaries"),
        required=True,
        help="Dataset to export.",
    )
    parser.add_argument(
        "--format",
        dest="export_format",
        choices=("json", "csv", "excel"),
        default="json",
        help="Export format.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Target output file path.",
    )
    parser.add_argument("--sort-by", default="composite_score")
    parser.add_argument("--sort-order", default="desc")
    parser.add_argument("--topic", default=None)
    args = parser.parse_args()

    session_factory = get_session_factory()
    with session_factory() as session:
        artifact = TaskExportService(session).export_dataset(
            args.task_id,
            dataset=args.dataset,
            export_format=args.export_format,
            sort_by=args.sort_by,
            sort_order=args.sort_order,
            topic=args.topic,
        )

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(artifact.content)
    print(f"Exported {args.dataset} to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
