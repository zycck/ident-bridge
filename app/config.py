"""Central configuration + shared dataclasses + TypedDicts for iDentBridge."""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from collections.abc import Iterator
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
    duration_us: int = 0
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.duration_us <= 0:
            self.duration_us = max(0, int(self.duration_ms)) * 1000
        self.duration_ms = max(0, int(self.duration_us // 1000))


@dataclass(slots=True)
class SyncResult:
    success:     bool
    rows_synced: int
    error:       str | None
    timestamp:   datetime
    duration_us: int = 0
    sql_duration_us: int = 0

    def __post_init__(self) -> None:
        self.duration_us = max(0, int(self.duration_us))
        self.sql_duration_us = max(0, int(self.sql_duration_us))


class GasOptions(TypedDict, total=False):
    sheet_name: str
    header_row: int
    dedupe_key_columns: list[str]
    auth_token: str


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
    duration_us: int
    sql_duration_us: int


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
    gas_options:      GasOptions
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
        # Batch mode: update() mutates in-memory only while depth > 0, and
        # one save() fires at the outermost __exit__. Avoids a tempfile +
        # fsync + os.replace cycle per keystroke when a settings form
        # autosaves many fields at once.
        self._batch_depth: int = 0
        self._batch_dirty: bool = False
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
                gas_options = job.get("gas_options")
                if isinstance(gas_options, dict):
                    header_row = gas_options.get("header_row", 1)
                    try:
                        gas_options["header_row"] = max(1, int(header_row))
                    except (TypeError, ValueError):
                        gas_options["header_row"] = 1
                    dedupe_columns = gas_options.get("dedupe_key_columns") or []
                    gas_options["dedupe_key_columns"] = [
                        str(column).strip()
                        for column in dedupe_columns
                        if str(column).strip()
                    ]
                    gas_options["auth_token"] = str(gas_options.get("auth_token", "") or "").strip()
                for entry in job.get("history") or []:
                    if entry.get("trigger") == "auto":
                        entry["trigger"] = "scheduled"
                    if "duration_us" not in entry and "duration_ms" in entry:
                        try:
                            entry["duration_us"] = max(0, int(entry["duration_ms"])) * 1000
                        except (TypeError, ValueError):
                            entry["duration_us"] = 0
                    if "sql_duration_us" not in entry and "sql_duration_ms" in entry:
                        try:
                            entry["sql_duration_us"] = max(0, int(entry["sql_duration_ms"])) * 1000
                        except (TypeError, ValueError):
                            entry["sql_duration_us"] = 0

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
            tmp_replaced = False
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
                tmp_replaced = True
            finally:
                # After a successful os.replace, tmp_path was atomically
                # renamed — there's nothing to unlink. Only attempt cleanup
                # on the failure path where the tempfile may still be
                # sitting alongside the real config.
                if not tmp_replaced and tmp_path is not None and tmp_path.exists():
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
        """Merge ``changes`` into the config.

        Outside of :meth:`batch`: atomic load → merge → save, preserving
        keys not in ``changes`` (same semantics as before).

        Inside :meth:`batch`: mutates the in-memory config only and marks
        the batch dirty; one :meth:`save` fires on batch exit.
        """
        with self._lock:
            if self._batch_depth > 0:
                self._cfg.update(changes)  # type: ignore[typeddict-item]
                self._batch_dirty = True
                return
            cfg = self.load()
            cfg.update(changes)  # type: ignore[typeddict-item]
            self.save(cfg)

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Coalesce multiple :meth:`update` calls into one disk write.

        Usage::

            with config.batch():
                config.update(sql_instance=inst)
                config.update(sql_database=db)
                config.update(sql_user=user)
            # one fsync + os.replace here

        Nested batches are allowed; only the outermost exit flushes.
        If nothing was changed inside the batch, no write happens.
        """
        with self._lock:
            self._batch_depth += 1
        try:
            yield
        finally:
            with self._lock:
                self._batch_depth -= 1
                if self._batch_depth == 0 and self._batch_dirty:
                    self._batch_dirty = False
                    self.save(self._cfg)

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._cfg.get(key)  # type: ignore[return-value]

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._cfg[key] = value  # type: ignore[literal-required]
