# -*- coding: utf-8 -*-
"""Tests for export failure accounting in ExportJobEditor."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import ExportJob, SyncResult
from app.ui.export_jobs_widget import ExportJobEditor


class _DummyConfig:
    def load(self):
        return {}

    def save(self, cfg):
        self.saved = cfg


@pytest.fixture
def export_job() -> ExportJob:
    return ExportJob(
        id="job-1",
        name="Nightly export",
        sql_query="SELECT 1",
        webhook_url="",
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],
    )


@pytest.fixture
def editor(qapp_session, export_job):
    return ExportJobEditor(export_job, _DummyConfig())


def _failure_result() -> SyncResult:
    return SyncResult(
        success=False,
        rows_synced=0,
        error="db down",
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def _success_result() -> SyncResult:
    return SyncResult(
        success=True,
        rows_synced=7,
        error=None,
        timestamp=datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
    )


def test_failed_run_counts_once_and_alerts_on_third_failure(editor):
    alerts: list[tuple[str, int]] = []
    editor.failure_alert.connect(lambda name, count: alerts.append((name, count)))

    for _ in range(2):
        editor._on_error("db down")
        editor._on_finished(_failure_result())

    assert editor._consecutive_failures == 2
    assert alerts == []

    editor._on_error("db down")
    editor._on_finished(_failure_result())

    assert editor._consecutive_failures == 3
    assert alerts == [("Nightly export", 3)]


def test_success_resets_failure_counter(editor):
    alerts: list[tuple[str, int]] = []
    editor.failure_alert.connect(lambda name, count: alerts.append((name, count)))

    editor._on_error("db down")
    editor._on_finished(_failure_result())
    editor._on_error("db down")
    editor._on_finished(_failure_result())

    assert editor._consecutive_failures == 2

    editor._on_finished(_success_result())

    assert editor._consecutive_failures == 0
    assert alerts == []

    editor._on_error("db down")
    editor._on_finished(_failure_result())

    assert editor._consecutive_failures == 1
    assert alerts == []
