# -*- coding: utf-8 -*-
"""TestRunDialog — выполняет SQL-запрос и отображает результат в таблице."""
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
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
from app.core.constants import (
    TEST_DIALOG_AUTO_RUN_MS,
    TEST_DIALOG_DEFAULT_H,
    TEST_DIALOG_DEFAULT_W,
    TEST_DIALOG_MIN_H,
    TEST_DIALOG_MIN_W,
)
from app.core.sql_client import SqlClient
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme
from app.ui.threading import run_worker

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

    test_completed = Signal(bool, int, str)  # (ok, rows, err_message)

    def __init__(
        self,
        cfg: AppConfig,
        initial_sql: str = "",
        auto_run: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._worker: _QueryWorker | None = None

        self.setWindowTitle("Тестовый запрос")
        self.setMinimumSize(TEST_DIALOG_MIN_W, TEST_DIALOG_MIN_H)
        self.resize(TEST_DIALOG_DEFAULT_W, TEST_DIALOG_DEFAULT_H)

        self._build_ui()
        self._editor.setPlainText(initial_sql or _DEFAULT_SQL)

        # Auto-run: execute immediately when dialog opens (used from card test btn)
        if auto_run and initial_sql:
            QTimer.singleShot(TEST_DIALOG_AUTO_RUN_MS, self._run_query)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

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
        self._editor.setFixedHeight(fm.lineSpacing() * 5 + 14)
        root.addWidget(self._editor)

        # ── Button row ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._run_btn = QPushButton("  Запустить")
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setIcon(lucide('play', color=Theme.gray_900, size=14))
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
        run_worker(self, worker, pin_attr="_worker")
        worker.result.connect(self._on_result)
        worker.error.connect(self._on_error)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_result(self, result: QueryResult) -> None:
        self._populate_table(result)
        self._set_status(f"{result.count} строк · {result.duration_ms} мс", color="")
        self._run_btn.setEnabled(True)
        self.test_completed.emit(True, result.count, "")

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._set_status(msg, color="#EF4444")
        self._run_btn.setEnabled(True)
        self.test_completed.emit(False, 0, msg)

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
