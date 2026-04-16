from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QMessageBox,
    QWidget,
)

from app.config import ConfigManager
from app.core.app_logger import get_logger

from app.core.updater import GITHUB_REPO
from app.ui.settings_app_controller import SettingsAppController
from app.ui.settings_shell import SettingsShell
from app.ui.settings_actions import (
    SettingsUpdateCoordinator,
    is_startup_enabled,
)
from app.ui.settings_form_controller import SettingsFormController
from app.ui.settings_sql_controller import SettingsSqlController
from app.ui.settings_sql_flow import SettingsSqlFlowState

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# SettingsWidget
# ---------------------------------------------------------------------------

class SettingsWidget(QWidget):

    def __init__(
        self,
        config: ConfigManager,
        current_version: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._current_version = current_version
        self._sql_flow = SettingsSqlFlowState()
        self._update_actions = SettingsUpdateCoordinator(
            self,
            current_version=self._current_version,
        )

        self._build_ui()
        self._sql_controller = SettingsSqlController(
            self,
            instance_combo=self._instance_combo,
            db_combo=self._db_combo,
            login_edit=self._login_edit,
            password_edit=self._password_edit,
            conn_status=self._conn_status,
            flow=self._sql_flow,
            load_config=self._config.load,
        )
        self._form_controller = SettingsFormController(
            config=self._config,
            flow=self._sql_flow,
            instance_combo=self._instance_combo,
            db_combo=self._db_combo,
            login_edit=self._login_edit,
            password_edit=self._password_edit,
            startup_check=self._startup_check,
            auto_update_check=self._auto_update_check,
            github_repo=GITHUB_REPO,
            is_startup_enabled_fn=is_startup_enabled,
            on_instance_selected=self._sql_controller.handle_instance_changed,
        )
        self._app_controller = SettingsAppController(
            startup_check=self._startup_check,
            update_coordinator=self._update_actions,
        )
        self._connect_auto_save()
        self._load_fields()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._shell = SettingsShell(self._current_version, self)
        self._shell.reset_requested.connect(self._reset)
        self._shell.save_requested.connect(self._save)
        self._shell.setContentsMargins(0, 0, 0, 0)

        outer = self.layout()
        if outer is None:
            from PySide6.QtWidgets import QVBoxLayout

            outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._shell)

        self._sql_panel = self._shell.sql_panel()
        self._instance_combo = self._sql_panel.instance_combo()
        self._db_combo = self._sql_panel.database_combo()
        self._login_edit = self._sql_panel.login_edit()
        self._password_edit = self._sql_panel.password_edit()
        self._conn_status = self._sql_panel.conn_status()
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        self._sql_panel.scan_requested.connect(self._scan_instances)
        self._sql_panel.refresh_databases_requested.connect(self._refresh_databases)
        self._sql_panel.test_connection_requested.connect(self._test_connection)

        self._app_panel = self._shell.app_panel()
        self._startup_check = self._app_panel.startup_check()
        self._auto_update_check = self._app_panel.auto_update_check()
        self._app_panel.startup_toggled.connect(self._on_startup_toggled)
        self._app_panel.check_update_requested.connect(self._check_update)

    # ------------------------------------------------------------------
    # Auto-save wiring
    # ------------------------------------------------------------------

    def _connect_auto_save(self) -> None:
        """Connect widget signals → auto-save after every user interaction."""
        self._db_combo.currentIndexChanged.connect(self._on_db_changed)
        self._login_edit.editingFinished.connect(self._auto_save)
        self._password_edit.editingFinished.connect(self._auto_save)
        if self._instance_combo.lineEdit() is not None:
            self._instance_combo.lineEdit().editingFinished.connect(self._auto_save)
        self._auto_update_check.toggled.connect(self._auto_save)

    # ------------------------------------------------------------------
    # Load / Save / Reset
    # ------------------------------------------------------------------

    def _load_fields(self) -> None:
        self._form_controller.load_fields()

    def _save(self) -> None:
        self._form_controller.save()
        QMessageBox.information(self, "Сохранено", "Настройки сохранены.")

    def _reset(self) -> None:
        self._load_fields()

    # ------------------------------------------------------------------
    # Auto-save helpers
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_db_changed(self, idx: int) -> None:
        self._form_controller.handle_database_changed(idx)

    def _auto_save(self) -> bool:
        return self._form_controller.auto_save()

    # ------------------------------------------------------------------
    # SQL Server — controller delegates
    # ------------------------------------------------------------------

    def _scan_instances(self) -> bool:
        return self._sql_controller.scan_instances()

    @Slot(int)
    def _on_instance_changed(self, idx: int) -> bool:
        return self._sql_controller.handle_instance_changed(idx)

    def _refresh_databases(self) -> bool:
        return self._sql_controller.refresh_databases()

    def _test_connection(self) -> bool:
        return self._sql_controller.test_connection()

    # ------------------------------------------------------------------
    # App settings
    # ------------------------------------------------------------------

    @Slot(bool)
    def _on_startup_toggled(self, checked: bool) -> None:
        self._app_controller.handle_startup_toggled(checked)

    def _check_update(self) -> bool:
        return self._app_controller.check_update()
