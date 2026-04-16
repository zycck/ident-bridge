from PySide6.QtCore import Qt, Slot
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

from app.config import AppConfig, ConfigManager, SqlInstance
from app.core.app_logger import get_logger

from app.core.updater import GITHUB_REPO
from app.ui.lucide_icons import lucide
from app.ui.settings_actions import (
    SettingsUpdateCoordinator,
    apply_startup_toggle,
    is_startup_enabled,
)
from app.ui.settings_persistence import (
    build_connection_config,
    build_settings_payload,
    resolve_autosave_database,
)
from app.ui.settings_sql_presenters import (
    build_database_items,
    build_instance_items,
    next_instance_index,
)
from app.ui.settings_sql_flow import SettingsSqlFlowState
from app.ui.theme import Theme
from app.ui.threading import run_worker
from app.ui.settings_workers import (
    DatabaseListWorker,
    InstanceScanWorker,
    TestConnectionWorker,
    instance_from_text,
)
from app.ui.widgets import labeled_row, section, set_status, status_label, style_combo_popup

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

        # Strong Python references — prevents GC from deleting workers while
        # the underlying QThread is still running (PySide6 doesn't keep them alive)
        self._scan_worker: InstanceScanWorker | None = None
        self._dblist_worker: DatabaseListWorker | None = None
        self._test_conn_worker: TestConnectionWorker | None = None
        self._update_actions = SettingsUpdateCoordinator(
            self,
            current_version=self._current_version,
        )

        self._build_ui()
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
        self._sql_flow.begin_load()
        try:
            self._load_fields_impl()
        finally:
            self._sql_flow.end_load()

    def _load_fields_impl(self) -> None:
        cfg = self._config.load()

        # Credentials FIRST — _on_instance_changed reads them to fetch databases
        self._login_edit.setText(cfg.get("sql_user", "") or "")
        self._password_edit.setText(cfg.get("sql_password", "") or "")

        # Запоминаем сохранённую БД — _on_dblist_finished будет её восстанавливать
        saved_db = cfg.get("sql_database", "") or ""
        self._sql_flow.remember_loaded_database(saved_db)

        # SQL instance — block signals while populating, fire exactly once at end
        saved_instance = cfg.get("sql_instance", "")
        if saved_instance:
            target_idx = 0
            try:
                self._instance_combo.blockSignals(True)
                idx = self._instance_combo.findText(saved_instance)
                if idx < 0:
                    inst = instance_from_text(saved_instance)
                    if inst:
                        self._instance_combo.addItem(saved_instance, userData=inst)
                    else:
                        self._instance_combo.addItem(saved_instance)
                    idx = self._instance_combo.count() - 1
                target_idx = max(idx, 0)
            finally:
                self._instance_combo.blockSignals(False)
            self._instance_combo.setCurrentIndex(target_idx)
            self._on_instance_changed(target_idx)

        self._startup_check.blockSignals(True)
        self._startup_check.setChecked(is_startup_enabled())
        self._startup_check.blockSignals(False)
        self._auto_update_check.setChecked(bool(cfg.get("auto_update_check", True)))

    def _save(self) -> None:
        # Merge with existing config to preserve export_jobs and other fields
        cfg = self._config.load()
        db = self._sql_flow.selected_database or self._db_combo.currentText().strip()
        cfg.update(build_settings_payload(
            sql_instance=self._instance_combo.currentText().strip(),
            sql_database=db,
            sql_user=self._login_edit.text().strip(),
            sql_password=self._password_edit.text(),
            auto_update_check=self._auto_update_check.isChecked(),
            run_on_startup=self._startup_check.isChecked(),
            github_repo=GITHUB_REPO,
        ))
        self._config.save(cfg)
        QMessageBox.information(self, "Сохранено", "Настройки сохранены.")

    def _reset(self) -> None:
        self._load_fields()

    # ------------------------------------------------------------------
    # Auto-save helpers
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_db_changed(self, idx: int) -> None:
        """Track DB selection in memory and trigger auto-save."""
        text = self._db_combo.itemText(idx)
        self._sql_flow.remember_database_selection(text)
        self._auto_save()

    def _auto_save(self) -> None:
        """Silently persist current field values; called on every user interaction."""
        if self._sql_flow.should_skip_autosave():
            return

        db = resolve_autosave_database(
            self._sql_flow.selected_database,
            self._db_combo.currentText().strip(),
        )

        self._config.update(**build_settings_payload(
            sql_instance=self._instance_combo.currentText().strip(),
            sql_database=db,
            sql_user=self._login_edit.text().strip(),
            sql_password=self._password_edit.text(),
            auto_update_check=self._auto_update_check.isChecked(),
            run_on_startup=self._startup_check.isChecked(),
            github_repo=GITHUB_REPO,
        ))
        _log.debug("Auto-saved settings")

    # ------------------------------------------------------------------
    # SQL Server — instance scan
    # ------------------------------------------------------------------

    def _scan_instances(self) -> None:
        if not self._sql_flow.begin_scan():
            return

        self._instance_combo.clear()
        self._instance_combo.addItem("Сканирование…")
        self._instance_combo.setEnabled(False)

        worker = InstanceScanWorker()
        run_worker(
            self,
            worker,
            pin_attr="_scan_worker",
            on_finished=self._on_scan_finished,
            on_error=self._on_scan_error,
        )

    @Slot(list)
    def _on_scan_finished(self, instances: list[SqlInstance]) -> None:
        self._sql_flow.finish_scan()

        try:
            self._instance_combo.blockSignals(True)
            self._instance_combo.setEnabled(True)
            self._instance_combo.clear()

            if not instances:
                self._instance_combo.addItem("Нет экземпляров")
                return

            cfg = self._config.load()
            saved = cfg.get("sql_instance", "")
            items, target_idx = build_instance_items(
                instances,
                saved_instance=saved,
            )
            for label, inst in items:
                self._instance_combo.addItem(label, userData=inst)
        finally:
            self._instance_combo.blockSignals(False)

        self._instance_combo.setCurrentIndex(target_idx)
        self._on_instance_changed(target_idx)

    @Slot(str)
    def _on_scan_error(self, message: str) -> None:
        self._sql_flow.fail_scan()
        self._instance_combo.setEnabled(True)
        self._instance_combo.clear()
        self._instance_combo.addItem("Ошибка сканирования")
        set_status(self._conn_status, "error", f"Сканирование: {message}")

    # ------------------------------------------------------------------
    # SQL Server — database list
    # ------------------------------------------------------------------

    def _on_instance_changed(self, idx: int) -> None:
        inst = self._instance_combo.itemData(idx)
        if inst is None:
            inst = instance_from_text(self._instance_combo.itemText(idx))
            if inst is None:
                return
            self._instance_combo.setItemData(idx, inst)
        self._fetch_databases(inst)

    def _refresh_databases(self) -> None:
        idx = self._instance_combo.currentIndex()
        inst = self._instance_combo.itemData(idx)
        if inst is None:
            inst = instance_from_text(self._instance_combo.currentText())
        if inst is None:
            return
        self._fetch_databases(inst)

    def _fetch_databases(self, inst: SqlInstance) -> None:
        if not self._sql_flow.begin_database_fetch(inst):
            return

        self._db_combo.clear()
        self._db_combo.addItem("Загрузка…")
        self._db_combo.setEnabled(False)

        user = self._login_edit.text().strip()
        password = self._password_edit.text()

        worker = DatabaseListWorker(inst, user, password)
        run_worker(
            self,
            worker,
            pin_attr="_dblist_worker",
            on_finished=self._on_dblist_finished,
            on_error=self._on_dblist_error,
        )

    @Slot(list)
    def _on_dblist_finished(self, databases: list[str]) -> None:
        restore, pending = self._sql_flow.finish_database_fetch(
            saved_database=self._config.load().get("sql_database", "") or "",
        )
        items, final_idx = build_database_items(databases, restore=restore)

        self._db_combo.blockSignals(True)
        self._db_combo.clear()
        self._db_combo.setEnabled(True)

        for db in items:
            self._db_combo.addItem(db)

        self._db_combo.blockSignals(False)

        if self._db_combo.count() > 0:
            if self._db_combo.currentIndex() != final_idx:
                self._db_combo.setCurrentIndex(final_idx)
            else:
                self._on_db_changed(final_idx)

        if pending is not None:
            self._fetch_databases(pending)

    @Slot(str)
    def _on_dblist_error(self, message: str) -> None:
        pending = self._sql_flow.fail_database_fetch()

        self._db_combo.clear()
        self._db_combo.setEnabled(True)
        set_status(self._conn_status, "error", f"Список БД: {message}")

        if pending is not None:
            self._fetch_databases(pending)
        else:
            cur = self._instance_combo.currentIndex()
            nxt = next_instance_index(
                current_index=cur,
                total_count=self._instance_combo.count(),
            )
            if nxt is not None:
                next_inst = self._instance_combo.itemData(nxt)
                if next_inst is not None:
                    _log.debug("Auto-advancing to next instance: %s", next_inst.display)
                    self._instance_combo.blockSignals(True)
                    self._instance_combo.setCurrentIndex(nxt)
                    self._instance_combo.blockSignals(False)
                    self._fetch_databases(next_inst)

    # ------------------------------------------------------------------
    # SQL Server — test connection
    # ------------------------------------------------------------------

    def _test_connection(self) -> None:
        if not self._sql_flow.begin_connection_test():
            return

        cfg = build_connection_config(
            sql_instance=self._instance_combo.currentText().strip(),
            sql_database=self._db_combo.currentText().strip(),
            sql_user=self._login_edit.text().strip(),
            sql_password=self._password_edit.text(),
        )
        set_status(self._conn_status, "neutral", "Проверка подключения…")

        worker = TestConnectionWorker(cfg)
        run_worker(
            self,
            worker,
            pin_attr="_test_conn_worker",
            on_finished=self._on_test_conn_finished,
        )

    @Slot(bool, str)
    def _on_test_conn_finished(self, ok: bool, message: str) -> None:
        self._sql_flow.finish_connection_test()
        if ok:
            set_status(self._conn_status, "ok", message or "Подключение успешно")
        else:
            set_status(self._conn_status, "error", message or "Ошибка подключения")

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
