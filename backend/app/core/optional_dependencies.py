from __future__ import annotations

import importlib
import subprocess
import sys
import threading
from typing import Any

from app.core.logging import get_logger

OPTIONAL_RUNTIME_REQUIREMENTS = {
    "cryptography": "cryptography==46.0.3",
    "jieba": "jieba==0.42.1",
    "openai": "openai==2.30.0",
    "openpyxl": "openpyxl==3.1.5",
    "playwright": "playwright==1.58.0",
    "prometheus-client": "prometheus-client==0.23.1",
}

_install_lock = threading.Lock()
_logger = get_logger(__name__)


def _is_missing_module_error(exc: ModuleNotFoundError, module_name: str) -> bool:
    top_level_module = module_name.split(".", 1)[0]
    return exc.name in {module_name, top_level_module}


def ensure_optional_dependency(
    distribution_name: str,
    module_name: str | None = None,
) -> Any:
    resolved_module_name = module_name or distribution_name.replace("-", "_")

    try:
        return importlib.import_module(resolved_module_name)
    except ModuleNotFoundError as exc:
        if not _is_missing_module_error(exc, resolved_module_name):
            raise

    requirement = OPTIONAL_RUNTIME_REQUIREMENTS.get(distribution_name)
    if requirement is None:
        raise RuntimeError(
            f"No optional runtime requirement is configured for '{distribution_name}'."
        )

    with _install_lock:
        try:
            return importlib.import_module(resolved_module_name)
        except ModuleNotFoundError as exc:
            if not _is_missing_module_error(exc, resolved_module_name):
                raise

        _logger.info(
            "Optional dependency '{}' is missing, installing it on demand.",
            requirement,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "install", requirement],
            check=True,
        )

    return importlib.import_module(resolved_module_name)
