import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, TypedDict

from app.core import dpapi


# ---------------------------------------------------------------------------
# Shared types
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


class ExportJob(TypedDict, total=False):
    """Configuration for a single named export job."""
    id:               str
    name:             str
    sql_query:        str
    webhook_url:      str
    schedule_enabled: bool
    schedule_mode:    str   # "daily" | "hourly"
    schedule_value:   str   # "14:30" | "4"


class AppConfig(TypedDict, total=False):
    sql_instance:      str
    sql_database:      str
    sql_user:          str   # stored DPAPI-encrypted as base64
    sql_password:      str   # stored DPAPI-encrypted as base64
    github_repo:       str
    auto_update_check: bool
    run_on_startup:    bool
    export_jobs:       list  # list[ExportJob]


class IExporter(Protocol):
    def push(self, data: QueryResult) -> None: ...


class INotifier(Protocol):
    def notify(self, message: str) -> None: ...


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
            if key in data:
                try:
                    encrypted_bytes = base64.b64decode(data[key])
                    data[key] = dpapi.decrypt(encrypted_bytes)
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Не удалось расшифровать поле '%s' — требуется повторный ввод", key
                    )
                    data[key] = ""

        valid_keys = AppConfig.__optional_keys__  # type: ignore[attr-defined]
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

    def get(self, key: str) -> str | None:
        return self._cfg.get(key)  # type: ignore[return-value]

    def set(self, key: str, value: str) -> None:
        self._cfg[key] = value  # type: ignore[literal-required]
