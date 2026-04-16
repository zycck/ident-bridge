# -*- coding: utf-8 -*-
"""Tests for extracted export jobs persistence helpers."""

from app.ui.export_jobs_store import (
    load_export_jobs,
    new_export_job,
    persist_export_jobs,
)


class _DummyConfig:
    def __init__(self) -> None:
        self.data = {
            "export_jobs": [
                {
                    "id": "job-1",
                    "name": "Nightly",
                    "sql_query": "SELECT 1",
                    "webhook_url": "",
                    "history": [{"ts": "2026-01-01 00:00:00"}],
                }
            ],
            "sql_instance": "server\\SQLEXPRESS",
        }

    def load(self):
        return dict(self.data)

    def save(self, cfg):
        self.data = dict(cfg)


def test_load_export_jobs_normalizes_missing_fields() -> None:
    jobs = load_export_jobs(_DummyConfig())

    assert jobs == [
        {
            "id": "job-1",
            "name": "Nightly",
            "sql_query": "SELECT 1",
            "webhook_url": "",
            "schedule_enabled": False,
            "schedule_mode": "daily",
            "schedule_value": "",
            "history": [{"ts": "2026-01-01 00:00:00"}],
        }
    ]


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

    assert job["id"]
    assert job["name"] == ""
    assert job["sql_query"] == ""
    assert job["schedule_enabled"] is False
    assert job["schedule_mode"] == "daily"
    assert job["history"] == []
