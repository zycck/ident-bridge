"""View adapter for Settings SQL discovery widgets."""

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QComboBox, QLabel

from app.config import SqlInstance
from app.ui.settings_sql_presenters import build_database_items, build_instance_items
from app.ui.widgets import set_status


class SettingsSqlView:
    """Owns combo-box/status mutations for SQL discovery UI."""

    def __init__(
        self,
        *,
        instance_combo: QComboBox,
        db_combo: QComboBox,
        conn_status: QLabel,
    ) -> None:
        self._instance_combo = instance_combo
        self._db_combo = db_combo
        self._conn_status = conn_status

    def show_scan_in_progress(self) -> None:
        self._instance_combo.clear()
        self._instance_combo.addItem("Сканирование…")
        self._instance_combo.setEnabled(False)

    def populate_instances(
        self,
        instances: list[SqlInstance],
        *,
        saved_instance: str,
    ) -> int | None:
        with QSignalBlocker(self._instance_combo):
            self._instance_combo.setEnabled(True)
            self._instance_combo.clear()

            if not instances:
                self._instance_combo.addItem("Нет экземпляров")
                return None

            items, target_idx = build_instance_items(
                instances,
                saved_instance=saved_instance,
            )
            for label, inst in items:
                self._instance_combo.addItem(label, userData=inst)
            self._instance_combo.setCurrentIndex(target_idx)
            return target_idx

    def show_scan_error(self, message: str) -> None:
        self._instance_combo.setEnabled(True)
        self._instance_combo.clear()
        self._instance_combo.addItem("Ошибка сканирования")
        set_status(self._conn_status, "error", f"Сканирование: {message}")

    def show_databases_loading(self) -> None:
        self._db_combo.clear()
        self._db_combo.addItem("Загрузка…")
        self._db_combo.setEnabled(False)

    def populate_databases(self, databases: list[str], *, restore: str) -> int:
        items, final_idx = build_database_items(databases, restore=restore)
        with QSignalBlocker(self._db_combo):
            self._db_combo.clear()
            self._db_combo.setEnabled(True)
            for db in items:
                self._db_combo.addItem(db)
            if self._db_combo.count() > 0:
                self._db_combo.setCurrentIndex(final_idx)
        return final_idx

    def show_database_error(self, message: str) -> None:
        self._db_combo.clear()
        self._db_combo.setEnabled(True)
        set_status(self._conn_status, "error", f"Список БД: {message}")
