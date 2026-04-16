from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigManager
from app.core.app_logger import get_logger

from app.core.updater import GITHUB_REPO
from app.ui.lucide_icons import lucide
from app.ui.settings_actions import (
    SettingsUpdateCoordinator,
    apply_startup_toggle,
    is_startup_enabled,
)
from app.ui.settings_form_controller import SettingsFormController
from app.ui.settings_sql_controller import SettingsSqlController
from app.ui.settings_sql_flow import SettingsSqlFlowState
from app.ui.theme import Theme
from app.ui.widgets import labeled_row, section, status_label, style_combo_popup

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

        # ── Section 1: SQL Server ─────────────────────────────────────
        sql_box, sql_lay = section("SQL Server")

        # Instance row
        self._instance_combo = QComboBox()
        style_combo_popup(self._instance_combo)
        self._instance_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._instance_combo.setEditable(True)
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)

        scan_btn = QPushButton("  Сканировать")
        scan_btn.setIcon(lucide('search', color=Theme.gray_700, size=14))
        scan_btn.clicked.connect(self._scan_instances)

        inst_row = QHBoxLayout()
        inst_row.setSpacing(6)
        inst_lbl = QLabel("SQL Instance")
        inst_lbl.setFixedWidth(100)
        inst_lbl.setStyleSheet("color: #9CA3AF;")
        inst_row.addWidget(inst_lbl)
        inst_row.addWidget(self._instance_combo, stretch=1)
        inst_row.addWidget(scan_btn)
        sql_lay.addLayout(inst_row)

        # Database row
        self._db_combo = QComboBox()
        style_combo_popup(self._db_combo)
        self._db_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        refresh_db_btn = QPushButton()
        refresh_db_btn.setIcon(lucide('refresh-cw', color=Theme.gray_700, size=14))
        refresh_db_btn.setFixedWidth(28)
        refresh_db_btn.setToolTip("Обновить список баз данных")
        refresh_db_btn.clicked.connect(self._refresh_databases)

        db_row = QHBoxLayout()
        db_row.setSpacing(6)
        db_lbl = QLabel("База данных")
        db_lbl.setFixedWidth(100)
        db_lbl.setStyleSheet("color: #9CA3AF;")
        db_row.addWidget(db_lbl)
        db_row.addWidget(self._db_combo, stretch=1)
        db_row.addWidget(refresh_db_btn)
        sql_lay.addLayout(db_row)

        self._login_edit = QLineEdit()
        self._login_edit.setPlaceholderText("sa")
        sql_lay.addLayout(labeled_row("Логин", self._login_edit))

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("••••••")
        sql_lay.addLayout(labeled_row("Пароль", self._password_edit))

        test_conn_btn = QPushButton("  Тест подключения")
        test_conn_btn.setObjectName("primaryBtn")
        test_conn_btn.setIcon(lucide('zap', color=Theme.gray_900, size=14))
        test_conn_btn.clicked.connect(self._test_connection)
        sql_lay.addWidget(test_conn_btn)

        self._conn_status = status_label()
        sql_lay.addWidget(self._conn_status)

        layout.addWidget(sql_box)

        # ── Section 2: Приложение ─────────────────────────────────────
        app_box, app_lay = section("Приложение")

        self._startup_check = QCheckBox("Запускать с Windows")
        self._startup_check.toggled.connect(self._on_startup_toggled)
        app_lay.addWidget(self._startup_check)

        self._auto_update_check = QCheckBox("Проверять обновления при запуске")
        app_lay.addWidget(self._auto_update_check)

        version_lbl = QLabel(f"Версия: {self._current_version}")
        version_lbl.setStyleSheet("color: #3F3F46; font-size: 9pt;")
        app_lay.addWidget(version_lbl)

        check_update_btn = QPushButton("  Проверить обновление")
        check_update_btn.setIcon(lucide('download-cloud', color=Theme.gray_700, size=14))
        check_update_btn.clicked.connect(self._check_update)
        app_lay.addWidget(check_update_btn)

        layout.addWidget(app_box)

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

    @Slot(str, str)
    def _on_update_available(self, tag: str, download_url: str) -> None:
        self._update_actions._on_update_available(tag, download_url)

    @Slot()
    def _on_no_update(self) -> None:
        self._update_actions._on_no_update()

    @Slot(str)
    def _on_update_error(self, message: str) -> None:
        self._update_actions._on_update_error(message)
