# -*- coding: utf-8 -*-
"""ExportJobsWidget — card-based export job manager."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

import sqlglot
from sqlglot.errors import ParseError, TokenError
from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
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

from app.config import (
    AppConfig,
    ConfigManager,
    ExportHistoryEntry,
    ExportJob,
    SyncResult,
    TriggerType,
)
from app.core.app_logger import get_logger
from app.core.constants import (
    DEBOUNCE_SAVE_MS,
    DEBOUNCE_SYNTAX_MS,
    HISTORY_MAX,
    SCHED_VALUE_INPUT_W,
)
from app.core.scheduler import SyncScheduler
from app.ui.history_row import HistoryRow
from app.ui.lucide_icons import lucide
from app.ui.test_run_dialog import TestRunDialog
from app.ui.theme import Theme
from app.ui.threading import run_worker
from app.ui.widgets import hsep
from app.workers.export_worker import ExportWorker

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# SQL Syntax Validator (sqlglot-backed, T-SQL dialect)
# ---------------------------------------------------------------------------

def _validate_sql(sql: str) -> tuple[bool, str]:
    """
    Full T-SQL syntax check via sqlglot. Parses the entire query
    (statements separated by ;) using the T-SQL dialect grammar.
    Returns (ok, short_message_in_russian).
    """
    sql = sql.strip()
    if not sql:
        return False, "Запрос пуст"

    try:
        statements = sqlglot.parse(
            sql,
            dialect="tsql",
            error_level=sqlglot.ErrorLevel.IMMEDIATE,
        )
    except (ParseError, TokenError) as exc:
        return False, _format_sqlglot_error(exc)
    except Exception as exc:  # pragma: no cover — defensive
        return False, f"Ошибка парсера: {exc}"

    # sqlglot returns [None] for trailing/empty statements; require at least one real one
    if not any(stmt is not None for stmt in statements):
        return False, "Пустое выражение"

    return True, "SQL корректен"


def _format_sqlglot_error(exc: Exception) -> str:
    """Take the first sqlglot error and make it short + Russian-friendly."""
    errors = getattr(exc, "errors", None)
    if errors:
        first = errors[0]
        desc = first.get("description") or ""
        line = first.get("line")
        col  = first.get("col")
        # Translate a few common sqlglot phrases to Russian
        ru = (desc
              .replace("Expecting", "Ожидается")
              .replace("Expected", "Ожидается")
              .replace("Invalid expression", "Недопустимое выражение")
              .replace("Unexpected token", "неожиданный токен")
              .replace("but got", "—"))
        # Strip noisy <Token …> blob if present
        ru = re.sub(r"<Token[^>]*text:\s*([^,]+),[^>]*>", r"«\1»", ru)
        ru = re.sub(r"\s+", " ", ru).strip()
        if line and col:
            return f"стр {line}:{col} · {ru[:80]}"
        return ru[:100] or "Синтаксическая ошибка"
    return str(exc)[:100] or "Синтаксическая ошибка"


# ---------------------------------------------------------------------------
# ExportJobCard
# ---------------------------------------------------------------------------

class ExportJobCard(QWidget):
    """Single export-job card with its own scheduler and worker thread."""

    changed          = Signal(object)  # ExportJob — emitted on any field edit
    delete_requested = Signal(str)     # job id
    sync_completed   = Signal(object)  # SyncResult — emitted on successful run
    history_changed  = Signal()        # emitted whenever an entry is added or deleted

    def __init__(
        self,
        job: ExportJob,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._config = config
        self._job_id: str = job.get("id") or str(uuid.uuid4())
        self._running = False
        self._worker: ExportWorker | None = None
        self._last_trigger: TriggerType = TriggerType.MANUAL    # set just before export starts
        self._current_trigger: TriggerType = TriggerType.MANUAL  # captured at export start for history
        self._history: list[ExportHistoryEntry] = []

        self._scheduler = SyncScheduler(self)
        self._scheduler.trigger.connect(self._auto_trigger)

        # debounce — save after user stops typing in SQL/name/webhook
        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(DEBOUNCE_SAVE_MS)
        self._query_timer.timeout.connect(self._emit_changed)

        # debounce — syntax check
        self._syntax_timer = QTimer(self)
        self._syntax_timer.setSingleShot(True)
        self._syntax_timer.setInterval(DEBOUNCE_SYNTAX_MS)
        self._syntax_timer.timeout.connect(self._check_syntax)

        self._build_ui()
        self._load_job(job)
        self._apply_schedule()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.setObjectName("exportCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(6)

        # ── Header: name · run · delete ──────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Название выгрузки…")
        self._name_edit.editingFinished.connect(self._emit_changed)
        hdr.addWidget(self._name_edit, stretch=1)

        self._run_btn = QPushButton()
        self._run_btn.setIcon(lucide("play", color=Theme.gray_900, size=12))
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setFixedSize(28, 24)
        self._run_btn.setToolTip("Запустить выгрузку вручную")
        self._run_btn.clicked.connect(self.start_export)
        hdr.addWidget(self._run_btn)

        del_btn = QPushButton()
        del_btn.setIcon(lucide("trash-2", color=Theme.error, size=12))
        del_btn.setFixedSize(24, 24)
        del_btn.setFlat(True)
        del_btn.setToolTip("Удалить выгрузку")
        del_btn.clicked.connect(self._on_delete)
        hdr.addWidget(del_btn)

        root.addLayout(hdr)
        root.addWidget(hsep())

        # ── SQL query ─────────────────────────────────────────────────────
        sql_lbl = QLabel("SQL запрос")
        sql_lbl.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"text-transform: uppercase; "
            f"letter-spacing: 0.3px;"
        )
        root.addWidget(sql_lbl)

        self._query_edit = QPlainTextEdit()
        self._query_edit.setPlaceholderText("SELECT … FROM …")
        self._query_edit.setMinimumHeight(72)
        self._query_edit.setMaximumHeight(140)
        self._query_edit.textChanged.connect(self._on_query_changed)
        root.addWidget(self._query_edit)

        # Syntax indicator + test button (inline row below editor)
        sql_tools = QHBoxLayout()
        sql_tools.setSpacing(6)

        self._syntax_lbl = QLabel("")
        self._syntax_lbl.setObjectName("syntaxStatus")
        self._syntax_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        sql_tools.addWidget(self._syntax_lbl)
        sql_tools.addStretch(1)

        test_btn = QPushButton("  Тест")
        test_btn.setIcon(lucide("terminal", color=Theme.gray_700, size=12))
        test_btn.setFixedHeight(24)
        test_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        test_btn.setToolTip("Выполнить SQL запрос в тестовом окне")
        test_btn.clicked.connect(self._open_test_dialog)
        sql_tools.addWidget(test_btn)

        root.addLayout(sql_tools)
        root.addWidget(hsep())

        # ── Webhook URL ───────────────────────────────────────────────────
        wh_lbl = QLabel("Webhook URL")
        wh_lbl.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"text-transform: uppercase; "
            f"letter-spacing: 0.3px;"
        )
        root.addWidget(wh_lbl)

        self._webhook_edit = QLineEdit()
        self._webhook_edit.setPlaceholderText("https://… (необязательно)")
        self._webhook_edit.editingFinished.connect(self._emit_changed)
        root.addWidget(self._webhook_edit)
        root.addWidget(hsep())

        # ── Schedule + status ─────────────────────────────────────────────
        sched_row = QHBoxLayout()
        sched_row.setSpacing(6)

        self._sched_check = QCheckBox("Авто")
        self._sched_check.setToolTip("Включить автоматическую выгрузку по расписанию")
        self._sched_check.toggled.connect(self._on_sched_changed)
        sched_row.addWidget(self._sched_check)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Ежедневно", "Каждые N часов"])
        self._mode_combo.currentIndexChanged.connect(self._on_sched_changed)
        sched_row.addWidget(self._mode_combo)

        self._sched_value_edit = QLineEdit()
        self._sched_value_edit.setFixedWidth(SCHED_VALUE_INPUT_W)
        self._sched_value_edit.setPlaceholderText("ЧЧ:ММ")
        self._sched_value_edit.editingFinished.connect(self._on_sched_changed)
        sched_row.addWidget(self._sched_value_edit)

        sched_row.addStretch(1)

        self._progress_lbl = QLabel()
        self._progress_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; font-size: {Theme.font_size_sm}pt;"
        )
        sched_row.addWidget(self._progress_lbl)

        self._status_lbl = QLabel()
        self._status_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._status_lbl.setStyleSheet(f"font-size: {Theme.font_size_sm}pt;")
        sched_row.addWidget(self._status_lbl)

        root.addLayout(sched_row)

        # ── History section (hidden until first entry) ────────────────────
        self._hist_sep = hsep()
        self._hist_sep.setVisible(False)
        root.addWidget(self._hist_sep)

        self._history_hdr = QLabel("История")
        self._history_hdr.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"text-transform: uppercase; "
            f"letter-spacing: 0.3px;"
        )
        self._history_hdr.setVisible(False)
        root.addWidget(self._history_hdr)

        # Inner container with transparent background
        self._history_container = QWidget()
        self._history_container.setStyleSheet("QWidget { background-color: transparent; }")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(2)

        self._history_scroll = QScrollArea()
        self._history_scroll.setWidget(self._history_container)
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._history_scroll.setMaximumHeight(120)
        self._history_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._history_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._history_scroll.setVisible(False)
        root.addWidget(self._history_scroll)

    # ------------------------------------------------------------------ Load / save

    def job_id(self) -> str:
        return self._job_id

    def to_job(self) -> ExportJob:
        return ExportJob(
            id=self._job_id,
            name=self._name_edit.text().strip(),
            sql_query=self._query_edit.toPlainText().strip(),
            webhook_url=self._webhook_edit.text().strip(),
            schedule_enabled=self._sched_check.isChecked(),
            schedule_mode="hourly" if self._mode_combo.currentIndex() == 1 else "daily",
            schedule_value=self._sched_value_edit.text().strip(),
            history=list(self._history),
        )

    def _load_job(self, job: ExportJob) -> None:
        # Block all signals during programmatic load to avoid spurious saves
        for w in (
            self._query_edit, self._name_edit, self._webhook_edit,
            self._sched_check, self._mode_combo, self._sched_value_edit,
        ):
            w.blockSignals(True)

        self._name_edit.setText(job.get("name", ""))
        self._query_edit.setPlainText(job.get("sql_query", ""))
        self._webhook_edit.setText(job.get("webhook_url", ""))
        self._sched_check.setChecked(bool(job.get("schedule_enabled", False)))
        mode = job.get("schedule_mode", "daily")
        self._mode_combo.setCurrentIndex(1 if mode == "hourly" else 0)
        self._sched_value_edit.setText(job.get("schedule_value", ""))
        self._history = list(job.get("history") or [])

        for w in (
            self._query_edit, self._name_edit, self._webhook_edit,
            self._sched_check, self._mode_combo, self._sched_value_edit,
        ):
            w.blockSignals(False)

        self._update_placeholder()
        self._rebuild_history_ui()
        # Trigger syntax check after layout settles
        QTimer.singleShot(0, self._check_syntax)

    # ------------------------------------------------------------------ Schedule

    def _on_sched_changed(self) -> None:
        self._update_placeholder()
        self._apply_schedule()
        self._emit_changed()

    def _update_placeholder(self) -> None:
        self._sched_value_edit.setPlaceholderText(
            "N часов" if self._mode_combo.currentIndex() == 1 else "ЧЧ:ММ"
        )

    def _apply_schedule(self) -> None:
        """Start or stop this card's scheduler based on current UI settings."""
        self._scheduler.stop()
        if not self._sched_check.isChecked():
            return
        mode = "hourly" if self._mode_combo.currentIndex() == 1 else "daily"
        value = self._sched_value_edit.text().strip()
        if not value:
            return
        if mode == "daily":
            if not re.fullmatch(r"\d{1,2}:\d{2}", value):
                return
        else:
            if not value.isdigit() or int(value) < 1:
                return
        self._scheduler.configure(mode, value)  # type: ignore[arg-type]
        self._scheduler.start()
        _log.debug(
            "Job '%s': scheduler started (%s %s)",
            self._name_edit.text().strip() or self._job_id, mode, value,
        )

    def stop_scheduler(self) -> None:
        self._scheduler.stop()

    # ------------------------------------------------------------------ SQL validation

    def _on_query_changed(self) -> None:
        self._query_timer.start()
        self._syntax_timer.start()

    def _check_syntax(self) -> None:
        sql = self._query_edit.toPlainText().strip()
        if not sql:
            self._syntax_lbl.setText("")
            return
        ok, msg = _validate_sql(sql)
        if ok:
            self._syntax_lbl.setStyleSheet(
                f"color: {Theme.success}; "
                f"font-size: {Theme.font_size_xs}pt; "
                f"background: transparent;"
            )
            self._syntax_lbl.setText("✓ SQL")
            self._syntax_lbl.setToolTip("")
        else:
            self._syntax_lbl.setStyleSheet(
                f"color: {Theme.error}; "
                f"font-size: {Theme.font_size_xs}pt; "
                f"background: transparent;"
            )
            short = msg if len(msg) <= 36 else msg[:33] + "…"
            self._syntax_lbl.setText(f"✗ {short}")
            self._syntax_lbl.setToolTip(msg)

    # ------------------------------------------------------------------ Export

    @Slot()
    def _auto_trigger(self) -> None:
        """Called by scheduler — marks trigger as scheduled then fires export."""
        self._last_trigger = TriggerType.SCHEDULED
        if not self._running:
            self._start_export()

    def start_export(self) -> None:
        """Public API — manual trigger; idempotent."""
        if not self._running:
            self._last_trigger = TriggerType.MANUAL
            self._start_export()

    def _start_export(self) -> None:
        if self._running:
            return
        self._running = True
        self._current_trigger = self._last_trigger  # capture for history entry
        self._run_btn.setEnabled(False)
        self._progress_lbl.setText("Запуск…")
        self._status_lbl.setText("")

        job = self.to_job()
        base_cfg = self._config.load()

        worker = ExportWorker(base_cfg, job)
        run_worker(
            self,
            worker,
            pin_attr="_worker",
            on_finished=self._on_finished,
            on_error=self._on_error,
        )
        # `progress` is a streaming signal — wired manually (run_worker only
        # handles the terminal finished/error signals).
        worker.progress.connect(self._on_progress)

    # ------------------------------------------------------------------ Worker slots

    @Slot(int, str)
    def _on_progress(self, _step: int, description: str) -> None:
        self._progress_lbl.setText(description)

    @Slot(object)
    def _on_finished(self, result: SyncResult) -> None:
        self._running = False
        self._run_btn.setEnabled(True)
        self._progress_lbl.setText("")
        if result.success:
            ts_clock = result.timestamp.strftime("%H:%M:%S")
            ts_full  = result.timestamp.strftime("%Y-%m-%d %H:%M")
            self._status_lbl.setStyleSheet(
                f"font-size: {Theme.font_size_sm}pt; color: {Theme.success};"
            )
            self._status_lbl.setText(f"✓ {result.rows_synced} строк · {ts_clock}")
            self._add_history_entry(ok=True, rows=result.rows_synced, ts=ts_full)
            self.sync_completed.emit(result)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._running = False
        self._run_btn.setEnabled(True)
        self._progress_lbl.setText("")
        self._status_lbl.setStyleSheet(
            f"font-size: {Theme.font_size_sm}pt; color: {Theme.error};"
        )
        self._status_lbl.setText(f"✗ {msg[:70]}")
        ts_full = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._add_history_entry(ok=False, err=msg, ts=ts_full)

    # ------------------------------------------------------------------ History data

    def _add_history_entry(
        self, *, ok: bool, ts: str, rows: int = 0, err: str = ""
    ) -> None:
        entry: ExportHistoryEntry = {
            "ts":      ts,
            "trigger": self._current_trigger.value,
            "ok":      ok,
            "rows":    rows,
            "err":     err,
        }
        self._history.insert(0, entry)          # newest first
        if len(self._history) > HISTORY_MAX:
            self._history = self._history[:HISTORY_MAX]
        self._rebuild_history_ui()
        self._emit_changed()
        self.history_changed.emit()

    def _delete_history(self, index: int) -> None:
        if 0 <= index < len(self._history):
            self._history.pop(index)
            self._rebuild_history_ui()
            self._emit_changed()
            self.history_changed.emit()

    # ------------------------------------------------------------------ History UI

    def _rebuild_history_ui(self) -> None:
        """Clear and repopulate history rows; show/hide section accordingly."""
        # Remove all existing row widgets
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        has = bool(self._history)
        self._hist_sep.setVisible(has)
        self._history_hdr.setVisible(has)
        self._history_scroll.setVisible(has)
        if has:
            self._history_hdr.setText(f"История ({len(self._history)})")
            for i, entry in enumerate(self._history):
                row = HistoryRow(entry, i, self)
                row.delete_requested.connect(self._delete_history)
                self._history_layout.addWidget(row)

    # ------------------------------------------------------------------ Test dialog

    def _open_test_dialog(self) -> None:
        sql = self._query_edit.toPlainText().strip()
        cfg = self._config.load()
        dialog = TestRunDialog(
            cfg,
            initial_sql=sql,
            auto_run=bool(sql),   # execute immediately if SQL is present
            parent=self,
        )
        dialog.test_completed.connect(self._on_test_completed)
        dialog.exec()

    @Slot(bool, int, str)
    def _on_test_completed(self, ok: bool, rows: int, err: str) -> None:
        """Record a TestRunDialog run as a TEST-trigger history entry."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        saved = self._current_trigger
        self._current_trigger = TriggerType.TEST
        try:
            self._add_history_entry(ok=ok, ts=ts, rows=rows, err=err)
        finally:
            self._current_trigger = saved

    # ------------------------------------------------------------------ Signals

    def _emit_changed(self) -> None:
        self.changed.emit(self.to_job())

    def _on_delete(self) -> None:
        name = self._name_edit.text().strip() or "без названия"
        reply = QMessageBox.question(
            self,
            "Удалить выгрузку",
            f"Удалить выгрузку «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_scheduler()
            self.delete_requested.emit(self._job_id)


# ---------------------------------------------------------------------------
# ExportJobsWidget
# ---------------------------------------------------------------------------

class ExportJobsWidget(QWidget):
    """Container — card-based export job manager."""

    sync_completed = Signal(object)  # SyncResult — bubbled up from any card
    history_changed = Signal()       # bubbled from any card (add/delete history)

    def __init__(
        self, config: ConfigManager, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._cards: list[ExportJobCard] = []
        self._build_ui()
        self._load_jobs()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top toolbar
        toolbar = QWidget()
        toolbar.setObjectName("exportToolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 12, 16, 12)

        title = QLabel("Выгрузки")
        title.setStyleSheet(
            f"font-size: {Theme.font_size_lg}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"color: {Theme.gray_900};"
        )
        tb.addWidget(title)
        tb.addStretch()

        add_btn = QPushButton("  Добавить выгрузку")
        add_btn.setObjectName("primaryBtn")
        add_btn.setIcon(lucide("plus", color=Theme.gray_900))
        add_btn.clicked.connect(self._add_new_job)
        tb.addWidget(add_btn)

        root.addWidget(toolbar)

        sep = hsep()
        root.addWidget(sep)

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, stretch=1)

        self._container = QWidget()
        scroll.setWidget(self._container)

        self._cards_layout = QVBoxLayout(self._container)
        self._cards_layout.setContentsMargins(16, 16, 16, 16)
        self._cards_layout.setSpacing(12)

        self._empty_lbl = QLabel(
            "Нет настроенных выгрузок.\nНажмите «Добавить выгрузку» для начала."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {Theme.gray_400}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"padding: 48px 0;"
        )
        self._cards_layout.addWidget(self._empty_lbl)
        self._cards_layout.addStretch()

    # ------------------------------------------------------------------ Jobs

    def _load_jobs(self) -> None:
        cfg = self._config.load()
        raw_jobs: list[dict] = cfg.get("export_jobs") or []  # type: ignore[assignment]
        for raw in raw_jobs:
            job = ExportJob(
                id=raw.get("id", str(uuid.uuid4())),
                name=raw.get("name", ""),
                sql_query=raw.get("sql_query", ""),
                webhook_url=raw.get("webhook_url", ""),
                schedule_enabled=bool(raw.get("schedule_enabled", False)),
                schedule_mode=raw.get("schedule_mode", "daily"),
                schedule_value=raw.get("schedule_value", ""),
                history=list(raw.get("history") or []),  # type: ignore[typeddict-unknown-key]
            )
            self._add_card(job)
        self._refresh_empty()

    def _save_jobs(self) -> None:
        cfg = self._config.load()
        cfg["export_jobs"] = [c.to_job() for c in self._cards]  # type: ignore[typeddict-unknown-key]
        self._config.save(cfg)

    def _add_new_job(self) -> None:
        job = ExportJob(
            id=str(uuid.uuid4()),
            name="",
            sql_query="",
            webhook_url="",
            schedule_enabled=False,
            schedule_mode="daily",
            schedule_value="",
            history=[],  # type: ignore[typeddict-unknown-key]
        )
        self._add_card(job)
        self._save_jobs()
        self._refresh_empty()

    def _add_card(self, job: ExportJob) -> None:
        card = ExportJobCard(job, self._config, self)
        card.changed.connect(lambda _j: self._save_jobs())
        card.delete_requested.connect(self._remove_card)
        card.sync_completed.connect(self.sync_completed)
        card.history_changed.connect(self.history_changed)
        self._cards.append(card)
        # Insert before trailing stretch
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    @Slot(str)
    def _remove_card(self, job_id: str) -> None:
        for card in list(self._cards):
            if card.job_id() == job_id:
                self._cards.remove(card)
                self._cards_layout.removeWidget(card)
                card.deleteLater()
                break
        self._save_jobs()
        self._refresh_empty()
        self.history_changed.emit()

    def _refresh_empty(self) -> None:
        self._empty_lbl.setVisible(len(self._cards) == 0)

    # ------------------------------------------------------------------ Public

    def stop_all_schedulers(self) -> None:
        """Stop all per-card schedulers — call on app shutdown."""
        for card in self._cards:
            card.stop_scheduler()
