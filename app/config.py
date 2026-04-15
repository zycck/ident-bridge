# -*- coding: utf-8 -*-
"""Central configuration + shared dataclasses + TypedDicts for iDentBridge."""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TypedDict

from app.core import dpapi


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


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

CONFIG_DIR  = Path(os.environ["APPDATA"]) / "iDentSync"
CONFIG_PATH = CONFIG_DIR / "config.json"
ENCRYPTED_KEYS: frozenset[str] = frozenset({"sql_user", "sql_password"})


class ConfigManager:
    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._cfg: AppConfig = {}
        if CONFIG_PATH.exists():
            self._cfg = self.load()

    def load(self) -> AppConfig:
        if not CONFIG_PATH.exists():
            return self._cfg
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as fh:
                data: dict = json.load(fh)
        except json.JSONDecodeError:
            import logging
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
                import logging
                logging.getLogger(__name__).warning(
                    "Не удалось расшифровать поле '%s' — требуется повторный ввод", key
                )
                data[key] = ""

        # Backward-compat migration: trigger "auto" → "scheduled"
        for job in data.get("export_jobs") or []:
            for entry in job.get("history") or []:
                if entry.get("trigger") == "auto":
                    entry["trigger"] = "scheduled"

        valid_keys = AppConfig.__annotations__.keys()
        self._cfg = AppConfig(**{k: v for k, v in data.items() if k in valid_keys})  # type: ignore[typeddict-item]
        return self._cfg

    def save(self, cfg: AppConfig) -> None:
        out: dict = dict(cfg)
        for key in ENCRYPTED_KEYS:
            if key in out and out[key]:
                encrypted_bytes = dpapi.encrypt(out[key])
                out[key] = base64.b64encode(encrypted_bytes).decode("ascii")

        with CONFIG_PATH.open("w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)

        os.chmod(CONFIG_PATH, 0o600)

    def update(self, **changes: object) -> None:
        """Atomic load → merge → save. Preserves keys not in changes."""
        cfg = self.load()
        cfg.update(changes)  # type: ignore[typeddict-item]
        self.save(cfg)

    def get(self, key: str) -> str | None:
        return self._cfg.get(key)  # type: ignore[return-value]

    def set(self, key: str, value: str) -> None:
        self._cfg[key] = value  # type: ignore[literal-required]
