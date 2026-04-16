# -*- coding: utf-8 -*-
"""View shell for the test-run SQL dialog."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import QueryResult
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme


class TestRunDialogShell(QWidget):
    """Owns the test-run dialog layout and view-only helpers."""

    run_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        sql_label = QLabel("SQL запрос:", self)
        sql_label.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: 600;")
        root.addWidget(sql_label)

        self._editor = QPlainTextEdit(self)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(mono)
        fm = self._editor.fontMetrics()
        self._editor.setFixedHeight(fm.lineSpacing() * 5 + 14)
        root.addWidget(self._editor)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._run_btn = QPushButton("  Запустить", self)
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setIcon(lucide("play", color=Theme.gray_900, size=14))
        self._run_btn.clicked.connect(self.run_requested)
        btn_row.addWidget(self._run_btn)

        self._status_label = QLabel("", self)
        self._status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        btn_row.addWidget(self._status_label, stretch=1)

        root.addLayout(btn_row)

        self._table = QTableWidget(self)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self._table, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self._close_btn = QPushButton("Закрыть", self)
        self._close_btn.clicked.connect(self.close_requested)
        close_row.addWidget(self._close_btn)
        root.addLayout(close_row)

    def sql_text(self) -> str:
        return self._editor.toPlainText().strip()

    def set_sql_text(self, sql: str) -> None:
        self._editor.setPlainText(sql)

    def set_run_enabled(self, enabled: bool) -> None:
        self._run_btn.setEnabled(enabled)

    def set_status(self, text: str, *, color: str) -> None:
        self._status_label.setStyleSheet(f"color: {color};" if color else "")
        self._status_label.setText(text)

    def populate_result(self, result: QueryResult) -> None:
        self._table.clear()
        self._table.setColumnCount(len(result.columns))
        self._table.setHorizontalHeaderLabels(result.columns)
        self._table.setRowCount(result.count)

        for row_idx, row in enumerate(result.rows):
            for col_idx, value in enumerate(row):
                self._table.setItem(
                    row_idx,
                    col_idx,
                    QTableWidgetItem("" if value is None else str(value)),
                )

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)

    def run_button(self) -> QPushButton:
        return self._run_btn

    def close_button(self) -> QPushButton:
        return self._close_btn

    def status_label(self) -> QLabel:
        return self._status_label

    def table(self) -> QTableWidget:
        return self._table
