"""TestRunDialog — выполняет SQL-запрос и отображает результат в таблице."""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from app.config import AppConfig
from app.core.constants import (
    TEST_DIALOG_AUTO_RUN_MS,
    TEST_DIALOG_DEFAULT_H,
    TEST_DIALOG_DEFAULT_W,
    TEST_DIALOG_MIN_H,
    TEST_DIALOG_MIN_W,
)
from app.ui.test_run_dialog_controller import TestRunDialogController
from app.ui.test_run_dialog_shell import TestRunDialogShell

_DEFAULT_SQL = (
    "SELECT TABLE_SCHEMA, TABLE_NAME\n"
    "FROM INFORMATION_SCHEMA.TABLES\n"
    "WHERE TABLE_TYPE = 'BASE TABLE'\n"
    "ORDER BY TABLE_SCHEMA, TABLE_NAME"
)


class TestRunDialog(QDialog):
    """Dialog for executing a SQL query and previewing the result table."""

    test_completed = Signal(bool, int, str)

    def __init__(
        self,
        cfg: AppConfig,
        initial_sql: str = "",
        auto_run: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Тестовый запрос")
        self.setMinimumSize(TEST_DIALOG_MIN_W, TEST_DIALOG_MIN_H)
        self.resize(TEST_DIALOG_DEFAULT_W, TEST_DIALOG_DEFAULT_H)

        self._build_ui()
        self._shell.set_sql_text(initial_sql or _DEFAULT_SQL)
        self._controller = TestRunDialogController(
            owner=self,
            shell=self._shell,
            cfg=cfg,
            emit_test_completed=self.test_completed.emit,
        )
        self._controller.wire()

        if auto_run and initial_sql:
            QTimer.singleShot(TEST_DIALOG_AUTO_RUN_MS, self._controller.run_query)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._shell = TestRunDialogShell(self)
        self._shell.close_requested.connect(self.reject)
        root.addWidget(self._shell)
