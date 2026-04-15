from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, ConfigManager, SqlInstance
from app.core import startup as StartupManager
from app.core.instance_scanner import list_databases, scan_all
from app.core.sql_client import SqlClient
from app.core.telegram import TelegramNotifier
from app.core.updater import GITHUB_REPO
from app.workers.update_worker import UpdateWorker


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _make_section(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    """Return a titled QGroupBox and its inner QVBoxLayout."""
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setSpacing(6)
    layout.setContentsMargins(10, 12, 10, 10)
    return box, layout


def _make_row(label_text: str, widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setFixedWidth(140)
    row.addWidget(lbl)
    row.addWidget(widget, stretch=1)
    return row


def _status_label() -> QLabel:
    lbl = QLabel()
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return lbl


def _set_status(lbl: QLabel, ok: bool, text: str) -> None:
    color = "#22C55E" if ok else "#EF4444"
    lbl.setStyleSheet(f"color: {color};")
    lbl.setText(text)


# ---------------------------------------------------------------------------
# Background scanner worker
# ---------------------------------------------------------------------------

class _InstanceScanWorker(QObject):
    finished: Signal = Signal(list)   # list[SqlInstance]
    error: Signal = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            instances = scan_all()
            self.finished.emit(instances)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# SettingsWidget
# ---------------------------------------------------------------------------

class SettingsWidget(QWidget):
    """Full settings panel rendered inside a QScrollArea."""

    def __init__(
        self,
        config: ConfigManager,
        current_version: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._current_version = current_version

        # Worker bookkeeping (kept alive while thread runs)
        self._scan_thread: QThread | None = None
        self._scan_worker: _InstanceScanWorker | None = None
        self._update_thread: QThread | None = None
        self._update_worker: UpdateWorker | None = None

        self._build_ui()
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
        layout.setSpacing(14)
        layout.setContentsMargins(12, 12, 12, 12)

        # -- Section 1: SQL Server ----------------------------------------
        sql_box, sql_lay = _make_section("SQL Server")

        self._instance_combo = QComboBox()
        self._instance_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)

        scan_btn = QPushButton("Сканировать")
        scan_btn.setFixedWidth(120)
        scan_btn.clicked.connect(self._scan_instances)

        inst_row = QHBoxLayout()
        inst_row.addWidget(QLabel("SQL Instance"))
        inst_row.addWidget(self._instance_combo, stretch=1)
        inst_row.addWidget(scan_btn)
        sql_lay.addLayout(inst_row)

        self._db_combo = QComboBox()
        sql_lay.addLayout(_make_row("База данных", self._db_combo))

        self._login_edit = QLineEdit()
        self._login_edit.setPlaceholderText("sa")
        sql_lay.addLayout(_make_row("Логин", self._login_edit))

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("••••••")
        sql_lay.addLayout(_make_row("Пароль", self._password_edit))

        test_conn_btn = QPushButton("Тест подключения")
        test_conn_btn.clicked.connect(self._test_connection)
        sql_lay.addWidget(test_conn_btn)

        self._conn_status = _status_label()
        sql_lay.addWidget(self._conn_status)

        self._query_edit = QPlainTextEdit()
        self._query_edit.setPlaceholderText("SELECT … FROM …")
        self._query_edit.setFixedHeight(72)
        sql_lay.addLayout(_make_row("SQL запрос", self._query_edit))

        layout.addWidget(sql_box)

        # -- Section 2: Расписание ----------------------------------------
        sched_box, sched_lay = _make_section("Расписание")

        self._sched_enabled = QCheckBox("Включить расписание")
        sched_lay.addWidget(self._sched_enabled)

        self._sched_mode_combo = QComboBox()
        self._sched_mode_combo.addItems([
            "daily — по времени",
            "hourly — каждые N часов",
        ])
        self._sched_mode_combo.currentIndexChanged.connect(self._on_sched_mode_changed)
        sched_lay.addLayout(_make_row("Режим", self._sched_mode_combo))

        self._sched_value_edit = QLineEdit()
        self._sched_value_edit.setPlaceholderText("ЧЧ:ММ")
        sched_lay.addLayout(_make_row("Значение", self._sched_value_edit))

        self._next_run_label = QLabel("Следующий запуск: —")
        self._next_run_label.setStyleSheet("color: #6B7280;")
        sched_lay.addWidget(self._next_run_label)

        layout.addWidget(sched_box)

        # -- Section 3: Экспорт -------------------------------------------
        export_box, export_lay = _make_section("Экспорт")

        self._webhook_edit = QLineEdit()
        self._webhook_edit.setPlaceholderText("https://...")
        export_lay.addLayout(_make_row("Webhook URL", self._webhook_edit))

        sheets_stub = QLabel("Google Sheets webhook (скоро)")
        sheets_stub.setStyleSheet("color: #9CA3AF; font-style: italic;")
        export_lay.addWidget(sheets_stub)

        layout.addWidget(export_box)

        # -- Section 4: Telegram ------------------------------------------
        tg_box, tg_lay = _make_section("Telegram")

        self._tg_token_edit = QLineEdit()
        self._tg_token_edit.setPlaceholderText("123456:ABC-DEF...")
        tg_lay.addLayout(_make_row("Bot Token", self._tg_token_edit))

        self._tg_chat_id_edit = QLineEdit()
        self._tg_chat_id_edit.setPlaceholderText("-100...")
        tg_lay.addLayout(_make_row("Chat ID", self._tg_chat_id_edit))

        test_tg_btn = QPushButton("Тест Telegram")
        test_tg_btn.clicked.connect(self._test_telegram)
        tg_lay.addWidget(test_tg_btn)

        self._tg_status = _status_label()
        tg_lay.addWidget(self._tg_status)

        layout.addWidget(tg_box)

        # -- Section 5: Приложение ----------------------------------------
        app_box, app_lay = _make_section("Приложение")

        self._startup_check = QCheckBox("Запускать с Windows")
        self._startup_check.toggled.connect(self._on_startup_toggled)
        app_lay.addWidget(self._startup_check)

        self._auto_update_check = QCheckBox("Проверять обновления при запуске")
        app_lay.addWidget(self._auto_update_check)

        version_lbl = QLabel(f"Версия: {self._current_version}")
        version_lbl.setStyleSheet("color: #6B7280;")
        app_lay.addWidget(version_lbl)

        check_update_btn = QPushButton("Проверить обновление")
        check_update_btn.clicked.connect(self._check_update)
        app_lay.addWidget(check_update_btn)

        layout.addWidget(app_box)

        # -- Bottom button row --------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        reset_btn = QPushButton("Сбросить")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)

        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Load / Save / Reset
    # ------------------------------------------------------------------

    def _load_fields(self) -> None:
        cfg = self._config.load()

        # SQL Server
        saved_instance = cfg.get("sql_instance", "")
        if saved_instance:
            idx = self._instance_combo.findText(saved_instance)
            if idx >= 0:
                self._instance_combo.setCurrentIndex(idx)
            else:
                self._instance_combo.addItem(saved_instance)
                self._instance_combo.setCurrentText(saved_instance)

        saved_db = cfg.get("sql_database", "")
        if saved_db:
            db_idx = self._db_combo.findText(saved_db)
            if db_idx >= 0:
                self._db_combo.setCurrentIndex(db_idx)
            else:
                self._db_combo.addItem(saved_db)
                self._db_combo.setCurrentText(saved_db)

        self._login_edit.setText(cfg.get("sql_user", "") or "")
        self._password_edit.setText(cfg.get("sql_password", "") or "")
        self._query_edit.setPlainText(cfg.get("sql_query", "") or "")  # type: ignore[arg-type]

        # Schedule
        self._sched_enabled.setChecked(bool(cfg.get("schedule_enabled", False)))
        mode = cfg.get("schedule_mode", "daily") or "daily"
        mode_index = 1 if mode == "hourly" else 0
        self._sched_mode_combo.setCurrentIndex(mode_index)
        self._sched_value_edit.setText(cfg.get("schedule_value", "") or "")
        self._on_sched_mode_changed(mode_index)

        # Export
        self._webhook_edit.setText(cfg.get("webhook_url", "") or "")

        # Telegram
        self._tg_token_edit.setText(cfg.get("tg_token", "") or "")
        self._tg_chat_id_edit.setText(cfg.get("tg_chat_id", "") or "")

        # App
        self._startup_check.blockSignals(True)
        self._startup_check.setChecked(StartupManager.is_registered())
        self._startup_check.blockSignals(False)

        self._auto_update_check.setChecked(bool(cfg.get("auto_update_check", True)))

    def _save(self) -> None:
        mode_index = self._sched_mode_combo.currentIndex()
        schedule_mode = "hourly" if mode_index == 1 else "daily"
        schedule_value = self._sched_value_edit.text().strip()

        if self._sched_enabled.isChecked():
            if schedule_mode == "daily":
                import re
                if not re.fullmatch(r"\d{1,2}:\d{2}", schedule_value):
                    QMessageBox.warning(self, "Ошибка", "Формат времени: ЧЧ:ММ (например, 09:30)")
                    return
            else:  # hourly
                if not schedule_value.isdigit() or int(schedule_value) < 1:
                    QMessageBox.warning(self, "Ошибка", "Введите целое число часов (≥ 1)")
                    return

        cfg: AppConfig = {
            "sql_instance": self._instance_combo.currentText().strip(),
            "sql_database": self._db_combo.currentText().strip(),
            "sql_user": self._login_edit.text().strip(),
            "sql_password": self._password_edit.text(),
            "sql_query": self._query_edit.toPlainText().strip(),  # type: ignore[typeddict-unknown-key]
            "webhook_url": self._webhook_edit.text().strip(),
            "tg_token": self._tg_token_edit.text().strip(),
            "tg_chat_id": self._tg_chat_id_edit.text().strip(),
            "schedule_enabled": self._sched_enabled.isChecked(),
            "schedule_mode": schedule_mode,
            "schedule_value": schedule_value,
            "auto_update_check": self._auto_update_check.isChecked(),
            "run_on_startup": self._startup_check.isChecked(),
            "github_repo": GITHUB_REPO,
        }
        self._config.save(cfg)

        QMessageBox.information(self, "Сохранено", "Настройки сохранены.")

    def _reset(self) -> None:
        self._load_fields()

    # ------------------------------------------------------------------
    # Schedule mode
    # ------------------------------------------------------------------

    def _on_sched_mode_changed(self, index: int) -> None:
        if index == 1:  # hourly
            self._sched_value_edit.setPlaceholderText("N (часов)")
        else:           # daily
            self._sched_value_edit.setPlaceholderText("ЧЧ:ММ")

    def set_next_run_text(self, text: str) -> None:
        """Update the next-run info label (called externally by scheduler)."""
        self._next_run_label.setText(f"Следующий запуск: {text}")

    # ------------------------------------------------------------------
    # Section 1 — SQL
    # ------------------------------------------------------------------

    def _scan_instances(self) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            return

        self._instance_combo.clear()
        self._instance_combo.addItem("Сканирование…")
        self._instance_combo.setEnabled(False)

        worker = _InstanceScanWorker()
        thread = QThread(self)
        worker.moveToThread(thread)

        worker.finished.connect(self._on_scan_finished)
        worker.error.connect(self._on_scan_error)
        thread.started.connect(worker.run)

        # Clean up after thread finishes
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._scan_worker = worker
        self._scan_thread = thread
        thread.start()

    @Slot(list)
    def _on_scan_finished(self, instances: list[SqlInstance]) -> None:
        self._instance_combo.setEnabled(True)
        self._instance_combo.clear()

        if not instances:
            self._instance_combo.addItem("Нет экземпляров")
            return

        cfg = self._config.load()
        saved = cfg.get("sql_instance", "")

        for inst in instances:
            self._instance_combo.addItem(inst.display, userData=inst)

        if saved:
            idx = self._instance_combo.findText(saved)
            if idx >= 0:
                self._instance_combo.setCurrentIndex(idx)

    @Slot(str)
    def _on_scan_error(self, message: str) -> None:
        self._instance_combo.setEnabled(True)
        self._instance_combo.clear()
        self._instance_combo.addItem("Ошибка сканирования")
        _set_status(self._conn_status, False, f"Сканирование: {message}")

    def _on_instance_changed(self, idx: int) -> None:
        self._db_combo.clear()
        inst = self._instance_combo.itemData(idx)
        if inst is None:
            return

        user = self._login_edit.text().strip()
        password = self._password_edit.text()
        databases = list_databases(inst, user, password)
        for db in databases:
            self._db_combo.addItem(db)

        cfg = self._config.load()
        saved_db = cfg.get("sql_database", "")
        if saved_db:
            db_idx = self._db_combo.findText(saved_db)
            if db_idx >= 0:
                self._db_combo.setCurrentIndex(db_idx)

    def _test_connection(self) -> None:
        cfg: AppConfig = {
            "sql_instance": self._instance_combo.currentText().strip(),
            "sql_database": self._db_combo.currentText().strip(),
            "sql_user": self._login_edit.text().strip(),
            "sql_password": self._password_edit.text(),
        }
        client = SqlClient(cfg)
        ok, message = client.test_connection()
        if ok:
            _set_status(self._conn_status, True, "Подключение успешно")
        else:
            _set_status(self._conn_status, False, message or "Ошибка подключения")

    # ------------------------------------------------------------------
    # Section 4 — Telegram
    # ------------------------------------------------------------------

    def _test_telegram(self) -> None:
        token = self._tg_token_edit.text().strip()
        chat_id = self._tg_chat_id_edit.text().strip()

        if not token or not chat_id:
            _set_status(self._tg_status, False, "Заполните Token и Chat ID")
            return

        notifier = TelegramNotifier(token, chat_id)
        ok, message = notifier.test()
        if ok:
            _set_status(self._tg_status, True, "Telegram: сообщение отправлено")
        else:
            _set_status(self._tg_status, False, message or "Ошибка Telegram")

    # ------------------------------------------------------------------
    # Section 5 — App
    # ------------------------------------------------------------------

    def _on_startup_toggled(self, checked: bool) -> None:
        if checked:
            ok, err = StartupManager.register()
        else:
            ok, err = StartupManager.unregister()

        if not ok:
            # Roll back the checkbox silently and inform the user
            self._startup_check.blockSignals(True)
            self._startup_check.setChecked(not checked)
            self._startup_check.blockSignals(False)
            QMessageBox.warning(
                self,
                "Автозапуск",
                f"Не удалось изменить запись в реестре:\n{err}",
            )

    def _check_update(self) -> None:
        if self._update_thread and self._update_thread.isRunning():
            return

        worker = UpdateWorker(
            current_version=self._current_version,
            repo=GITHUB_REPO,
        )
        thread = QThread(self)
        worker.moveToThread(thread)

        worker.update_available.connect(self._on_update_available)
        worker.no_update.connect(self._on_no_update)
        worker.error.connect(self._on_update_error)

        thread.started.connect(worker.check)
        worker.update_available.connect(thread.quit)
        worker.no_update.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._update_worker = worker
        self._update_thread = thread
        thread.start()

    @Slot(str, str)
    def _on_update_available(self, tag: str, download_url: str) -> None:
        QMessageBox.information(
            self,
            "Доступно обновление",
            f"Новая версия {tag} доступна.\n\nСсылка: {download_url}",
        )

    @Slot()
    def _on_no_update(self) -> None:
        QMessageBox.information(
            self,
            "Обновлений нет",
            f"Установлена актуальная версия ({self._current_version}).",
        )

    @Slot(str)
    def _on_update_error(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "Ошибка проверки обновлений",
            message,
        )
