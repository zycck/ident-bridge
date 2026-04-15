# -*- coding: utf-8 -*-
"""ExportJobsWidget — card-based export job manager."""
from __future__ import annotations

import re
import uuid

import qtawesome as qta
from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
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

from app.config import AppConfig, ConfigManager, ExportJob, SyncResult
from app.core.app_logger import get_logger
from app.core.scheduler import SyncScheduler
from app.workers.export_worker import ExportWorker
from app.ui.test_run_dialog import TestRunDialog

_log = get_logger(__name__)


class ExportJobCard(QWidget):
    """Single export-job card with its own scheduler and worker thread."""

    changed = Signal(object)         # ExportJob — emitted on any field edit
    delete_requested = Signal(str)   # job id
    sync_completed = Signal(object)  # SyncResult — emitted on successful run

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

        self._scheduler = SyncScheduler(self)
        self._scheduler.trigger.connect(self._start_export)

        # Debounce timer for SQL text changes
        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(800)
        self._query_timer.timeout.connect(self._emit_changed)

        self._build_ui()
        self._load_job(job)
        self._apply_schedule()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.setObjectName("exportCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # Header: name + run + delete
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Название выгрузки…")
        self._name_edit.editingFinished.connect(self._emit_changed)
        hdr.addWidget(self._name_edit, stretch=1)

        self._run_btn = QPushButton()
        self._run_btn.setIcon(qta.icon("fa5s.play", color="#FFFFFF"))
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setFixedSize(34, 34)
        self._run_btn.setToolTip("Запустить выгрузку вручную")
        self._run_btn.clicked.connect(self.start_export)
        hdr.addWidget(self._run_btn)

        del_btn = QPushButton()
        del_btn.setIcon(qta.icon("fa5s.trash-alt", color="#EF4444"))
        del_btn.setFixedSize(34, 34)
        del_btn.setToolTip("Удалить выгрузку")
        del_btn.clicked.connect(self._on_delete)
        hdr.addWidget(del_btn)

        root.addLayout(hdr)

        # SQL query label + editor
        sql_lbl = QLabel("SQL запрос")
        sql_lbl.setStyleSheet("color: #9CA3AF; font-size: 8.5pt;")
        root.addWidget(sql_lbl)

        self._query_edit = QPlainTextEdit()
        self._query_edit.setPlaceholderText("SELECT … FROM …")
        self._query_edit.setMinimumHeight(88)
        self._query_edit.setMaximumHeight(160)
        self._query_edit.textChanged.connect(self._query_timer.start)
        root.addWidget(self._query_edit)

        test_btn = QPushButton("  Тестовый запрос")
        test_btn.setIcon(qta.icon("fa5s.terminal", color="#374151"))
        test_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        test_btn.clicked.connect(self._open_test_dialog)
        root.addWidget(test_btn)

        # Webhook URL (optional)
        wh_lbl = QLabel("Webhook URL (необязательно)")
        wh_lbl.setStyleSheet("color: #9CA3AF; font-size: 8.5pt;")
        root.addWidget(wh_lbl)

        self._webhook_edit = QLineEdit()
        self._webhook_edit.setPlaceholderText("https://…")
        self._webhook_edit.editingFinished.connect(self._emit_changed)
        root.addWidget(self._webhook_edit)

        # Thin separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #E5E7EB; max-height: 1px; border: none;")
        root.addWidget(sep)

        # Schedule row
        sched_row = QHBoxLayout()
        sched_row.setSpacing(8)

        self._sched_check = QCheckBox("Авто")
        self._sched_check.setToolTip("Включить автоматическую выгрузку по расписанию")
        self._sched_check.toggled.connect(self._on_sched_changed)
        sched_row.addWidget(self._sched_check)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Ежедневно", "Каждые N часов"])
        self._mode_combo.currentIndexChanged.connect(self._on_sched_changed)
        sched_row.addWidget(self._mode_combo)

        self._sched_value_edit = QLineEdit()
        self._sched_value_edit.setFixedWidth(72)
        self._sched_value_edit.setPlaceholderText("ЧЧ:ММ")
        self._sched_value_edit.editingFinished.connect(self._on_sched_changed)
        sched_row.addWidget(self._sched_value_edit)

        sched_row.addStretch()

        root.addLayout(sched_row)

        # Status row
        status_row = QHBoxLayout()

        self._progress_lbl = QLabel()
        self._progress_lbl.setStyleSheet("color: #6B7280; font-size: 8.5pt;")
        status_row.addWidget(self._progress_lbl, stretch=1)

        self._status_lbl = QLabel()
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._status_lbl.setStyleSheet("font-size: 8.5pt;")
        status_row.addWidget(self._status_lbl)

        root.addLayout(status_row)

    # ------------------------------------------------------------------ Data

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
        )

    def _load_job(self, job: ExportJob) -> None:
        self._name_edit.setText(job.get("name", ""))
        self._query_edit.setPlainText(job.get("sql_query", ""))
        self._webhook_edit.setText(job.get("webhook_url", ""))
        self._sched_check.setChecked(bool(job.get("schedule_enabled", False)))
        mode = job.get("schedule_mode", "daily")
        self._mode_combo.setCurrentIndex(1 if mode == "hourly" else 0)
        self._sched_value_edit.setText(job.get("schedule_value", ""))
        self._update_placeholder()

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
        """Start or stop this card's scheduler based on current settings."""
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

    # ------------------------------------------------------------------ Export

    def start_export(self) -> None:
        """Public API — idempotent manual trigger."""
        if not self._running:
            self._start_export()

    def _start_export(self) -> None:
        if self._running:
            return
        self._running = True
        self._run_btn.setEnabled(False)
        self._progress_lbl.setText("Запуск…")
        self._status_lbl.setText("")

        job = self.to_job()
        base_cfg = self._config.load()

        worker = ExportWorker(base_cfg, job)
        self._worker = worker  # strong ref — GC would delete it otherwise
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda w=worker: setattr(self, "_worker", None)
            if self._worker is w else None
        )
        thread.start()

    @Slot(int, str)
    def _on_progress(self, _step: int, description: str) -> None:
        self._progress_lbl.setText(description)

    @Slot(object)
    def _on_finished(self, result: SyncResult) -> None:
        self._running = False
        self._run_btn.setEnabled(True)
        self._progress_lbl.setText("")
        if result.success:
            ts = result.timestamp.strftime("%H:%M:%S")
            self._status_lbl.setStyleSheet("font-size: 8.5pt; color: #34D399;")
            self._status_lbl.setText(f"✓ {result.rows_synced} строк · {ts}")
            self.sync_completed.emit(result)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._running = False
        self._run_btn.setEnabled(True)
        self._progress_lbl.setText("")
        self._status_lbl.setStyleSheet("font-size: 8.5pt; color: #EF4444;")
        self._status_lbl.setText(f"✗ {msg[:70]}")

    # ------------------------------------------------------------------ Test dialog

    def _open_test_dialog(self) -> None:
        cfg = self._config.load()
        TestRunDialog(
            cfg, initial_sql=self._query_edit.toPlainText().strip(), parent=self
        ).exec()

    # ------------------------------------------------------------------ Signals

    def _emit_changed(self) -> None:
        self.changed.emit(self.to_job())

    def _on_delete(self) -> None:
        name = self._name_edit.text().strip() or "без названия"
        reply = QMessageBox.question(
            self, "Удалить выгрузку",
            f"Удалить выгрузку «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_scheduler()
            self.delete_requested.emit(self._job_id)


# ---------------------------------------------------------------------------

class ExportJobsWidget(QWidget):
    """Container — card-based export job manager."""

    sync_completed = Signal(object)  # SyncResult — bubbled up from any card

    def __init__(self, config: ConfigManager, parent: QWidget | None = None) -> None:
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
        title.setStyleSheet("font-size: 13pt; font-weight: 600; color: #111827;")
        tb.addWidget(title)
        tb.addStretch()

        add_btn = QPushButton("  Добавить выгрузку")
        add_btn.setObjectName("primaryBtn")
        add_btn.setIcon(qta.icon("fa5s.plus", color="#FFFFFF"))
        add_btn.clicked.connect(self._add_new_job)
        tb.addWidget(add_btn)

        root.addWidget(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #E5E7EB; max-height: 1px; border: none;")
        root.addWidget(sep)

        # Scroll area
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
            "color: #9CA3AF; font-size: 11pt; padding: 48px 0;"
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
        )
        self._add_card(job)
        self._save_jobs()
        self._refresh_empty()

    def _add_card(self, job: ExportJob) -> None:
        card = ExportJobCard(job, self._config, self)
        card.changed.connect(lambda _j: self._save_jobs())
        card.delete_requested.connect(self._remove_card)
        card.sync_completed.connect(self.sync_completed)
        self._cards.append(card)
        # Insert before the trailing stretch
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

    def _refresh_empty(self) -> None:
        self._empty_lbl.setVisible(len(self._cards) == 0)

    # ------------------------------------------------------------------ Public

    def stop_all_schedulers(self) -> None:
        """Stop all per-card schedulers — call on app shutdown."""
        for card in self._cards:
            card.stop_scheduler()
