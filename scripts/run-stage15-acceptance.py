from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import _backend_bootstrap  # noqa: F401

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.task_acceptance_service import TaskAcceptanceService

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


@dataclass(slots=True)
class CommandResult:
    name: str
    ok: bool
    command: list[str]
    cwd: str
    returncode: int
    stdout_tail: str
    stderr_tail: str


def run_command(name: str, command: list[str], *, cwd: Path) -> CommandResult:
    resolved_command = list(command)
    if os.name == "nt" and resolved_command[0].lower() == "npm":
        resolved_command[0] = "npm.cmd"

    try:
        completed = subprocess.run(
            resolved_command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            name=name,
            ok=False,
            command=resolved_command,
            cwd=str(cwd),
            returncode=127,
            stdout_tail="",
            stderr_tail=str(exc),
        )
    return CommandResult(
        name=name,
        ok=completed.returncode == 0,
        command=resolved_command,
        cwd=str(cwd),
        returncode=completed.returncode,
        stdout_tail=_tail_text(completed.stdout),
        stderr_tail=_tail_text(completed.stderr),
    )


def _tail_text(value: str, *, max_lines: int = 40) -> str:
    lines = value.strip().splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[-max_lines:])


def build_config_checks() -> list[dict[str, Any]]:
    settings = get_settings()
    return [
        {
            "code": "crawler-rate-limit",
            "status": (
                "pass" if settings.crawler_rate_limit_per_minute > 0 else "fail"
            ),
            "message": (
                "Crawler rate limit is configured."
                if settings.crawler_rate_limit_per_minute > 0
                else "Crawler rate limit must be greater than zero."
            ),
            "actual": settings.crawler_rate_limit_per_minute,
        },
        {
            "code": "crawler-sleep-window",
            "status": (
                "pass"
                if settings.crawler_min_sleep <= settings.crawler_max_sleep
                else "fail"
            ),
            "message": (
                "Crawler sleep window is valid."
                if settings.crawler_min_sleep <= settings.crawler_max_sleep
                else "Crawler min sleep cannot exceed max sleep."
            ),
            "actual": {
                "min": settings.crawler_min_sleep,
                "max": settings.crawler_max_sleep,
            },
        },
        {
            "code": "monitoring-enabled",
            "status": "pass" if settings.monitoring_enabled else "warn",
            "message": (
                "Monitoring is enabled."
                if settings.monitoring_enabled
                else "Monitoring is disabled; production should enable it."
            ),
            "actual": settings.monitoring_enabled,
        },
        {
            "code": "worker-concurrency-guard",
            "status": (
                "pass" if settings.worker_global_task_concurrency > 0 else "fail"
            ),
            "message": (
                "Global task concurrency guard is enabled."
                if settings.worker_global_task_concurrency > 0
                else "Global task concurrency must be greater than zero."
            ),
            "actual": settings.worker_global_task_concurrency,
        },
    ]


def overall_status(
    command_results: list[CommandResult],
    config_checks: list[dict[str, Any]],
    task_report: dict[str, Any] | None,
) -> str:
    if any(not result.ok for result in command_results):
        return "fail"
    if any(check["status"] == "fail" for check in config_checks):
        return "fail"
    if task_report and task_report["overall_status"] == "fail":
        return "fail"
    if any(check["status"] == "warn" for check in config_checks):
        return "warn"
    if task_report and task_report["overall_status"] == "warn":
        return "warn"
    return "pass"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run stage 15 acceptance checks and output a report.",
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="Optional task ID for task-level acceptance validation.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output file path (.json or .md).",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument(
        "--skip-backend",
        action="store_true",
        help="Skip backend lint and test checks.",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend lint, test, and build checks.",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip docker compose config validation.",
    )
    args = parser.parse_args()

    python_executable = Path(sys.executable)
    command_results: list[CommandResult] = []

    if not args.skip_backend:
        command_results.append(
            run_command(
                "backend-ruff",
                [
                    str(python_executable),
                    "-m",
                    "ruff",
                    "check",
                    "app",
                    "tests",
                    "..\\scripts",
                ],
                cwd=BACKEND_DIR,
            )
        )
        command_results.append(
            run_command(
                "backend-pytest",
                [str(python_executable), "-m", "pytest", "-q"],
                cwd=BACKEND_DIR,
            )
        )

    if not args.skip_frontend:
        command_results.append(
            run_command(
                "frontend-lint",
                ["npm", "run", "lint"],
                cwd=FRONTEND_DIR,
            )
        )
        command_results.append(
            run_command(
                "frontend-test",
                ["npm", "run", "test"],
                cwd=FRONTEND_DIR,
            )
        )
        command_results.append(
            run_command(
                "frontend-build",
                ["npm", "run", "build"],
                cwd=FRONTEND_DIR,
            )
        )

    if not args.skip_docker:
        command_results.append(
            run_command(
                "docker-compose-config",
                ["docker", "compose", "-f", "docker-compose.prod.yml", "config"],
                cwd=ROOT_DIR,
            )
        )

    config_checks = build_config_checks()
    task_report: dict[str, Any] | None = None
    if args.task_id:
        session_factory = get_session_factory()
        with session_factory() as session:
            task_report = (
                TaskAcceptanceService(session)
                .build_report(args.task_id)
                .to_dict()
            )

    report = {
        "overall_status": overall_status(
            command_results,
            config_checks,
            task_report,
        ),
        "commands": [asdict(item) for item in command_results],
        "config_checks": config_checks,
        "task_report": task_report,
    }

    output_text = (
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.format == "json"
        else render_markdown(report)
    )
    print(output_text)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8")

    return 0 if report["overall_status"] != "fail" else 1


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Stage 15 Acceptance Report",
        "",
        f"- Overall status: `{report['overall_status']}`",
        "",
        "## Command Checks",
    ]

    for item in report["commands"]:
        command_text = " ".join(item["command"])
        lines.append(
            f"- `{item['name']}`: {'PASS' if item['ok'] else 'FAIL'} "
            f"(`{item['cwd']}`)"
        )
        lines.append(f"- Command: `{command_text}`")

    lines.extend(["", "## Config Checks"])
    for check in report["config_checks"]:
        lines.append(
            f"- `{check['code']}`: `{check['status']}` - {check['message']}"
        )

    if report["task_report"]:
        task_report = report["task_report"]
        lines.extend(["", "## Task Report"])
        lines.append(f"- Task ID: `{task_report['task_id']}`")
        lines.append(f"- Task status: `{task_report['task_status']}`")
        lines.append(f"- Task acceptance: `{task_report['overall_status']}`")
        for section_name, checks in task_report["sections"].items():
            lines.extend(["", f"### {section_name.title()}"])
            for check in checks:
                lines.append(
                    f"- `{check['code']}`: `{check['status']}` - "
                    f"{check['message']}"
                )

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
