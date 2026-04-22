from PySide6.QtWidgets import QWidget

from app.config import ConfigManager

from app.core.updater import GITHUB_REPO
from app.ui.settings_app_controller import SettingsAppController
from app.ui.settings_actions import (
    SettingsUpdateCoordinator,
    is_startup_enabled,
)
from app.ui.settings_form_controller import SettingsFormController
from app.ui.settings_sql_controller import SettingsSqlController
from app.ui.settings_sql_flow import SettingsSqlFlowState
from app.ui.settings_widget_controller import SettingsWidgetController


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
        self._controller = SettingsWidgetController(
            shell=self._shell,
            form_controller=self._form_controller,
            sql_controller=self._sql_controller,
            app_controller=self._app_controller,
        )
        self._controller.wire()
        self._controller.load_initial_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        from app.ui.settings_shell import SettingsShell

        self._shell = SettingsShell(self._current_version, self)
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

        self._app_panel = self._shell.app_panel()
        self._startup_check = self._app_panel.startup_check()
        self._auto_update_check = self._app_panel.auto_update_check()
