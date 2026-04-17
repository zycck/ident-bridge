# -*- coding: utf-8 -*-
"""Runtime controller for the test-run SQL dialog."""

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from app.config import AppConfig, QueryResult
from app.core.app_logger import get_logger
from app.core.constants import TEST_DIALOG_MAX_ROWS
from app.core.sql_client import SqlClient
from app.ui.test_run_dialog_shell import TestRunDialogShell
from app.ui.threading import run_worker

_log = get_logger(__name__)

RunWorkerFn = Callable[..., object]
EmitTestCompletedFn = Callable[[bool, int, str], None]
QueryWorkerFactory = Callable[[AppConfig, str], object]


class _QueryWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, cfg: AppConfig, sql: str) -> None:
        super().__init__()
        self._cfg = cfg
        self._sql = sql

    @Slot()
    def run(self) -> None:
        client = SqlClient(self._cfg)
        try:
            client.connect()
            query_result = client.query(self._sql, max_rows=TEST_DIALOG_MAX_ROWS)
            _log.info("Query: %d строк за %d мс", query_result.count, query_result.duration_ms)
            self.result.emit(query_result)
        except ConnectionError as exc:
            _log.error("Query connection failed: %s", exc)
            self.error.emit(str(exc))
        except Exception as exc:
            _log.error("Query failed: %s", exc)
            self.error.emit("Ошибка выполнения запроса")
        finally:
            client.disconnect()
            self.finished.emit()


class TestRunDialogController(QObject):
    """Owns worker startup and result/error handling for TestRunDialog."""

    def __init__(
        self,
        *,
        owner: QObject,
        shell: TestRunDialogShell,
        cfg: AppConfig,
        emit_test_completed: EmitTestCompletedFn,
        run_worker_fn: RunWorkerFn = run_worker,
        worker_factory: QueryWorkerFactory = _QueryWorker,
    ) -> None:
        super().__init__(owner)
        self._owner = owner
        self._shell = shell
        self._cfg = cfg
        self._emit_test_completed = emit_test_completed
        self._run_worker = run_worker_fn
        self._worker_factory = worker_factory

    def wire(self) -> None:
        self._shell.run_requested.connect(self.run_query)

    @Slot()
    def run_query(self) -> bool:
        sql = self._shell.sql_text().strip()
        if not sql:
            return False

        self._shell.set_run_enabled(False)
        self._shell.set_status("Выполнение…", color="")

        worker = self._worker_factory(self._cfg, sql)
        self._run_worker(
            self._owner,
            worker,
            pin_attr="_worker",
            on_error=self.handle_error,
            connect_signals=lambda query_worker, _thread: query_worker.result.connect(
                self.handle_result
            ),
        )
        return True

    @Slot(object)
    def handle_result(self, result: QueryResult) -> None:
        self._shell.populate_result(result)
        status = f"{result.count} строк · {result.duration_ms} мс"
        if result.truncated:
            status += " · показаны первые строки"
        self._shell.set_status(status, color="")
        self._shell.set_run_enabled(True)
        self._emit_test_completed(True, result.count, "")

    @Slot(str)
    def handle_error(self, msg: str) -> None:
        self._shell.set_status(msg, color="#EF4444")
        self._shell.set_run_enabled(True)
        self._emit_test_completed(False, 0, msg)
