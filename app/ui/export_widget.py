# -*- coding: utf-8 -*-
"""
ExportWidget — manual sync trigger panel.

Displays a primary action button, a 4-step progress bar, step description,
result summary, and an optional webhook-not-configured warning.
"""
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigManager, IExporter, INotifier, SyncResult
from app.workers.export_worker import ExportWorker


class ExportWidget(QWidget):
    def __init__(
        self,
        config: ConfigManager,
        exporter: IExporter,
        notifier: INotifier | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._exporter = exporter
        self._notifier = notifier
        self._export_running = False
        self._export_worker: ExportWorker | None = None

        self._build_ui()
        self._apply_initial_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # Primary action button
        self._btn = QPushButton("ВЫГРУЗИТЬ")
        self._btn.setObjectName("primaryBtn")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self._btn.setFont(font)
        self._btn.setMinimumHeight(48)
        self._btn.clicked.connect(self._start_export)

        # Progress bar (0–4 steps)
        self._progress = QProgressBar()
        self._progress.setRange(0, 4)
        self._progress.setValue(0)
        self._progress.setFormat("%v/4")
        self._progress.setTextVisible(True)

        # Step description label (muted, centered)
        self._step_label = QLabel("")
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._step_label.setEnabled(False)

        # Result summary label
        self._result_label = QLabel("")
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_label.setWordWrap(True)

        # Webhook warning — shown only when exporter reports unconfigured
        self._warn_label = QLabel(
            "⚠ Webhook не настроен — данные будут выведены в лог"
        )
        self._warn_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._warn_label.setObjectName("warnLabel")

        root.addWidget(self._btn)
        root.addWidget(self._progress)
        root.addWidget(self._step_label)
        root.addWidget(self._result_label)
        root.addWidget(self._warn_label)
        root.addStretch()

    def _apply_initial_state(self) -> None:
        is_configured = (
            hasattr(self._exporter, "is_configured")
            and self._exporter.is_configured()  # type: ignore[attr-defined]
        )
        self._warn_label.setVisible(not is_configured)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_export(self) -> None:
        """Публичный метод — можно вызывать из трея или других виджетов."""
        if not self._export_running:
            self._start_export()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _start_export(self) -> None:
        if self._export_running:
            return
        self._export_running = True
        self._btn.setEnabled(False)
        self._progress.setValue(0)
        self._step_label.setText("")
        self._result_label.setText("")
        self._result_label.setStyleSheet("")

        worker = ExportWorker(self._config, self._exporter, self._notifier)
        self._export_worker = worker  # keep alive — GC would delete it otherwise
        thread = QThread(self)

        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda w=worker: setattr(self, '_export_worker', None)
            if self._export_worker is w else None
        )

        thread.start()

    def _on_progress(self, step: int, description: str) -> None:
        self._progress.setValue(step)
        self._step_label.setText(description)

    def _on_finished(self, result: SyncResult) -> None:
        self._export_running = False
        if result.success:
            self._result_label.setStyleSheet("")
            self._result_label.setText(
                f"Синхронизировано {result.rows_synced} строк  ·  "
                f"{result.timestamp.strftime('%H:%M:%S')}"
            )
        self._btn.setEnabled(True)

    def _on_error(self, msg: str) -> None:
        self._export_running = False
        self._result_label.setStyleSheet("color: #EF4444;")
        self._result_label.setText(f"Ошибка: {msg}")
        self._btn.setEnabled(True)
