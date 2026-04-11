from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import _backend_bootstrap  # noqa: F401

from app.core.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Delete rotated log files older than the configured retention window."
        ),
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Override the log directory. Defaults to LOG_DIR from settings.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=7,
        help="Delete files older than this many days.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print files that would be removed.",
    )
    args = parser.parse_args()

    settings = get_settings()
    log_dir = Path(args.log_dir or settings.log_dir).expanduser().resolve()
    active_log_path = log_dir / "app.log"
    threshold = datetime.now() - timedelta(days=args.retention_days)

    if not log_dir.exists():
        print(f"Log directory does not exist: {log_dir}")
        return 0

    removed_count = 0
    for path in sorted(log_dir.glob("*.log*")):
        if path.resolve() == active_log_path.resolve():
            continue

        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at >= threshold:
            continue

        print(f"{'Would remove' if args.dry_run else 'Removing'} {path}")
        if not args.dry_run:
            path.unlink(missing_ok=True)
        removed_count += 1

    print(f"Processed {removed_count} log files in {log_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
