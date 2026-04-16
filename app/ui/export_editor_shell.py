# -*- coding: utf-8 -*-
"""Composite view shell for ExportJobEditor."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from app.config import ExportHistoryEntry
from app.ui.export_editor_header import ExportEditorHeader
from app.ui.export_history_panel import ExportHistoryPanel
from app.ui.export_schedule_panel import ExportSchedulePanel
from app.ui.export_sql_panel import ExportSqlPanel
from app.ui.widgets import HeaderLabel, hsep


class ExportEditorShell(QWidget):
    """Owns the view composition and view-level helpers for the editor."""

    changed = Signal()
    query_changed = Signal()
    schedule_changed = Signal()
    history_changed = Signal()
    test_requested = Signal()
    run_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._wire_signals()

    @staticmethod
    def _section_break(root: QVBoxLayout) -> None:
        root.addSpacing(8)
        root.addWidget(hsep())
        root.addSpacing(8)

    def _build_ui(self) -> None:
        self.setObjectName("exportCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        self._header = ExportEditorHeader(self)
        root.addWidget(self._header)

        self._section_break(root)

        self._sql_panel = ExportSqlPanel(self)
        root.addWidget(self._sql_panel, stretch=1)

        self._section_break(root)

        root.addWidget(HeaderLabel("Webhook URL"))
        self._webhook_edit = QLineEdit(self)
        self._webhook_edit.setPlaceholderText("https://… (необязательно)")
        root.addWidget(self._webhook_edit)

        self._section_break(root)

        self._schedule_panel = ExportSchedulePanel(self)
        root.addWidget(self._schedule_panel)

        self._history_panel = ExportHistoryPanel(self)
        root.addWidget(self._history_panel)

    def _wire_signals(self) -> None:
        self._header.changed.connect(self.changed)
        self._header.test_requested.connect(self.test_requested)
        self._header.run_requested.connect(self.run_requested)
        self._sql_panel.changed.connect(self.query_changed)
        self._webhook_edit.editingFinished.connect(self.changed)
        self._schedule_panel.changed.connect(self.schedule_changed)
        self._history_panel.changed.connect(self.history_changed)

    def job_name(self) -> str:
        return self._header.job_name()

    def set_job_name(self, name: str) -> None:
        self._header.set_job_name(name)

    def sql_text(self) -> str:
        return self._sql_panel.sql_text()

    def set_sql_text(self, sql: str) -> None:
        self._sql_panel.set_sql_text(sql)

    def refresh_sql_syntax(self) -> None:
        self._sql_panel.refresh_syntax()

    def webhook_url(self) -> str:
        return self._webhook_edit.text().strip()

    def set_webhook_url(self, url: str) -> None:
        self._webhook_edit.blockSignals(True)
        try:
            self._webhook_edit.setText(url)
        finally:
            self._webhook_edit.blockSignals(False)

    def schedule_enabled(self) -> bool:
        return self._schedule_panel.schedule_enabled()

    def schedule_mode(self) -> str:
        return self._schedule_panel.schedule_mode()

    def schedule_value(self) -> str:
        return self._schedule_panel.schedule_value()

    def set_schedule(self, enabled: bool, mode: str, value: str) -> None:
        self._schedule_panel.set_schedule(enabled, mode, value)

    def set_progress_text(self, text: str) -> None:
        self._schedule_panel.set_progress_text(text)

    def set_status(self, kind: str, text: str) -> None:
        self._header.set_status(kind, text)

    def set_run_enabled(self, enabled: bool) -> None:
        self._header.set_run_enabled(enabled)

    def history(self) -> list[ExportHistoryEntry]:
        return self._history_panel.history()

    def set_history(self, history: list[ExportHistoryEntry]) -> None:
        self._history_panel.set_history(history)

    def latest_history_entry(self) -> ExportHistoryEntry | None:
        return self._history_panel.latest_entry()

    def prepend_history_entry(self, entry: ExportHistoryEntry) -> None:
        self._history_panel.prepend_entry(entry)
