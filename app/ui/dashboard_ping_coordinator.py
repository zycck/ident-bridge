# -*- coding: utf-8 -*-

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from app.config import AppConfig, ConfigManager
from app.core.app_logger import get_logger
from app.core.sql_client import SqlClient
from app.ui.threading import run_worker

_log = get_logger(__name__)


class _PingWorker(QObject):
    result = Signal(object)  # bool | None; None = instance not configured
    finished = Signal()

    def __init__(
        self,
        instance: str,
        database: str,
        user: str,
        password: str,
        trust_cert: bool,
    ) -> None:
        super().__init__()
        self._instance = instance
        self._database = database
        self._user = user
        self._password = password
        self._trust_cert = trust_cert

    @Slot()
    def run(self) -> None:
        try:
            if not self._instance:
                _log.debug("DB ping skipped: instance not configured")
                self.result.emit(None)
                return

            cfg = AppConfig(
                sql_instance=self._instance,
                sql_database=self._database,
                sql_user=self._user,
                sql_password=self._password,
                sql_trust_cert=self._trust_cert,
            )
            client = SqlClient(cfg)
            try:
                client.connect()
                alive = client.is_alive()
            except Exception as exc:
                _log.debug("DB ping failed: %s", exc)
                alive = False
            finally:
                client.disconnect()

            _log.debug("DB ping: %s", "alive" if alive else "unreachable")
            self.result.emit(alive)
        finally:
            self.finished.emit()


class DashboardPingCoordinator(QObject):
    def __init__(
        self,
        parent: QObject,
        config: ConfigManager,
        set_connected: Callable[[bool | None], None],
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._set_connected = set_connected
        self._ping_running = False
        self._ping_worker: _PingWorker | None = None  # strong ref to prevent GC

    def stop(self) -> None:
        self._ping_running = False

    def ping_db(self) -> None:
        if self._ping_running:
            return

        cfg = self._config.load()
        self._ping_running = True

        worker = _PingWorker(
            instance=cfg.get("sql_instance") or "",
            database=cfg.get("sql_database") or "master",
            user=cfg.get("sql_user") or "",
            password=cfg.get("sql_password") or "",
            trust_cert=(
                cfg.get("sql_trust_cert")
                if cfg.get("sql_trust_cert") is not None
                else True
            ),
        )
        run_worker(
            self,
            worker,
            pin_attr="_ping_worker",
            on_finished=self._on_ping_finished,
            connect_signals=lambda ping_worker, _thread: ping_worker.result.connect(
                self._on_ping_result
            ),
        )

    @Slot(object)
    def _on_ping_result(self, alive) -> None:
        self._ping_running = False
        self._set_connected(alive)

    @Slot()
    def _on_ping_finished(self) -> None:
        # Defensive reset in case a fast worker finished before a result
        # handler had a chance to run or exited early with no connectivity
        # update.
        self._ping_running = False
