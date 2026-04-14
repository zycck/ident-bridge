import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, TypedDict

from app.core import dpapi


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SqlInstance:
    name: str      # e.g. "PZSQLSERVER"
    host: str      # e.g. "localhost"
    display: str   # e.g. "localhost\\PZSQLSERVER"


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


class AppConfig(TypedDict, total=False):
    sql_instance:      str
    sql_database:      str
    sql_user:          str   # stored DPAPI-encrypted as base64
    sql_password:      str   # stored DPAPI-encrypted as base64
    webhook_url:       str
    tg_token:          str   # stored DPAPI-encrypted as base64
    tg_chat_id:        str
    schedule_enabled:  bool
    schedule_mode:     Literal["daily", "hourly", "cron"]
    schedule_value:    str   # "14:30" | "4" | "0 14 * * *"
    github_repo:       str   # "zycck/ident-bridge"
    auto_update_check: bool
    run_on_startup:    bool


class IExporter(Protocol):
    def push(self, data: QueryResult) -> None: ...


class INotifier(Protocol):
    def notify(self, message: str) -> None: ...


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

CONFIG_DIR  = Path(os.environ["APPDATA"]) / "iDentSync"
CONFIG_PATH = CONFIG_DIR / "config.json"
ENCRYPTED_KEYS: frozenset[str] = frozenset({"sql_user", "sql_password", "tg_token"})


class ConfigManager:
    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._cfg: AppConfig = {}
        if CONFIG_PATH.exists():
            self._cfg = self.load()

    def load(self) -> AppConfig:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data: dict = json.load(fh)

        for key in ENCRYPTED_KEYS:
            if key in data:
                encrypted_bytes = base64.b64decode(data[key])
                data[key] = dpapi.decrypt(encrypted_bytes)

        self._cfg = AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__optional_keys__})  # type: ignore[attr-defined]
        return self._cfg

    def save(self, cfg: AppConfig) -> None:
        # Work on a shallow copy so the caller's dict is untouched
        out: dict = dict(cfg)

        for key in ENCRYPTED_KEYS:
            if key in out:
                encrypted_bytes = dpapi.encrypt(out[key])
                out[key] = base64.b64encode(encrypted_bytes).decode("ascii")

        with CONFIG_PATH.open("w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)

        # Restrict file permissions (best-effort on Windows; meaningful on POSIX)
        os.chmod(CONFIG_PATH, 0o600)

    def get(self, key: str) -> str | None:
        return self._cfg.get(key)  # type: ignore[return-value]

    def set(self, key: str, value: str) -> None:
        self._cfg[key] = value  # type: ignore[literal-required]
        # Caller must invoke save() explicitly
