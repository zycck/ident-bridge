# -*- coding: utf-8 -*-
"""Tests for extracted test-run dialog controller."""

from PySide6.QtCore import QObject

from app.config import QueryResult
from app.ui.test_run_dialog_controller import TestRunDialogController as _TestRunDialogController


class _FakeShell(QObject):
    def __init__(self, sql: str = "SELECT 1") -> None:
        super().__init__()
        self._sql = sql
        self.run_enabled: list[bool] = []
        self.status_updates: list[tuple[str, str]] = []
        self.results: list[QueryResult] = []

    def sql_text(self) -> str:
        return self._sql

    def set_run_enabled(self, enabled: bool) -> None:
        self.run_enabled.append(enabled)

    def set_status(self, text: str, *, color: str) -> None:
        self.status_updates.append((text, color))

    def populate_result(self, result: QueryResult) -> None:
        self.results.append(result)


def test_test_run_dialog_controller_skips_blank_sql() -> None:
    owner = QObject()
    shell = _FakeShell("   ")
    worker_calls = []
    completed = []
    controller = _TestRunDialogController(
        owner=owner,
        shell=shell,
        cfg={},
        emit_test_completed=lambda ok, rows, err: completed.append((ok, rows, err)),
        run_worker_fn=lambda *args, **kwargs: worker_calls.append((args, kwargs)),
    )

    assert controller.run_query() is False
    assert worker_calls == []
    assert completed == []
    assert shell.run_enabled == []


def test_test_run_dialog_controller_starts_worker_and_sets_busy_state() -> None:
    owner = QObject()
    shell = _FakeShell("SELECT 42")
    worker_calls = []
    created = []

    def _worker_factory(cfg, sql):
        created.append((cfg, sql))
        return object()

    controller = _TestRunDialogController(
        owner=owner,
        shell=shell,
        cfg={"sql_instance": "srv"},
        emit_test_completed=lambda *_args: None,
        run_worker_fn=lambda *args, **kwargs: worker_calls.append((args, kwargs)),
        worker_factory=_worker_factory,
    )

    assert controller.run_query() is True
    assert created == [({"sql_instance": "srv"}, "SELECT 42")]
    assert shell.run_enabled == [False]
    assert shell.status_updates == [("Выполнение…", "")]
    assert len(worker_calls) == 1
    assert worker_calls[0][1]["pin_attr"] == "_worker"
    assert callable(worker_calls[0][1]["connect_signals"])


def test_test_run_dialog_controller_handles_result_and_error() -> None:
    owner = QObject()
    shell = _FakeShell("SELECT 1")
    completed = []
    controller = _TestRunDialogController(
        owner=owner,
        shell=shell,
        cfg={},
        emit_test_completed=lambda ok, rows, err: completed.append((ok, rows, err)),
    )
    result = QueryResult(columns=["id"], rows=[(1,), (2,)], count=2, duration_ms=7)

    controller.handle_result(result)
    controller.handle_error("boom")

    assert shell.results == [result]
    assert shell.run_enabled == [True, True]
    assert shell.status_updates == [("2 строк · 7 мс", ""), ("boom", "#EF4444")]
    assert completed == [(True, 2, ""), (False, 0, "boom")]
