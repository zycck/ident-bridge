# -*- coding: utf-8 -*-
"""SQL editor section for ExportJobEditor."""

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.export_sql import format_sql_for_tsql_editor, validate_sql
from app.ui.sql_editor import SqlEditor
from app.ui.theme import Theme
from app.ui.widgets import HeaderLabel


class ExportSqlPanel(QWidget):
    """Owns SQL text editing and syntax status display."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(HeaderLabel("SQL запрос"))

        self._query_edit = SqlEditor()
        self._query_edit.setPlaceholderText("SELECT … FROM …")
        self._query_edit.setMinimumHeight(200)
        self._query_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._query_edit.textChanged.connect(self.changed)
        self._query_edit.expand_requested.connect(self._open_in_window)
        root.addWidget(self._query_edit, stretch=1)

        syntax_row = QHBoxLayout()
        syntax_row.setSpacing(8)

        self._syntax_lbl = QLabel("")
        self._syntax_lbl.setObjectName("syntaxStatus")
        self._syntax_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent; "
            f"padding-top: 2px;"
        )
        syntax_row.addWidget(self._syntax_lbl)
        syntax_row.addStretch()

        root.addLayout(syntax_row)

    def sql_text(self) -> str:
        return self._query_edit.toPlainText().strip()

    def set_sql_text(self, sql: str) -> None:
        self._query_edit.blockSignals(True)
        try:
            self._query_edit.setPlainText(sql)
        finally:
            self._query_edit.blockSignals(False)

    def refresh_syntax(self) -> None:
        sql = self.sql_text()
        if not sql:
            self._syntax_lbl.setText("")
            self._syntax_lbl.setToolTip("")
            return
        ok, msg = validate_sql(sql)
        if ok:
            self._syntax_lbl.setStyleSheet(
                f"color: {Theme.success}; "
                f"font-size: {Theme.font_size_xs}pt; "
                f"background: transparent;"
            )
            self._syntax_lbl.setText("✓ SQL")
            self._syntax_lbl.setToolTip("")
            return
        self._syntax_lbl.setStyleSheet(
            f"color: {Theme.error}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        short = msg if len(msg) <= 36 else msg[:33] + "…"
        self._syntax_lbl.setText(f"✗ {short}")
        self._syntax_lbl.setToolTip(msg)

    @Slot()
    def _open_in_window(self) -> None:
        from app.ui.sql_editor import SqlEditorDialog

        dialog = SqlEditorDialog(
            self._query_edit.toPlainText(),
            parent=self,
            on_format=format_sql_for_tsql_editor,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._query_edit.setPlainText(dialog.text())
