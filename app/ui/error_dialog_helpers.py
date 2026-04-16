"""Helpers for the application error dialog and exception hook."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from app.core.constants import CONFIG_DIR_NAME

LOG_MAX_BYTES = 1_000_000  # rotate errors.log when it exceeds ~1 MB


def _error_log_path() -> Path | None:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    log_dir = Path(appdata) / CONFIG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "errors.log"


def append_error_log(traceback_text: str) -> None:
    """Append a traceback to the rotated error log if APPDATA is available."""
    log_path = _error_log_path()
    if log_path is None:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        if log_path.exists() and log_path.stat().st_size > LOG_MAX_BYTES:
            rotated = log_path.with_suffix(".log.1")
            try:
                if rotated.exists():
                    rotated.unlink()
                log_path.rename(rotated)
            except OSError:
                pass
    except OSError:
        pass

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n[{timestamp}]\n{traceback_text}")
