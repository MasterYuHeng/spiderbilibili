from __future__ import annotations

import argparse
import json

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check backend health and optionally print a short metrics summary."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8014/api",
        help="Backend API base URL.",
    )
    parser.add_argument(
        "--include-metrics",
        action="store_true",
        help="Also fetch /metrics and print selected lines.",
    )
    args = parser.parse_args()

    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{args.base_url.rstrip('/')}/health")
        payload = response.json()

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        exit_code = 0 if response.is_success else 1

        if args.include_metrics:
            metrics_response = client.get(f"{args.base_url.rstrip('/')}/metrics")
            metrics_response.raise_for_status()
            interesting_lines = [
                line
                for line in metrics_response.text.splitlines()
                if line.startswith("spiderbilibili_component_health_status")
                or line.startswith("spiderbilibili_runtime_health")
                or line.startswith("spiderbilibili_celery_queue_depth")
            ]
            print()
            print("\n".join(interesting_lines))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
