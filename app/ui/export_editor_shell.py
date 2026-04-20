"""Composite view shell for ExportJobEditor."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from app.config import ExportHistoryEntry
from app.core.scheduler import ScheduleMode
from app.ui.export_google_sheets_panel import ExportGoogleSheetsPanel
from app.ui.export_editor_header import ExportEditorHeader
from app.ui.export_history_panel import ExportHistoryPanel
from app.ui.export_schedule_panel import ExportSchedulePanel
from app.ui.export_sql_panel import ExportSqlPanel
from app.ui.widgets import HeaderLabel, hsep

if TYPE_CHECKING:
    from app.ui.gas_setup_wizard import GasSetupWizard


class ExportEditorShell(QWidget):
    """Owns the view composition and view-level helpers for the editor."""

    changed = Signal()
    query_changed = Signal()
    schedule_changed = Signal()
    history_changed = Signal()
    test_requested = Signal()
    run_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        gas_setup_wizard_factory: Callable[..., "GasSetupWizard"] | None = None,
    ) -> None:
        super().__init__(parent)
        self._gas_setup_wizard_factory = gas_setup_wizard_factory
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

        root.addWidget(HeaderLabel("Адрес обработки"))
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self._webhook_edit = QLineEdit(self)
        self._webhook_edit.setPlaceholderText("https://... (необязательно)")
        url_row.addWidget(self._webhook_edit, stretch=1)
        self._gas_setup_wizard_btn = QPushButton("Подключить таблицу...", self)
        url_row.addWidget(self._gas_setup_wizard_btn)
        root.addLayout(url_row)

        self._google_sheets_panel = ExportGoogleSheetsPanel(self)
        root.addWidget(self._google_sheets_panel)

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
        self._webhook_edit.editingFinished.connect(self._on_webhook_changed)
        self._gas_setup_wizard_btn.clicked.connect(self._open_gas_setup_wizard)
        self._google_sheets_panel.changed.connect(self.changed)
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
        with QSignalBlocker(self._webhook_edit):
            self._webhook_edit.setText(url)
        self._google_sheets_panel.set_target_url(url)

    def gas_sheet_name(self) -> str:
        return self._google_sheets_panel.sheet_name()

    def gas_write_mode(self) -> str:
        return self._google_sheets_panel.write_mode()

    def set_gas_options(
        self,
        *,
        sheet_name: str,
        write_mode: str,
    ) -> None:
        self._google_sheets_panel.set_gas_options(
            sheet_name=sheet_name,
            write_mode=write_mode,
        )

    def schedule_enabled(self) -> bool:
        return self._schedule_panel.schedule_enabled()

    def schedule_mode(self) -> ScheduleMode:
        return self._schedule_panel.schedule_mode()

    def schedule_value(self) -> str:
        return self._schedule_panel.schedule_value()

    def set_schedule(self, enabled: bool, mode: ScheduleMode | str, value: str) -> None:
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

    def _on_webhook_changed(self) -> None:
        self._google_sheets_panel.set_target_url(self.webhook_url())
        self.changed.emit()

    def _open_gas_setup_wizard(self) -> None:
        dialog_factory = self._gas_setup_wizard_factory
        if dialog_factory is None:
            from app.ui.gas_setup_wizard import GasSetupWizard

            dialog_factory = GasSetupWizard

        dialog = dialog_factory(
            initial_webhook_url=self.webhook_url(),
            parent=self,
        )
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return

        selected = dialog.selected_config()
        self.set_webhook_url(str(selected.get("webhook_url", "") or "").strip())
        self.set_gas_options(
            sheet_name=self.gas_sheet_name(),
            write_mode=self.gas_write_mode(),
        )
        self.changed.emit()
