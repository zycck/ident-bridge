"""SQLite-backed runtime journal for export runs and chunk progress."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import app.config as config_module
from app.config import ConfigManager, ExportHistoryEntry, TriggerType
from app.ui.export_jobs.editor.runtime import normalize_short_user_error

_HISTORY_LIMIT = 100


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_history_timestamp(value: str | None) -> str:
    parsed = _from_iso(value)
    if parsed is None:
        return ""
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_trigger(value: object) -> str:
    try:
        return TriggerType(str(value or "").strip() or TriggerType.MANUAL.value).value
    except ValueError:
        return TriggerType.MANUAL.value


@dataclass(frozen=True, slots=True)
class ExportRunInfo:
    run_id: str
    job_id: str
    job_name: str
    webhook_url: str
    sheet_name: str
    source_id: str
    write_mode: str
    export_date: str
    total_chunks: int
    total_rows: int
    delivered_chunks: int
    delivered_rows: int
    status: str
    trigger: str
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    last_error: str
    sql_duration_us: int
    total_duration_us: int
    supersedes_run_id: str | None


class ExportRunStore:
    """Persist export runs and chunk progress in local SQLite."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else (config_module.CONFIG_DIR / "runtime.sqlite3")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def migrate_legacy_history(self, config: ConfigManager) -> bool:
        cfg = config.load()
        jobs = list(cfg.get("export_jobs") or [])
        if not jobs:
            return False

        imported_any = False
        normalized_jobs: list[dict[str, Any]] = []
        with self._connect() as conn:
            for raw_job in jobs:
                job = dict(raw_job)
                job_id = str(job.get("id") or "").strip()
                job_name = str(job.get("name") or "").strip()
                history = list(job.get("history") or [])
                if job_id and history:
                    for index, entry in enumerate(history):
                        ts = str(entry.get("ts", "") or "").strip()
                        run_id = self._legacy_run_id(job_id, index, entry)
                        created_at = self._history_timestamp_to_iso(ts) or _to_iso(_now_utc()) or ""
                        delivered_rows = max(0, int(entry.get("rows") or 0))
                        ok = bool(entry.get("ok"))
                        trigger = _normalize_trigger(entry.get("trigger"))
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO export_runs (
                                run_id,
                                job_id,
                                job_name,
                                webhook_url,
                                sheet_name,
                                source_id,
                                write_mode,
                                export_date,
                                total_chunks,
                                total_rows,
                                delivered_chunks,
                                delivered_rows,
                                status,
                                trigger,
                                created_at,
                                started_at,
                                finished_at,
                                updated_at,
                                last_error,
                                sql_duration_us,
                                total_duration_us,
                                supersedes_run_id
                            ) VALUES (?, ?, ?, '', '', ?, '', '', 1, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                            """,
                            (
                                run_id,
                                job_id,
                                job_name,
                                job_id,
                                delivered_rows,
                                delivered_rows,
                                "completed" if ok else "failed",
                                trigger,
                                created_at,
                                created_at,
                                created_at,
                                created_at,
                                normalize_short_user_error(str(entry.get("err", "") or ""), default="") if not ok else "",
                                max(0, int(entry.get("sql_duration_us") or 0)),
                                max(0, int(entry.get("duration_us") or 0)),
                            ),
                        )
                        imported_any = True

                job["history"] = []
                normalized_jobs.append(job)

        if imported_any:
            cfg["export_jobs"] = normalized_jobs
            config.save(cfg)
        return imported_any

    def create_run(
        self,
        *,
        run_id: str,
        job_id: str,
        job_name: str,
        webhook_url: str,
        sheet_name: str,
        source_id: str,
        write_mode: str,
        export_date: str,
        total_chunks: int,
        total_rows: int,
        trigger: str,
        sql_duration_us: int = 0,
        supersedes_run_id: str | None = None,
    ) -> None:
        now_iso = _to_iso(_now_utc()) or ""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO export_runs (
                    run_id,
                    job_id,
                    job_name,
                    webhook_url,
                    sheet_name,
                    source_id,
                    write_mode,
                    export_date,
                    total_chunks,
                    total_rows,
                    delivered_chunks,
                    delivered_rows,
                    status,
                    trigger,
                    created_at,
                    started_at,
                    finished_at,
                    updated_at,
                    last_error,
                    sql_duration_us,
                    total_duration_us,
                    supersedes_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'planned', ?, ?, NULL, NULL, ?, '', ?, 0, ?)
                """,
                (
                    run_id,
                    job_id,
                    job_name,
                    webhook_url,
                    sheet_name,
                    source_id,
                    write_mode,
                    export_date,
                    max(0, int(total_chunks)),
                    max(0, int(total_rows)),
                    _normalize_trigger(trigger),
                    now_iso,
                    now_iso,
                    max(0, int(sql_duration_us)),
                    supersedes_run_id,
                ),
            )

    def supersede_unfinished_runs(self, *, job_id: str, new_run_id: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE export_runs
                   SET status = 'superseded',
                       updated_at = ?,
                       finished_at = ?,
                       supersedes_run_id = ?
                 WHERE job_id = ?
                   AND run_id <> ?
                   AND status IN ('planned', 'running', 'failed')
                """,
                (
                    _to_iso(_now_utc()) or "",
                    _to_iso(_now_utc()) or "",
                    new_run_id,
                    job_id,
                    new_run_id,
                ),
            )
            return cursor.rowcount or 0

    def mark_running(self, run_id: str) -> None:
        now_iso = _to_iso(_now_utc()) or ""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE export_runs
                   SET status = 'running',
                       started_at = COALESCE(started_at, ?),
                       updated_at = ?
                 WHERE run_id = ?
                """,
                (now_iso, now_iso, run_id),
            )

    def record_chunk_success(
        self,
        *,
        run_id: str,
        chunk_index: int,
        chunk_rows: int,
        chunk_bytes: int,
        delivered_chunks: int,
        delivered_rows: int,
    ) -> None:
        delivered_at = _to_iso(_now_utc()) or ""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO export_run_chunks (
                    run_id,
                    chunk_index,
                    chunk_rows,
                    chunk_bytes,
                    status,
                    delivered_at,
                    error_message
                ) VALUES (?, ?, ?, ?, 'delivered', ?, '')
                ON CONFLICT(run_id, chunk_index) DO UPDATE SET
                    chunk_rows = excluded.chunk_rows,
                    chunk_bytes = excluded.chunk_bytes,
                    status = 'delivered',
                    delivered_at = excluded.delivered_at,
                    error_message = ''
                """,
                (
                    run_id,
                    max(1, int(chunk_index)),
                    max(0, int(chunk_rows)),
                    max(0, int(chunk_bytes)),
                    delivered_at,
                ),
            )
            conn.execute(
                """
                UPDATE export_runs
                   SET delivered_chunks = ?,
                       delivered_rows = ?,
                       updated_at = ?
                 WHERE run_id = ?
                """,
                (
                    max(0, int(delivered_chunks)),
                    max(0, int(delivered_rows)),
                    delivered_at,
                    run_id,
                ),
            )

    def mark_failed(
        self,
        *,
        run_id: str,
        error_message: str,
        delivered_chunks: int,
        delivered_rows: int,
        total_duration_us: int = 0,
    ) -> None:
        finished_at = _to_iso(_now_utc()) or ""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE export_runs
                   SET status = 'failed',
                       delivered_chunks = ?,
                       delivered_rows = ?,
                       finished_at = ?,
                       updated_at = ?,
                       last_error = ?,
                       total_duration_us = ?
                 WHERE run_id = ?
                """,
                (
                    max(0, int(delivered_chunks)),
                    max(0, int(delivered_rows)),
                    finished_at,
                    finished_at,
                    normalize_short_user_error(error_message, default="Ошибка"),
                    max(0, int(total_duration_us)),
                    run_id,
                ),
            )

    def mark_completed(
        self,
        *,
        run_id: str,
        delivered_chunks: int,
        delivered_rows: int,
        total_duration_us: int = 0,
    ) -> None:
        finished_at = _to_iso(_now_utc()) or ""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE export_runs
                   SET status = 'completed',
                       delivered_chunks = ?,
                       delivered_rows = ?,
                       finished_at = ?,
                       updated_at = ?,
                       last_error = '',
                       total_duration_us = ?
                 WHERE run_id = ?
                """,
                (
                    max(0, int(delivered_chunks)),
                    max(0, int(delivered_rows)),
                    finished_at,
                    finished_at,
                    max(0, int(total_duration_us)),
                    run_id,
                ),
            )

    def record_history_entry(
        self,
        *,
        job_id: str,
        job_name: str,
        entry: ExportHistoryEntry,
    ) -> str:
        ts = str(entry.get("ts", "") or "").strip()
        timestamp = self._history_timestamp_to_iso(ts) or _to_iso(_now_utc()) or ""
        run_id = str(entry.get("run_id") or f"entry-{job_id}-{timestamp.replace(':', '').replace('-', '')}")
        ok = bool(entry.get("ok"))
        trigger = _normalize_trigger(entry.get("trigger"))
        rows = max(0, int(entry.get("rows") or 0))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO export_runs (
                    run_id,
                    job_id,
                    job_name,
                    webhook_url,
                    sheet_name,
                    source_id,
                    write_mode,
                    export_date,
                    total_chunks,
                    total_rows,
                    delivered_chunks,
                    delivered_rows,
                    status,
                    trigger,
                    created_at,
                    started_at,
                    finished_at,
                    updated_at,
                    last_error,
                    sql_duration_us,
                    total_duration_us,
                    supersedes_run_id
                ) VALUES (?, ?, ?, '', '', ?, '', '', 1, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    run_id,
                    job_id,
                    job_name,
                    job_id,
                    rows,
                    rows,
                    "completed" if ok else "failed",
                    trigger,
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                    "" if ok else normalize_short_user_error(str(entry.get("err", "") or ""), default="\u041e\u0448\u0438\u0431\u043a\u0430"),
                    max(0, int(entry.get("sql_duration_us") or 0)),
                    max(0, int(entry.get("duration_us") or 0)),
                ),
            )
        return run_id

    def list_job_history(self, job_id: str, *, limit: int = _HISTORY_LIMIT) -> list[ExportHistoryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM export_runs
                 WHERE job_id = ?
                   AND status IN ('completed', 'failed')
                 ORDER BY COALESCE(finished_at, updated_at, created_at) DESC
                 LIMIT ?
                """,
                (job_id, max(1, int(limit))),
            ).fetchall()
        return [self._row_to_history_entry(row) for row in rows]

    def list_recent_history(
        self,
        *,
        limit: int = _HISTORY_LIMIT,
    ) -> list[tuple[ExportHistoryEntry, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM export_runs
                 WHERE status IN ('completed', 'failed')
                 ORDER BY COALESCE(finished_at, updated_at, created_at) DESC
                 LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [(self._row_to_history_entry(row), str(row["job_name"] or "")) for row in rows]

    def latest_history_entry(self, job_id: str) -> ExportHistoryEntry | None:
        history = self.list_job_history(job_id, limit=1)
        return history[0] if history else None

    def mark_abandoned(self, run_id: str) -> bool:
        finished_at = _to_iso(_now_utc()) or ""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE export_runs
                   SET status = 'abandoned',
                       finished_at = COALESCE(finished_at, ?),
                       updated_at = ?
                 WHERE run_id = ?
                   AND status IN ('planned', 'running', 'failed')
                """,
                (finished_at, finished_at, run_id),
            )
            return bool(cursor.rowcount)

    def delete_run(self, run_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM export_run_chunks WHERE run_id = ?", (run_id,))
            cursor = conn.execute("DELETE FROM export_runs WHERE run_id = ?", (run_id,))
            return bool(cursor.rowcount)

    def delete_history_entry(self, run_id: str) -> bool:
        return self.delete_run(run_id)

    def clear_job_history(self, job_id: str) -> int:
        with self._connect() as conn:
            run_ids = [row[0] for row in conn.execute(
                "SELECT run_id FROM export_runs WHERE job_id = ? AND status IN ('completed', 'failed')",
                (job_id,),
            ).fetchall()]
            if not run_ids:
                return 0
            conn.executemany("DELETE FROM export_run_chunks WHERE run_id = ?", [(run_id,) for run_id in run_ids])
            cursor = conn.execute(
                "DELETE FROM export_runs WHERE job_id = ? AND status IN ('completed', 'failed')",
                (job_id,),
            )
            return cursor.rowcount or 0

    def clear_all_history(self) -> int:
        with self._connect() as conn:
            run_ids = [row[0] for row in conn.execute(
                "SELECT run_id FROM export_runs WHERE status IN ('completed', 'failed')"
            ).fetchall()]
            if not run_ids:
                return 0
            conn.executemany("DELETE FROM export_run_chunks WHERE run_id = ?", [(run_id,) for run_id in run_ids])
            cursor = conn.execute(
                "DELETE FROM export_runs WHERE status IN ('completed', 'failed')"
            )
            return cursor.rowcount or 0

    def list_unfinished_runs(self, *, job_id: str | None = None) -> list[ExportRunInfo]:
        query = """
            SELECT *
              FROM export_runs
             WHERE status IN ('planned', 'running', 'failed')
        """
        params: list[object] = []
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        query += " ORDER BY COALESCE(updated_at, created_at) DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_run_info(row) for row in rows]

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS export_runs (
                    run_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    job_name TEXT NOT NULL,
                    webhook_url TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    write_mode TEXT NOT NULL,
                    export_date TEXT NOT NULL,
                    total_chunks INTEGER NOT NULL,
                    total_rows INTEGER NOT NULL,
                    delivered_chunks INTEGER NOT NULL DEFAULT 0,
                    delivered_rows INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    trigger TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    last_error TEXT NOT NULL DEFAULT '',
                    sql_duration_us INTEGER NOT NULL DEFAULT 0,
                    total_duration_us INTEGER NOT NULL DEFAULT 0,
                    supersedes_run_id TEXT
                );
                CREATE TABLE IF NOT EXISTS export_run_chunks (
                    run_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_rows INTEGER NOT NULL,
                    chunk_bytes INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    delivered_at TEXT,
                    error_message TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (run_id, chunk_index),
                    FOREIGN KEY (run_id) REFERENCES export_runs(run_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_export_runs_job_status
                    ON export_runs(job_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_export_runs_recent
                    ON export_runs(status, finished_at DESC, updated_at DESC);
                """
            )

    def _row_to_history_entry(self, row: sqlite3.Row) -> ExportHistoryEntry:
        ok = str(row["status"] or "") == "completed"
        return {
            "run_id": str(row["run_id"] or ""),
            "ts": _to_history_timestamp(row["finished_at"] or row["updated_at"] or row["created_at"]),
            "trigger": _normalize_trigger(row["trigger"]),
            "ok": ok,
            "rows": max(0, int(row["delivered_rows"] or 0)),
            "err": "" if ok else str(row["last_error"] or ""),
            "duration_us": max(0, int(row["total_duration_us"] or 0)),
            "sql_duration_us": max(0, int(row["sql_duration_us"] or 0)),
        }

    def _row_to_run_info(self, row: sqlite3.Row) -> ExportRunInfo:
        return ExportRunInfo(
            run_id=str(row["run_id"] or ""),
            job_id=str(row["job_id"] or ""),
            job_name=str(row["job_name"] or ""),
            webhook_url=str(row["webhook_url"] or ""),
            sheet_name=str(row["sheet_name"] or ""),
            source_id=str(row["source_id"] or ""),
            write_mode=str(row["write_mode"] or ""),
            export_date=str(row["export_date"] or ""),
            total_chunks=max(0, int(row["total_chunks"] or 0)),
            total_rows=max(0, int(row["total_rows"] or 0)),
            delivered_chunks=max(0, int(row["delivered_chunks"] or 0)),
            delivered_rows=max(0, int(row["delivered_rows"] or 0)),
            status=str(row["status"] or ""),
            trigger=_normalize_trigger(row["trigger"]),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
            started_at=str(row["started_at"] or "") or None,
            finished_at=str(row["finished_at"] or "") or None,
            last_error=str(row["last_error"] or ""),
            sql_duration_us=max(0, int(row["sql_duration_us"] or 0)),
            total_duration_us=max(0, int(row["total_duration_us"] or 0)),
            supersedes_run_id=str(row["supersedes_run_id"] or "") or None,
        )

    def _legacy_run_id(self, job_id: str, index: int, entry: ExportHistoryEntry) -> str:
        ts = str(entry.get("ts", "") or "").strip().replace(" ", "T").replace(":", "").replace("-", "")
        trigger = _normalize_trigger(entry.get("trigger"))
        suffix = "ok" if entry.get("ok") else "err"
        return f"legacy-{job_id}-{ts or index}-{trigger}-{suffix}-{index}"

    def _history_timestamp_to_iso(self, value: str) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            return _to_iso(parsed.replace(tzinfo=UTC))
        return None


__all__ = ["ExportRunInfo", "ExportRunStore"]
