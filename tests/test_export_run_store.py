from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from app.export.run_store import ExportRunStore


def _save_jobs(tmp_config, jobs: list[dict]) -> None:
    cfg = tmp_config.load()
    cfg["export_jobs"] = jobs
    tmp_config.save(cfg)


def test_export_run_store_migrates_legacy_history_and_clears_config(tmp_config) -> None:
    _save_jobs(
        tmp_config,
        [
            {
                "id": "job-1",
                "name": "Сотрудники",
                "history": [
                    {
                        "ts": "2026-04-20 12:00:00",
                        "ok": True,
                        "rows": 12,
                        "trigger": "manual",
                        "duration_us": 3_000_000,
                        "sql_duration_us": 1_000_000,
                    },
                    {
                        "ts": "2026-04-20 11:00:00",
                        "ok": False,
                        "err": "boom",
                        "trigger": "scheduled",
                    },
                ],
            }
        ],
    )

    store = ExportRunStore()

    assert store.migrate_legacy_history(tmp_config) is True

    history = store.list_job_history("job-1")
    assert [entry["ok"] for entry in history] == [True, False]
    assert history[0]["rows"] == 12
    assert history[1]["err"] == "boom"
    assert tmp_config.load()["export_jobs"][0]["history"] == []


def test_export_run_store_tracks_run_progress_and_failure(tmp_config) -> None:
    store = ExportRunStore()
    store.create_run(
        run_id="run-1",
        job_id="job-1",
        job_name="Сотрудники",
        webhook_url="https://script.google.com/macros/s/abc/exec",
        sheet_name="Лист1",
        source_id="job-1",
        write_mode="replace_by_date_source",
        export_date="2026-04-21",
        total_chunks=3,
        total_rows=9,
        trigger="manual",
        sql_duration_us=25_000,
    )
    store.mark_running("run-1")
    store.record_chunk_success(
        run_id="run-1",
        chunk_index=1,
        chunk_rows=3,
        chunk_bytes=120,
        delivered_chunks=1,
        delivered_rows=3,
    )
    store.mark_failed(
        run_id="run-1",
        error_message="Сеть оборвалась",
        delivered_chunks=1,
        delivered_rows=3,
        total_duration_us=50_000,
    )

    unfinished = store.list_unfinished_runs(job_id="job-1")
    assert len(unfinished) == 1
    assert unfinished[0].status == "failed"
    assert unfinished[0].delivered_chunks == 1
    assert unfinished[0].delivered_rows == 3

    history = store.list_job_history("job-1")
    assert len(history) == 1
    assert history[0]["ok"] is False
    assert history[0]["err"] == "Сеть оборвалась"


def test_export_run_store_marks_previous_unfinished_runs_superseded(tmp_config) -> None:
    store = ExportRunStore()
    store.create_run(
        run_id="run-old",
        job_id="job-1",
        job_name="Сотрудники",
        webhook_url="https://script.google.com/macros/s/abc/exec",
        sheet_name="Лист1",
        source_id="job-1",
        write_mode="replace_all",
        export_date="2026-04-21",
        total_chunks=2,
        total_rows=10,
        trigger="manual",
    )
    store.mark_running("run-old")
    store.create_run(
        run_id="run-new",
        job_id="job-1",
        job_name="Сотрудники",
        webhook_url="https://script.google.com/macros/s/abc/exec",
        sheet_name="Лист1",
        source_id="job-1",
        write_mode="replace_all",
        export_date="2026-04-21",
        total_chunks=2,
        total_rows=10,
        trigger="manual",
    )

    assert store.supersede_unfinished_runs(job_id="job-1", new_run_id="run-new") == 1

    unfinished = store.list_unfinished_runs(job_id="job-1")
    assert [run.run_id for run in unfinished] == ["run-new"]


def test_export_run_store_records_history_entries_and_recent_history(tmp_config) -> None:
    store = ExportRunStore()
    store.record_history_entry(
        job_id="job-1",
        job_name="Сотрудники",
        entry={
            "run_id": "entry-job-1",
            "ts": "2026-04-21 09:00:00",
            "ok": True,
            "rows": 5,
            "err": "",
            "trigger": "test",
            "duration_us": 12_000,
        },
    )
    store.record_history_entry(
        job_id="job-2",
        job_name="\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u044f",
        entry={
            "run_id": "entry-job-2",
            "ts": "2026-04-21 10:00:00",
            "ok": False,
            "rows": 0,
            "err": "\u041e\u0448\u0438\u0431\u043a\u0430 SQL",
            "trigger": "test",
            "duration_us": 15_000,
        },
    )

    recent = store.list_recent_history(limit=5)
    assert len(recent) == 2
    assert recent[0][1] == "Начисления"
    assert recent[0][0]["trigger"] == "test"
    assert recent[0][0]["ok"] is False


def test_export_run_store_clears_job_and_global_history(tmp_config) -> None:
    store = ExportRunStore()
    for job_id in ("job-1", "job-2"):
        store.record_history_entry(
            job_id=job_id,
            job_name=job_id,
            entry={
                "run_id": f"entry-{job_id}",
                "ts": "2026-04-21 09:00:00",
                "ok": True,
                "rows": 1,
                "err": "",
                "trigger": "test",
                "duration_us": 1_000,
            },
        )

    assert store.clear_job_history("job-1") == 1
    assert store.list_job_history("job-1") == []
    assert len(store.list_recent_history()) == 1
    assert store.clear_all_history() == 1
    assert store.list_recent_history() == []


def test_export_run_store_can_abandon_and_delete_unfinished_runs(tmp_config) -> None:
    store = ExportRunStore()
    store.create_run(
        run_id="run-1",
        job_id="job-1",
        job_name="Сотрудники",
        webhook_url="https://script.google.com/macros/s/abc/exec",
        sheet_name="Лист1",
        source_id="job-1",
        write_mode="replace_all",
        export_date="2026-04-21",
        total_chunks=2,
        total_rows=10,
        trigger="manual",
    )

    assert [run.run_id for run in store.list_unfinished_runs(job_id="job-1")] == ["run-1"]
    assert store.mark_abandoned("run-1") is True
    assert store.list_unfinished_runs(job_id="job-1") == []

    store.create_run(
        run_id="run-2",
        job_id="job-1",
        job_name="Сотрудники",
        webhook_url="https://script.google.com/macros/s/abc/exec",
        sheet_name="Лист1",
        source_id="job-1",
        write_mode="append",
        export_date="2026-04-21",
        total_chunks=3,
        total_rows=10,
        trigger="manual",
    )

    assert [run.run_id for run in store.list_unfinished_runs(job_id="job-1")] == ["run-2"]
    assert store.delete_run("run-2") is True
    assert store.list_unfinished_runs(job_id="job-1") == []


def test_export_run_store_uses_wal_mode_for_concurrent_ui_reads(tmp_config) -> None:
    store = ExportRunStore()

    with sqlite3.connect(store.db_path) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert str(journal_mode).lower() == "wal"


def test_export_run_store_closes_connections_so_temp_dir_can_be_removed() -> None:
    with tempfile.TemporaryDirectory(prefix="ident-run-store-") as tmp:
        db_path = Path(tmp) / "runtime.sqlite3"
        store = ExportRunStore(db_path=db_path)
        store.record_history_entry(
            job_id="job-1",
            job_name="job-1",
            entry={
                "run_id": "entry-job-1",
                "ts": "2026-04-21 09:00:00",
                "ok": True,
                "rows": 1,
                "err": "",
                "trigger": "test",
                "duration_us": 1_000,
            },
        )
        assert store.list_recent_history(limit=1)

    assert not db_path.exists()
