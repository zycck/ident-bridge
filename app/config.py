# -*- coding: utf-8 -*-
"""Central configuration + shared dataclasses + TypedDicts for iDentBridge."""

import base64
import json
import logging
import os
import threading
import tempfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TypedDict

from app.core import dpapi
from app.core.constants import CONFIG_DIR_NAME


# ---------------------------------------------------------------------------
# Shared dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SqlInstance:
    name: str
    host: str
    display: str


@dataclass(slots=True)
class QueryResult:
    columns: list[str]
    rows:    list[tuple]
    count:   int
    duration_ms: int


@dataclass(slots=True)
class SyncResult:
    success:     bool
    rows_synced: int
    error:       str | None
    timestamp:   datetime


# ---------------------------------------------------------------------------
# TypedDicts
# ---------------------------------------------------------------------------

class ExportHistoryEntry(TypedDict, total=False):
    """Single run record stored inside ExportJob.history."""
    ts:      str   # "YYYY-MM-DD HH:MM"
    rows:    int
    trigger: str   # "manual" | "scheduled" | "test"
    ok:      bool
    err:     str


class TriggerType(str, Enum):
    """How an export run was initiated."""
    MANUAL    = "manual"
    SCHEDULED = "scheduled"   # was "auto" in older configs — migrated on read
    TEST      = "test"        # dry-run via TestRunDialog


class ExportJob(TypedDict, total=False):
    """Configuration for a single named export job."""
    id:               str
    name:             str
    sql_query:        str
    webhook_url:      str
    schedule_enabled: bool
    schedule_mode:    str   # "daily" | "hourly"
    schedule_value:   str   # "14:30" | "4"
    history:          list[ExportHistoryEntry]


class AppConfig(TypedDict, total=False):
    sql_instance:      str
    sql_database:      str
    sql_user:          str   # stored DPAPI-encrypted as base64
    sql_password:      str   # stored DPAPI-encrypted as base64
    sql_trust_cert:    bool  # accept self-signed server certs
    github_repo:       str
    auto_update_check: bool
    run_on_startup:    bool
    export_jobs:       list[ExportJob]
    tray_notice_shown: bool  # shown once when app first minimises to tray


_APP_CONFIG_KEYS = frozenset({
    "sql_instance",
    "sql_database",
    "sql_user",
    "sql_password",
    "sql_trust_cert",
    "github_repo",
    "auto_update_check",
    "run_on_startup",
    "export_jobs",
    "tray_notice_shown",
})


def _default_config_dir() -> Path:
    """Return the platform-appropriate config directory.

    Windows keeps the existing %APPDATA% layout. On other platforms we
    prefer XDG_CONFIG_HOME when available and otherwise fall back to
    ~/.config so the module remains import-safe outside Windows.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / CONFIG_DIR_NAME

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / CONFIG_DIR_NAME

    return Path.home() / ".config" / CONFIG_DIR_NAME


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

CONFIG_DIR  = _default_config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"
ENCRYPTED_KEYS: frozenset[str] = frozenset({"sql_user", "sql_password"})


class ConfigManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._cfg: AppConfig = {}
        if CONFIG_PATH.exists():
            self._cfg = self.load()

    def load(self) -> AppConfig:
        with self._lock:
            if not CONFIG_PATH.exists():
                return self._cfg
            try:
                with CONFIG_PATH.open("r", encoding="utf-8") as fh:
                    data: dict = json.load(fh)
            except json.JSONDecodeError:
                logging.getLogger(__name__).warning(
                    "config.json повреждён, используются последние известные настройки"
                )
                return self._cfg

            for key in ENCRYPTED_KEYS:
                raw = data.get(key)
                if not raw:
                    # Field missing or empty — normal for Trusted Connection mode
                    # (Windows authentication on a local SQL Server), no warning.
                    continue
                try:
                    encrypted_bytes = base64.b64decode(raw)
                    data[key] = dpapi.decrypt(encrypted_bytes)
                except Exception:
                    # Real corruption: blob present but unreadable (e.g. DPAPI
                    # master key changed because the user moved profiles).
                    logging.getLogger(__name__).warning(
                        "Не удалось расшифровать поле '%s' — требуется повторный ввод", key
                    )
                    data[key] = ""

            # Backward-compat migration: trigger "auto" → "scheduled"
            for job in data.get("export_jobs") or []:
                for entry in job.get("history") or []:
                    if entry.get("trigger") == "auto":
                        entry["trigger"] = "scheduled"

            self._cfg = AppConfig(
                **{k: v for k, v in data.items() if k in _APP_CONFIG_KEYS}
            )  # type: ignore[typeddict-item]
            return self._cfg

    def save(self, cfg: AppConfig) -> None:
        with self._lock:
            self._cfg = AppConfig(
                **{k: v for k, v in dict(cfg).items() if k in _APP_CONFIG_KEYS}
            )  # type: ignore[typeddict-item]
            out: dict = dict(cfg)
            for key in ENCRYPTED_KEYS:
                if key in out and out[key]:
                    encrypted_bytes = dpapi.encrypt(out[key])
                    out[key] = base64.b64encode(encrypted_bytes).decode("ascii")

            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=CONFIG_DIR,
                    delete=False,
                ) as fh:
                    tmp_path = Path(fh.name)
                    json.dump(out, fh, indent=2, ensure_ascii=False)
                    fh.flush()
                    os.fsync(fh.fileno())

                os.replace(tmp_path, CONFIG_PATH)
            finally:
                if tmp_path is not None and tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except FileNotFoundError:
                        pass

            try:
                os.chmod(CONFIG_PATH, 0o600)
            except OSError:
                # Permission bits are advisory outside POSIX filesystems.
                pass

    def update(self, **changes: object) -> None:
        """Atomic load → merge → save. Preserves keys not in changes."""
        with self._lock:
            cfg = self.load()
            cfg.update(changes)  # type: ignore[typeddict-item]
            self.save(cfg)

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._cfg.get(key)  # type: ignore[return-value]

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._cfg[key] = value  # type: ignore[literal-required]
