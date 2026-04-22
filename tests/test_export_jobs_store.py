"""Tests for extracted export jobs persistence helpers."""

from app.config import AppConfig
from app.export.run_store import ExportRunInfo
from app.ui.export_jobs_store import (
    find_duplicate_export_target,
    load_export_jobs,
    new_export_job,
    persist_export_jobs,
)

_SHORT_JOB_ID_ALPHABET = set("abcdefghijklmnopqrstuvwxyz234567")


def _is_short_job_id(value: str) -> bool:
    return len(value) == 12 and set(value) <= _SHORT_JOB_ID_ALPHABET


class _DummyConfig:
    def __init__(self) -> None:
        self.data = {
            "export_jobs": [
                {
                    "id": "job-1",
                    "name": "Nightly",
                    "sql_query": "SELECT 1",
                    "webhook_url": "",
                    "gas_options": {
                        "sheet_name": "Exports",
                        "write_mode": "append",
                        "header_row": "2",
                        "dedupe_key_columns": ["id", "updated_at", ""],
                        "scheme_id": "  library_v1  ",
                    },
                    "history": [{"ts": "2026-01-01 00:00:00"}],
                }
            ],
            "sql_instance": "server\\SQLEXPRESS",
        }

    def load(self):
        return dict(self.data)

    def save(self, cfg):
        self.data = dict(cfg)


class _FakeRunStore:
    def list_job_history(self, job_id: str):
        return [{"ts": f"{job_id}-sqlite"}]

    def list_unfinished_runs(self, *, job_id: str | None = None):
        if job_id != "job-1":
            return []
        return [
            ExportRunInfo(
                run_id="run-1",
                job_id="job-1",
                job_name="Nightly",
                webhook_url="https://example.test",
                sheet_name="Exports",
                source_id="job-1",
                write_mode="replace_all",
                export_date="2026-04-21",
                total_chunks=3,
                total_rows=9,
                delivered_chunks=1,
                delivered_rows=3,
                status="running",
                trigger="manual",
                created_at="2026-04-21T09:00:00+00:00",
                updated_at="2026-04-21T09:05:00+00:00",
                started_at="2026-04-21T09:00:10+00:00",
                finished_at=None,
                last_error="",
                sql_duration_us=0,
                total_duration_us=0,
                supersedes_run_id=None,
            )
        ]


def test_load_export_jobs_normalizes_missing_fields() -> None:
    jobs = load_export_jobs(_DummyConfig())

    assert jobs == [
        {
            "id": "job-1",
            "name": "Nightly",
            "sql_query": "SELECT 1",
            "webhook_url": "",
            "gas_options": {"sheet_name": "Exports", "write_mode": "append"},
            "schedule_enabled": False,
            "schedule_mode": "daily",
            "schedule_value": "",
            "history": [{"ts": "2026-01-01 00:00:00"}],
        }
    ]


def test_load_export_jobs_fills_missing_identity_fields() -> None:
    class _Config:
        def load(self):
            return {
                "export_jobs": [
                    {
                        "sql_query": "SELECT 1",
                        "history": [],
                    }
                ]
            }

    jobs = load_export_jobs(_Config())

    assert _is_short_job_id(jobs[0]["id"])
    assert jobs[0]["name"] == ""


def test_load_export_jobs_drops_legacy_gas_fields_through_config_manager(tmp_config) -> None:
    tmp_config.save(
        AppConfig(
            export_jobs=[
                {
                    "id": "job-3",
                    "name": "Nightly",
                    "sql_query": "SELECT 1",
                    "webhook_url": "",
                    "gas_options": {
                        "sheet_name": "Exports",
                        "header_row": "2",
                        "dedupe_key_columns": ["id", ""],
                        "auth_token": "  secret-token  ",
                        "scheme_id": "  library_v1  ",
                    },
                    "schedule_enabled": False,
                    "schedule_mode": "daily",
                    "schedule_value": "",
                    "history": [],
                }
            ]
        )
    )

    jobs = load_export_jobs(tmp_config)

    assert jobs[0]["gas_options"] == {
        "sheet_name": "Exports",
        "write_mode": "replace_by_date_source",
    }


def test_load_export_jobs_reads_history_and_unfinished_runs_from_sqlite_store() -> None:
    jobs = load_export_jobs(_DummyConfig(), run_store=_FakeRunStore())

    assert jobs[0]["history"] == [{"ts": "job-1-sqlite"}]
    assert jobs[0]["unfinished_runs"][0].run_id == "run-1"


def test_find_duplicate_export_target_detects_same_webhook_and_sheet() -> None:
    duplicate = find_duplicate_export_target(
        [
            {
                "id": "job-1",
                "name": "Nightly",
                "sql_query": "SELECT 1",
                "webhook_url": "https://script.google.com/macros/s/abc/exec",
                "gas_options": {"sheet_name": "Exports"},
                "schedule_enabled": False,
                "schedule_mode": "daily",
                "schedule_value": "",
                "history": [],
            },
            {
                "id": "job-2",
                "name": "Archive",
                "sql_query": "SELECT 2",
                "webhook_url": "https://script.google.com/macros/s/abc/exec",
                "gas_options": {"sheet_name": "Exports"},
                "schedule_enabled": False,
                "schedule_mode": "daily",
                "schedule_value": "",
                "history": [],
            },
        ]
    )

    assert duplicate == (
        "job-1",
        "job-2",
        "https://script.google.com/macros/s/abc/exec",
        "Exports",
    )


def test_persist_export_jobs_preserves_other_config_fields() -> None:
    cfg = _DummyConfig()

    persist_export_jobs(
        cfg,
        [
            {
                "id": "job-2",
                "name": "Manual",
                "sql_query": "SELECT 2",
                "webhook_url": "https://example.test",
                "gas_options": {
                    "sheet_name": "Archive",
                    "write_mode": "replace_all",
                },
                "schedule_enabled": True,
                "schedule_mode": "hourly",
                "schedule_value": "2",
                "history": [],
            }
        ],
    )

    assert cfg.data["sql_instance"] == "server\\SQLEXPRESS"
    assert cfg.data["export_jobs"][0]["id"] == "job-2"


def test_new_export_job_starts_blank_with_generated_id() -> None:
    job = new_export_job()

    assert _is_short_job_id(job["id"])
    assert job["name"] == ""
    assert job["sql_query"] == ""
    assert job["schedule_enabled"] is False
    assert job["schedule_mode"] == "daily"
    assert job["gas_options"] == {
        "sheet_name": "",
        "write_mode": "replace_by_date_source",
    }
    assert job["history"] == []
