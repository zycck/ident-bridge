from __future__ import annotations

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigManager, QueryResult
from app.workers.sql_worker import SqlWorker

_DEFAULT_SQL = "SELECT TOP 10 * FROM dbo.Receptions WITH (NOLOCK)"


class TestRunDialog(QDialog):
    def __init__(
        self,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._config = config
        self._thread: QThread | None = None

        self.setWindowTitle("Тестовый запрос")
        self.setMinimumSize(700, 500)
        self.resize(780, 540)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # ── 1. SQL label ──────────────────────────────────────────────────
        sql_label = QLabel("SQL запрос:")
        sql_label.setStyleSheet("color: #6B7280;")
        root.addWidget(sql_label)

        # ── 2. SQL editor ─────────────────────────────────────────────────
        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("Courier New", 9))
        self._editor.setPlainText(_DEFAULT_SQL)
        # ~5 visible lines: font metrics × line count + margins
        fm = self._editor.fontMetrics()
        line_h = fm.lineSpacing()
        self._editor.setFixedHeight(line_h * 5 + 16)
        root.addWidget(self._editor)

        # ── 3. Button row (Run + status label) ────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._run_btn = QPushButton("Запустить")
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.clicked.connect(self._run_query)
        btn_row.addWidget(self._run_btn)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        btn_row.addWidget(self._status_label, stretch=1)

        root.addLayout(btn_row)

        # ── 4. Results table ──────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self._table, stretch=1)

        # ── 5. Close button (right-aligned) ───────────────────────────────
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Закрыть")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    # ── Public slots / handlers ───────────────────────────────────────────

    def _run_query(self) -> None:
        sql_text = self._editor.toPlainText().strip()
        if not sql_text:
            return

        self._run_btn.setEnabled(False)
        self._set_status("Выполнение...", color="")

        worker = SqlWorker(self._config)
        thread = QThread(self)
        self._thread = thread

        worker.moveToThread(thread)

        # thread.started cannot pass args; use a lambda to forward sql_text
        thread.started.connect(lambda: worker.run_query(sql_text))

        worker.result.connect(self._on_result)
        worker.error.connect(self._on_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()

    def _on_result(self, result: QueryResult) -> None:
        self._populate_table(result)
        self._set_status(
            f"{result.count} строк · {result.duration_ms} мс",
            color="",
        )
        self._run_btn.setEnabled(True)

    def _on_error(self, msg: str) -> None:
        self._set_status(msg, color="#EF4444")
        self._run_btn.setEnabled(True)

    def _populate_table(self, result: QueryResult) -> None:
        self._table.clear()
        self._table.setColumnCount(len(result.columns))
        self._table.setHorizontalHeaderLabels(result.columns)
        self._table.setRowCount(len(result.rows))

        for row_idx, row in enumerate(result.rows):
            for col_idx, value in enumerate(row):
                cell_text = str(value) if value is not None else ""
                self._table.setItem(row_idx, col_idx, QTableWidgetItem(cell_text))

        self._table.resizeColumnsToContents()
        # Restore stretch on last column after resizeColumnsToContents resets it
        self._table.horizontalHeader().setStretchLastSection(True)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _set_status(self, text: str, *, color: str) -> None:
        style = f"color: {color};" if color else ""
        self._status_label.setStyleSheet(style)
        self._status_label.setText(text)
