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

import logging

from app.config import AppConfig, ConfigManager, SqlInstance
from app.core import startup as StartupManager
from app.core.app_logger import get_logger
from app.core.instance_scanner import list_databases, scan_all
from app.core.sql_client import SqlClient
from app.core.telegram import TelegramNotifier
from app.core.updater import GITHUB_REPO
from app.workers.update_worker import UpdateWorker

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _make_section(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setSpacing(8)
    layout.setContentsMargins(12, 14, 12, 12)
    return box, layout


def _make_row(label_text: str, widget: QWidget, label_width: int = 120) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(10)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(label_width)
    lbl.setStyleSheet("color: #9CA3AF;")
    row.addWidget(lbl)
    row.addWidget(widget, stretch=1)
    return row


def _status_label() -> QLabel:
    lbl = QLabel()
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lbl.setStyleSheet("font-size: 9pt; padding: 2px 0;")
    return lbl


def _set_status(lbl: QLabel, ok: bool | None, text: str) -> None:
    if ok is True:
        color = "#34D399"
    elif ok is False:
        color = "#F87171"
    else:
        color = "#9CA3AF"
    lbl.setStyleSheet(f"color: {color}; font-size: 9pt; padding: 2px 0;")
    lbl.setText(text)


def _instance_from_text(text: str) -> SqlInstance | None:
    text = text.strip()
    if not text or text in (
        "Сканирование…", "Нет экземпляров", "Ошибка сканирования", "Загрузка…"
    ):
        return None
    parts = text.split("\\", 1)
    host = parts[0].strip()
    name = parts[1].strip() if len(parts) > 1 else ""
    return SqlInstance(name=name, host=host, display=text)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _InstanceScanWorker(QObject):
    finished: Signal = Signal(list)
    error: Signal = Signal(str)

    @Slot()
    def run(self) -> None:
        _log.debug("Scanning SQL instances…")
        try:
            instances = scan_all()
            _log.info("Instance scan done: %d found", len(instances))
            self.finished.emit(instances)
        except Exception as exc:
            _log.error("Instance scan failed: %s", exc)
            self.error.emit(str(exc))


class _DbListWorker(QObject):
    finished: Signal = Signal(list)
    error: Signal = Signal(str)

    def __init__(self, inst: SqlInstance, user: str, password: str) -> None:
        super().__init__()
        self._inst = inst
        self._user = user
        self._password = password

    @Slot()
    def run(self) -> None:
        _log.debug("Fetching databases for %s", self._inst.display)
        try:
            dbs = list_databases(self._inst, self._user, self._password)
            _log.info("Database list for %s: %d entries", self._inst.display, len(dbs))
            self.finished.emit(dbs)
        except Exception as exc:
            _log.error("Database list failed (%s): %s", self._inst.display, exc)
            self.error.emit(str(exc))


class _TestConnWorker(QObject):
    finished: Signal = Signal(bool, str)

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self._cfg = cfg

    @Slot()
    def run(self) -> None:
        _log.debug("Testing SQL connection to %s", self._cfg.get("sql_instance"))
        client = SqlClient(self._cfg)
        ok, msg = client.test_connection()
        if ok:
            _log.info("SQL connection test passed")
        else:
            _log.warning("SQL connection test failed: %s", msg)
        self.finished.emit(ok, msg or "")


class _TestTgWorker(QObject):
    finished: Signal = Signal(bool, str)

    def __init__(self, token: str, chat_id: str) -> None:
        super().__init__()
        self._token = token
        self._chat_id = chat_id

    @Slot()
    def run(self) -> None:
        _log.debug("Testing Telegram notification")
        notifier = TelegramNotifier(self._token, self._chat_id)
        ok, msg = notifier.test()
        if ok:
            _log.info("Telegram test passed")
        else:
            _log.warning("Telegram test failed: %s", msg)
        self.finished.emit(ok, msg)


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

        self._scan_running = False
        self._dblist_running = False
        self._test_conn_running = False
        self._test_tg_running = False
        self._update_running = False

        # If instance changes while a db-list fetch is in-flight, store the new
        # target here and re-fetch as soon as the current fetch finishes/errors.
        self._dblist_pending: SqlInstance | None = None

        # Strong Python references — prevents GC from deleting workers while
        # the underlying QThread is still running (PySide6 doesn't keep them alive)
        self._scan_worker: _InstanceScanWorker | None = None
        self._dblist_worker: _DbListWorker | None = None
        self._test_conn_worker: _TestConnWorker | None = None
        self._test_tg_worker: _TestTgWorker | None = None
        self._update_worker: object | None = None

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
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Section 1: SQL Server ─────────────────────────────────────
        sql_box, sql_lay = _make_section("SQL Server")

        # Instance row
        self._instance_combo = QComboBox()
        self._instance_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._instance_combo.setEditable(True)
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)

        scan_btn = QPushButton("Сканировать")
        scan_btn.setFixedWidth(110)
        scan_btn.clicked.connect(self._scan_instances)

        inst_row = QHBoxLayout()
        inst_row.setSpacing(8)
        inst_lbl = QLabel("SQL Instance")
        inst_lbl.setFixedWidth(120)
        inst_lbl.setStyleSheet("color: #9CA3AF;")
        inst_row.addWidget(inst_lbl)
        inst_row.addWidget(self._instance_combo, stretch=1)
        inst_row.addWidget(scan_btn)
        sql_lay.addLayout(inst_row)

        # Database row
        self._db_combo = QComboBox()
        self._db_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        refresh_db_btn = QPushButton("↻")
        refresh_db_btn.setFixedWidth(34)
        refresh_db_btn.setToolTip("Обновить список баз данных")
        refresh_db_btn.clicked.connect(self._refresh_databases)

        db_row = QHBoxLayout()
        db_row.setSpacing(8)
        db_lbl = QLabel("База данных")
        db_lbl.setFixedWidth(120)
        db_lbl.setStyleSheet("color: #9CA3AF;")
        db_row.addWidget(db_lbl)
        db_row.addWidget(self._db_combo, stretch=1)
        db_row.addWidget(refresh_db_btn)
        sql_lay.addLayout(db_row)

        self._login_edit = QLineEdit()
        self._login_edit.setPlaceholderText("sa")
        sql_lay.addLayout(_make_row("Логин", self._login_edit))

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("••••••")
        sql_lay.addLayout(_make_row("Пароль", self._password_edit))

        test_conn_btn = QPushButton("Тест подключения")
        test_conn_btn.setObjectName("primaryBtn")
        test_conn_btn.clicked.connect(self._test_connection)
        sql_lay.addWidget(test_conn_btn)

        self._conn_status = _status_label()
        sql_lay.addWidget(self._conn_status)

        self._query_edit = QPlainTextEdit()
        self._query_edit.setPlaceholderText("SELECT … FROM …")
        self._query_edit.setFixedHeight(76)
        sql_lay.addLayout(_make_row("SQL запрос", self._query_edit))

        layout.addWidget(sql_box)

        # ── Section 2: Расписание ─────────────────────────────────────
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
        self._next_run_label.setStyleSheet("color: #52525B; font-size: 9pt;")
        sched_lay.addWidget(self._next_run_label)

        layout.addWidget(sched_box)

        # ── Section 3: Экспорт ────────────────────────────────────────
        export_box, export_lay = _make_section("Экспорт")

        self._webhook_edit = QLineEdit()
        self._webhook_edit.setPlaceholderText("https://...")
        export_lay.addLayout(_make_row("Webhook URL", self._webhook_edit))

        sheets_stub = QLabel("Google Sheets webhook (скоро)")
        sheets_stub.setStyleSheet("color: #3F3F46; font-style: italic; font-size: 9pt;")
        export_lay.addWidget(sheets_stub)

        layout.addWidget(export_box)

        # ── Section 4: Telegram ───────────────────────────────────────
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

        # ── Section 5: Приложение ─────────────────────────────────────
        app_box, app_lay = _make_section("Приложение")

        self._startup_check = QCheckBox("Запускать с Windows")
        self._startup_check.toggled.connect(self._on_startup_toggled)
        app_lay.addWidget(self._startup_check)

        self._auto_update_check = QCheckBox("Проверять обновления при запуске")
        app_lay.addWidget(self._auto_update_check)

        version_lbl = QLabel(f"Версия: {self._current_version}")
        version_lbl.setStyleSheet("color: #3F3F46; font-size: 9pt;")
        app_lay.addWidget(version_lbl)

        check_update_btn = QPushButton("Проверить обновление")
        check_update_btn.clicked.connect(self._check_update)
        app_lay.addWidget(check_update_btn)

        layout.addWidget(app_box)

        # ── Bottom buttons ────────────────────────────────────────────
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

        # Credentials FIRST — _on_instance_changed reads them to fetch databases
        self._login_edit.setText(cfg.get("sql_user", "") or "")
        self._password_edit.setText(cfg.get("sql_password", "") or "")

        # SQL instance — block signals while populating, fire exactly once at end
        saved_instance = cfg.get("sql_instance", "")
        if saved_instance:
            target_idx = 0
            try:
                self._instance_combo.blockSignals(True)
                idx = self._instance_combo.findText(saved_instance)
                if idx < 0:
                    inst = _instance_from_text(saved_instance)
                    if inst:
                        self._instance_combo.addItem(saved_instance, userData=inst)
                    else:
                        self._instance_combo.addItem(saved_instance)
                    idx = self._instance_combo.count() - 1
                target_idx = max(idx, 0)
            finally:
                self._instance_combo.blockSignals(False)
            self._instance_combo.setCurrentIndex(target_idx)
            # Qt sets currentIndex=0 during addItem even with signals blocked,
            # so setCurrentIndex(0) emits nothing. Always trigger fetch explicitly.
            self._on_instance_changed(target_idx)

        saved_db = cfg.get("sql_database", "")
        if saved_db:
            db_idx = self._db_combo.findText(saved_db)
            if db_idx >= 0:
                self._db_combo.setCurrentIndex(db_idx)
            else:
                self._db_combo.addItem(saved_db)
                self._db_combo.setCurrentText(saved_db)
        self._query_edit.setPlainText(cfg.get("sql_query", "") or "")  # type: ignore[arg-type]

        self._sched_enabled.setChecked(bool(cfg.get("schedule_enabled", False)))
        mode = cfg.get("schedule_mode", "daily") or "daily"
        mode_index = 1 if mode == "hourly" else 0
        self._sched_mode_combo.setCurrentIndex(mode_index)
        self._sched_value_edit.setText(cfg.get("schedule_value", "") or "")
        self._on_sched_mode_changed(mode_index)

        self._webhook_edit.setText(cfg.get("webhook_url", "") or "")
        self._tg_token_edit.setText(cfg.get("tg_token", "") or "")
        self._tg_chat_id_edit.setText(cfg.get("tg_chat_id", "") or "")

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
            else:
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
    # Schedule
    # ------------------------------------------------------------------

    def _on_sched_mode_changed(self, index: int) -> None:
        if index == 1:
            self._sched_value_edit.setPlaceholderText("N (часов)")
        else:
            self._sched_value_edit.setPlaceholderText("ЧЧ:ММ")

    def set_next_run_text(self, text: str) -> None:
        self._next_run_label.setText(f"Следующий запуск: {text}")

    # ------------------------------------------------------------------
    # SQL Server — instance scan
    # ------------------------------------------------------------------

    def _scan_instances(self) -> None:
        if self._scan_running:
            return
        self._scan_running = True

        self._instance_combo.clear()
        self._instance_combo.addItem("Сканирование…")
        self._instance_combo.setEnabled(False)

        worker = _InstanceScanWorker()
        self._scan_worker = worker  # keep alive — GC would delete it otherwise
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.finished.connect(self._on_scan_finished)
        worker.error.connect(self._on_scan_error)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda w=worker: setattr(self, '_scan_worker', None) if self._scan_worker is w else None)
        thread.start()

    @Slot(list)
    def _on_scan_finished(self, instances: list[SqlInstance]) -> None:
        self._scan_running = False
        self._dblist_running = False  # reset any in-flight fetch from before scan

        target_idx = 0
        try:
            self._instance_combo.blockSignals(True)
            self._instance_combo.setEnabled(True)
            self._instance_combo.clear()

            if not instances:
                self._instance_combo.addItem("Нет экземпляров")
                return  # finally unblocks signals, then function returns

            cfg = self._config.load()
            saved = cfg.get("sql_instance", "")

            for inst in instances:
                self._instance_combo.addItem(inst.display, userData=inst)

            if saved:
                idx = self._instance_combo.findText(saved)
                if idx >= 0:
                    target_idx = idx
        finally:
            self._instance_combo.blockSignals(False)

        self._instance_combo.setCurrentIndex(target_idx)
        # Qt sets currentIndex=0 during addItem even with signals blocked,
        # so setCurrentIndex(0) emits nothing. Always trigger fetch explicitly.
        self._on_instance_changed(target_idx)

    @Slot(str)
    def _on_scan_error(self, message: str) -> None:
        self._scan_running = False
        self._instance_combo.setEnabled(True)
        self._instance_combo.clear()
        self._instance_combo.addItem("Ошибка сканирования")
        _set_status(self._conn_status, False, f"Сканирование: {message}")

    # ------------------------------------------------------------------
    # SQL Server — database list
    # ------------------------------------------------------------------

    def _on_instance_changed(self, idx: int) -> None:
        inst = self._instance_combo.itemData(idx)

        if inst is None:
            # Construct SqlInstance from display text (e.g. loaded from config)
            inst = _instance_from_text(self._instance_combo.itemText(idx))
            if inst is None:
                return
            self._instance_combo.setItemData(idx, inst)

        self._fetch_databases(inst)

    def _refresh_databases(self) -> None:
        idx = self._instance_combo.currentIndex()
        inst = self._instance_combo.itemData(idx)
        if inst is None:
            inst = _instance_from_text(self._instance_combo.currentText())
        if inst is None:
            return
        self._fetch_databases(inst)

    def _fetch_databases(self, inst: SqlInstance) -> None:
        if self._dblist_running:
            # A fetch is already in-flight; queue this instance for after it finishes
            self._dblist_pending = inst
            return
        self._dblist_pending = None
        self._dblist_running = True

        self._db_combo.clear()
        self._db_combo.addItem("Загрузка…")
        self._db_combo.setEnabled(False)

        user = self._login_edit.text().strip()
        password = self._password_edit.text()

        worker = _DbListWorker(inst, user, password)
        self._dblist_worker = worker  # keep alive — GC would delete it otherwise
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.finished.connect(self._on_dblist_finished)
        worker.error.connect(self._on_dblist_error)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda w=worker: setattr(self, '_dblist_worker', None) if self._dblist_worker is w else None)
        thread.start()

    @Slot(list)
    def _on_dblist_finished(self, databases: list[str]) -> None:
        self._dblist_running = False
        pending = self._dblist_pending
        self._dblist_pending = None

        cfg = self._config.load()
        saved_db = cfg.get("sql_database", "")

        self._db_combo.clear()
        self._db_combo.setEnabled(True)

        if not databases:
            if saved_db:
                self._db_combo.addItem(saved_db)
        else:
            for db in databases:
                self._db_combo.addItem(db)
            if saved_db:
                idx = self._db_combo.findText(saved_db)
                if idx >= 0:
                    self._db_combo.setCurrentIndex(idx)

        # Instance changed while we were fetching — fetch the new one now
        if pending is not None:
            self._fetch_databases(pending)

    @Slot(str)
    def _on_dblist_error(self, message: str) -> None:
        self._dblist_running = False
        pending = self._dblist_pending
        self._dblist_pending = None

        self._db_combo.clear()
        self._db_combo.setEnabled(True)
        _set_status(self._conn_status, False, f"Список БД: {message}")

        if pending is not None:
            # User switched instance while we were fetching — honour their choice
            self._fetch_databases(pending)
        else:
            # Auto-advance: try the next instance in the list so that, for example,
            # a dead MSSQLSERVER doesn't block discovery of a working SQLEXPRESS.
            cur = self._instance_combo.currentIndex()
            nxt = cur + 1
            if nxt < self._instance_combo.count():
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
        if self._test_conn_running:
            return
        self._test_conn_running = True

        cfg: AppConfig = {
            "sql_instance": self._instance_combo.currentText().strip(),
            "sql_database": self._db_combo.currentText().strip(),
            "sql_user": self._login_edit.text().strip(),
            "sql_password": self._password_edit.text(),
        }
        _set_status(self._conn_status, None, "Проверка подключения…")

        worker = _TestConnWorker(cfg)
        self._test_conn_worker = worker  # keep alive — GC would delete it otherwise
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.finished.connect(self._on_test_conn_finished)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda w=worker: setattr(self, '_test_conn_worker', None) if self._test_conn_worker is w else None)
        thread.start()

    @Slot(bool, str)
    def _on_test_conn_finished(self, ok: bool, message: str) -> None:
        self._test_conn_running = False
        if ok:
            _set_status(self._conn_status, True, "Подключение успешно")
            self._refresh_databases()
        else:
            _set_status(self._conn_status, False, message or "Ошибка подключения")

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------

    def _test_telegram(self) -> None:
        token = self._tg_token_edit.text().strip()
        chat_id = self._tg_chat_id_edit.text().strip()

        if not token or not chat_id:
            _set_status(self._tg_status, False, "Заполните Token и Chat ID")
            return

        if self._test_tg_running:
            return
        self._test_tg_running = True

        _set_status(self._tg_status, None, "Отправка…")

        worker = _TestTgWorker(token, chat_id)
        self._test_tg_worker = worker  # keep alive — GC would delete it otherwise
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.finished.connect(self._on_test_tg_finished)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda w=worker: setattr(self, '_test_tg_worker', None) if self._test_tg_worker is w else None)
        thread.start()

    @Slot(bool, str)
    def _on_test_tg_finished(self, ok: bool, message: str) -> None:
        self._test_tg_running = False
        if ok:
            _set_status(self._tg_status, True, "Telegram: сообщение отправлено")
        else:
            _set_status(self._tg_status, False, message or "Ошибка Telegram")

    # ------------------------------------------------------------------
    # App settings
    # ------------------------------------------------------------------

    def _on_startup_toggled(self, checked: bool) -> None:
        if checked:
            ok, err = StartupManager.register()
        else:
            ok, err = StartupManager.unregister()

        if not ok:
            self._startup_check.blockSignals(True)
            self._startup_check.setChecked(not checked)
            self._startup_check.blockSignals(False)
            QMessageBox.warning(
                self, "Автозапуск",
                f"Не удалось изменить запись в реестре:\n{err}",
            )

    def _check_update(self) -> None:
        if self._update_running:
            return
        self._update_running = True

        worker = UpdateWorker(
            current_version=self._current_version,
            repo=GITHUB_REPO,
        )
        self._update_worker = worker  # keep alive — GC would delete it otherwise
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
        thread.finished.connect(lambda w=worker: setattr(self, '_update_worker', None) if self._update_worker is w else None)
        thread.start()

    @Slot(str, str)
    def _on_update_available(self, tag: str, download_url: str) -> None:
        self._update_running = False
        QMessageBox.information(
            self, "Доступно обновление",
            f"Новая версия {tag} доступна.\n\nСсылка: {download_url}",
        )

    @Slot()
    def _on_no_update(self) -> None:
        self._update_running = False
        QMessageBox.information(
            self, "Обновлений нет",
            f"Установлена актуальная версия ({self._current_version}).",
        )

    @Slot(str)
    def _on_update_error(self, message: str) -> None:
        self._update_running = False
        QMessageBox.warning(self, "Ошибка проверки обновлений", message)
