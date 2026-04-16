# -*- coding: utf-8 -*-
"""SQL discovery/test orchestration extracted from SettingsWidget."""

from collections.abc import Callable

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit

from app.config import AppConfig, SqlInstance
from app.core.app_logger import get_logger
from app.ui.settings_persistence import build_connection_config
from app.ui.settings_sql_flow import SettingsSqlFlowState
from app.ui.settings_sql_presenters import (
    next_instance_index,
)
from app.ui.settings_sql_view import SettingsSqlView
from app.ui.settings_workers import (
    DatabaseListWorker,
    InstanceScanWorker,
    TestConnectionWorker,
    instance_from_text,
)
from app.ui.threading import run_worker
from app.ui.widgets import set_status

_log = get_logger(__name__)

LoadConfigFn = Callable[[], AppConfig]
RunWorkerFn = Callable[..., object]
ScanWorkerFactory = Callable[[], object]
DatabaseListWorkerFactory = Callable[[SqlInstance, str, str], object]
TestConnectionWorkerFactory = Callable[[AppConfig], object]


class SettingsSqlController(QObject):
    """Owns scan/list/test orchestration for SQL settings widgets."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        instance_combo: QComboBox,
        db_combo: QComboBox,
        login_edit: QLineEdit,
        password_edit: QLineEdit,
        conn_status: QLabel,
        flow: SettingsSqlFlowState,
        load_config: LoadConfigFn,
        run_worker_fn: RunWorkerFn = run_worker,
        scan_worker_factory: ScanWorkerFactory = InstanceScanWorker,
        database_list_worker_factory: DatabaseListWorkerFactory = DatabaseListWorker,
        test_connection_worker_factory: TestConnectionWorkerFactory = TestConnectionWorker,
    ) -> None:
        super().__init__(parent)
        self._instance_combo = instance_combo
        self._db_combo = db_combo
        self._login_edit = login_edit
        self._password_edit = password_edit
        self._conn_status = conn_status
        self._flow = flow
        self._load_config = load_config
        self._run_worker = run_worker_fn
        self._scan_worker_factory = scan_worker_factory
        self._database_list_worker_factory = database_list_worker_factory
        self._test_connection_worker_factory = test_connection_worker_factory
        self._scan_worker: object | None = None
        self._dblist_worker: object | None = None
        self._test_conn_worker: object | None = None
        self._view = SettingsSqlView(
            instance_combo=self._instance_combo,
            db_combo=self._db_combo,
            conn_status=self._conn_status,
        )

    def scan_instances(self, _checked: bool = False) -> bool:
        if not self._flow.begin_scan():
            return False

        self._view.show_scan_in_progress()

        worker = self._scan_worker_factory()
        self._run_worker(
            self,
            worker,
            pin_attr="_scan_worker",
            on_finished=self._on_scan_finished,
            on_error=self._on_scan_error,
        )
        return True

    @Slot(list)
    def _on_scan_finished(self, instances: list[SqlInstance]) -> None:
        self._flow.finish_scan()
        target_idx = self._view.populate_instances(
            instances,
            saved_instance=self._load_config().get("sql_instance", ""),
        )
        if target_idx is not None:
            self.handle_instance_changed(target_idx)

    @Slot(str)
    def _on_scan_error(self, message: str) -> None:
        self._flow.fail_scan()
        self._view.show_scan_error(message)

    @Slot(int)
    def handle_instance_changed(self, idx: int) -> bool:
        inst = self._instance_combo.itemData(idx)
        if inst is None:
            inst = instance_from_text(self._instance_combo.itemText(idx))
            if inst is None:
                return False
            self._instance_combo.setItemData(idx, inst)
        return self._fetch_databases(inst)

    def refresh_databases(self, _checked: bool = False) -> bool:
        idx = self._instance_combo.currentIndex()
        inst = self._instance_combo.itemData(idx)
        if inst is None:
            inst = instance_from_text(self._instance_combo.currentText())
        if inst is None:
            return False
        return self._fetch_databases(inst)

    def _fetch_databases(self, inst: SqlInstance) -> bool:
        if not self._flow.begin_database_fetch(inst):
            return False

        self._view.show_databases_loading()

        user = self._login_edit.text().strip()
        password = self._password_edit.text()
        worker = self._database_list_worker_factory(inst, user, password)
        self._run_worker(
            self,
            worker,
            pin_attr="_dblist_worker",
            on_finished=self._on_dblist_finished,
            on_error=self._on_dblist_error,
        )
        return True

    @Slot(list)
    def _on_dblist_finished(self, databases: list[str]) -> None:
        restore, pending = self._flow.finish_database_fetch(
            saved_database=self._load_config().get("sql_database", "") or "",
        )
        final_idx = self._view.populate_databases(databases, restore=restore)

        if self._db_combo.count() > 0:
            if self._db_combo.currentIndex() != final_idx:
                self._db_combo.setCurrentIndex(final_idx)
            else:
                self._flow.remember_database_selection(self._db_combo.itemText(final_idx))

        if pending is not None:
            self._fetch_databases(pending)

    @Slot(str)
    def _on_dblist_error(self, message: str) -> None:
        pending = self._flow.fail_database_fetch()

        self._view.show_database_error(message)

        if pending is not None:
            self._fetch_databases(pending)
            return

        cur = self._instance_combo.currentIndex()
        nxt = next_instance_index(
            current_index=cur,
            total_count=self._instance_combo.count(),
        )
        if nxt is None:
            return
        next_inst = self._instance_combo.itemData(nxt)
        if next_inst is None:
            return
        _log.debug("Auto-advancing to next instance: %s", next_inst.display)
        self._instance_combo.blockSignals(True)
        self._instance_combo.setCurrentIndex(nxt)
        self._instance_combo.blockSignals(False)
        self._fetch_databases(next_inst)

    def test_connection(self, _checked: bool = False) -> bool:
        if not self._flow.begin_connection_test():
            return False

        cfg = build_connection_config(
            sql_instance=self._instance_combo.currentText().strip(),
            sql_database=self._db_combo.currentText().strip(),
            sql_user=self._login_edit.text().strip(),
            sql_password=self._password_edit.text(),
        )
        set_status(self._conn_status, "neutral", "Проверка подключения…")

        worker = self._test_connection_worker_factory(cfg)
        self._run_worker(
            self,
            worker,
            pin_attr="_test_conn_worker",
            on_finished=self._on_test_conn_finished,
        )
        return True

    @Slot(bool, str)
    def _on_test_conn_finished(self, ok: bool, message: str) -> None:
        self._flow.finish_connection_test()
        if ok:
            set_status(self._conn_status, "ok", message or "Подключение успешно")
        else:
            set_status(self._conn_status, "error", message or "Ошибка подключения")
