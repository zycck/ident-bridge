# -*- coding: utf-8 -*-
"""TestRunDialog — выполняет SQL-запрос и отображает результат в таблице."""
from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
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

from app.config import AppConfig, QueryResult
from app.core.app_logger import get_logger
from app.core.sql_client import SqlClient

_log = get_logger(__name__)

_DEFAULT_SQL = (
    "SELECT TABLE_SCHEMA, TABLE_NAME\n"
    "FROM INFORMATION_SCHEMA.TABLES\n"
    "WHERE TABLE_TYPE = 'BASE TABLE'\n"
    "ORDER BY TABLE_SCHEMA, TABLE_NAME"
)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _QueryWorker(QObject):
    result: Signal = Signal(object)   # QueryResult
    error:  Signal = Signal(str)
    finished: Signal = Signal()

    def __init__(self, cfg: AppConfig, sql: str) -> None:
        super().__init__()
        self._cfg = cfg
        self._sql = sql

    @Slot()
    def run(self) -> None:
        client = SqlClient(self._cfg)
        try:
            client.connect()
            query_result = client.query(self._sql)
            _log.info("Query: %d строк за %d мс", query_result.count, query_result.duration_ms)
            self.result.emit(query_result)
        except ConnectionError as exc:
            _log.error("Query connection failed: %s", exc)
            self.error.emit(str(exc))
        except Exception as exc:
            _log.error("Query failed: %s", exc)
            self.error.emit("Ошибка выполнения запроса")
        finally:
            client.disconnect()
            self.finished.emit()


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class TestRunDialog(QDialog):
    """Диалог тестового SQL-запроса. Принимает AppConfig — сохранять настройки не нужно."""

    def __init__(
        self,
        cfg: AppConfig,
        initial_sql: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._worker: _QueryWorker | None = None

        self.setWindowTitle("Тестовый запрос")
        self.setMinimumSize(700, 520)
        self.resize(860, 580)

        self._build_ui()
        self._editor.setPlainText(initial_sql or _DEFAULT_SQL)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        # ── SQL editor label ──────────────────────────────────────────
        sql_label = QLabel("SQL запрос:")
        sql_label.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: 600;")
        root.addWidget(sql_label)

        # ── SQL editor ────────────────────────────────────────────────
        self._editor = QPlainTextEdit()
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(mono)
        fm = self._editor.fontMetrics()
        self._editor.setFixedHeight(fm.lineSpacing() * 6 + 18)
        root.addWidget(self._editor)

        # ── Button row ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._run_btn = QPushButton("  Запустить")
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setIcon(qta.icon('fa5s.play', color='#FFFFFF'))
        self._run_btn.clicked.connect(self._run_query)
        btn_row.addWidget(self._run_btn)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        btn_row.addWidget(self._status_label, stretch=1)

        root.addLayout(btn_row)

        # ── Results table ─────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self._table, stretch=1)

        # ── Close button ──────────────────────────────────────────────
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def _run_query(self) -> None:
        sql = self._editor.toPlainText().strip()
        if not sql:
            return

        self._run_btn.setEnabled(False)
        self._set_status("Выполнение…", color="")

        worker = _QueryWorker(self._cfg, sql)
        self._worker = worker  # keep alive — GC would delete it otherwise
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.result.connect(self._on_result)
        worker.error.connect(self._on_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda w=worker: setattr(self, '_worker', None)
            if self._worker is w else None
        )

        thread.start()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_result(self, result: QueryResult) -> None:
        self._populate_table(result)
        self._set_status(f"{result.count} строк · {result.duration_ms} мс", color="")
        self._run_btn.setEnabled(True)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._set_status(msg, color="#EF4444")
        self._run_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _populate_table(self, result: QueryResult) -> None:
        self._table.clear()
        self._table.setColumnCount(len(result.columns))
        self._table.setHorizontalHeaderLabels(result.columns)
        self._table.setRowCount(result.count)

        for row_idx, row in enumerate(result.rows):
            for col_idx, value in enumerate(row):
                self._table.setItem(
                    row_idx, col_idx,
                    QTableWidgetItem("" if value is None else str(value)),
                )

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)

    def _set_status(self, text: str, *, color: str) -> None:
        self._status_label.setStyleSheet(f"color: {color};" if color else "")
        self._status_label.setText(text)
