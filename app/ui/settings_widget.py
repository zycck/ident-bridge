from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigManager
from app.core.app_logger import get_logger

from app.core.updater import GITHUB_REPO
from app.ui.lucide_icons import lucide
from app.ui.settings_app_panel import SettingsAppPanel
from app.ui.settings_actions import (
    SettingsUpdateCoordinator,
    apply_startup_toggle,
    is_startup_enabled,
)
from app.ui.settings_form_controller import SettingsFormController
from app.ui.settings_sql_controller import SettingsSqlController
from app.ui.settings_sql_flow import SettingsSqlFlowState
from app.ui.settings_sql_panel import SettingsSqlPanel
from app.ui.theme import Theme

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
        self._connect_auto_save()
        self._load_fields()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        self._sql_panel = SettingsSqlPanel(self)
        self._instance_combo = self._sql_panel.instance_combo()
        self._db_combo = self._sql_panel.database_combo()
        self._login_edit = self._sql_panel.login_edit()
        self._password_edit = self._sql_panel.password_edit()
        self._conn_status = self._sql_panel.conn_status()
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        self._sql_panel.scan_requested.connect(self._scan_instances)
        self._sql_panel.refresh_databases_requested.connect(self._refresh_databases)
        self._sql_panel.test_connection_requested.connect(self._test_connection)
        layout.addWidget(self._sql_panel)

        self._app_panel = SettingsAppPanel(self._current_version, self)
        self._startup_check = self._app_panel.startup_check()
        self._auto_update_check = self._app_panel.auto_update_check()
        self._app_panel.startup_toggled.connect(self._on_startup_toggled)
        self._app_panel.check_update_requested.connect(self._check_update)
        layout.addWidget(self._app_panel)

        # ── Bottom buttons ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addStretch()

        reset_btn = QPushButton("  Сбросить")
        reset_btn.setIcon(lucide('rotate-ccw', color=Theme.gray_700, size=14))
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)

        save_btn = QPushButton("  Сохранить")
        save_btn.setObjectName("primaryBtn")
        save_btn.setIcon(lucide('save', color=Theme.gray_900, size=14))
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)
        layout.addStretch()

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
        result = apply_startup_toggle(checked)
        if not result.ok:
            self._startup_check.blockSignals(True)
            self._startup_check.setChecked(not checked)
            self._startup_check.blockSignals(False)
            QMessageBox.warning(
                self, "Автозапуск",
                f"Не удалось изменить запись в реестре:\n{result.error}",
            )

    def _check_update(self) -> None:
        self._update_actions.check()
