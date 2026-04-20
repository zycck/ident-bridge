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
from app.ui.theme import Theme

# Fallback SQL used only when the editor card is genuinely empty AND
# the caller didn't pass anything. In the normal path the user's
# current query from the card is forwarded and shown verbatim — the
# dialog never silently overwrites it (see audit bug fix, 2026-04-17).
_FALLBACK_SQL_WHEN_NO_CARD_QUERY = (
    "SELECT TABLE_SCHEMA, TABLE_NAME\n"
    "FROM INFORMATION_SCHEMA.TABLES\n"
    "WHERE TABLE_TYPE = 'BASE TABLE'\n"
    "ORDER BY TABLE_SCHEMA, TABLE_NAME"
)


# Explicit QSS for the dialog. Qt on Windows sometimes fails to
# inherit QApplication.styleSheet() into a top-level QDialog shown
# modally, which left the dialog rendering with the Qt default dark
# palette over the app's light theme — hence the "black dialog" bug
# report. Same pattern is used in SqlEditorDialog for the same
# reason.
_DIALOG_QSS = (
    f"QDialog {{"
    f"  background-color: {Theme.surface_tinted};"
    f"  color: {Theme.gray_900};"
    f"}}"
    f"QWidget {{"
    f"  background-color: {Theme.surface_tinted};"
    f"  color: {Theme.gray_900};"
    f"}}"
    f"QPlainTextEdit {{"
    f"  background-color: {Theme.surface};"
    f"  color: {Theme.gray_900};"
    f"  border: 1px solid {Theme.border_strong};"
    f"  border-radius: {Theme.radius}px;"
    f"  padding: 8px 10px;"
    f"  selection-background-color: {Theme.primary_200};"
    f"  selection-color: {Theme.primary_900};"
    f"}}"
    f"QPlainTextEdit:focus {{"
    f"  border-color: {Theme.border_focus};"
    f"}}"
    f"QTableWidget {{"
    f"  background-color: {Theme.surface};"
    f"  alternate-background-color: {Theme.gray_50};"
    f"  color: {Theme.gray_900};"
    f"  gridline-color: {Theme.border};"
    f"  border: 1px solid {Theme.border};"
    f"  border-radius: {Theme.radius}px;"
    f"}}"
    f"QTableWidget::item {{"
    f"  padding: 4px 6px;"
    f"  color: {Theme.gray_900};"
    f"}}"
    f"QHeaderView::section {{"
    f"  background-color: {Theme.gray_100};"
    f"  color: {Theme.gray_700};"
    f"  border: none;"
    f"  border-right: 1px solid {Theme.border};"
    f"  border-bottom: 1px solid {Theme.border};"
    f"  padding: 4px 8px;"
    f"  font-weight: {Theme.font_weight_semi};"
    f"}}"
    f"QPushButton {{"
    f"  min-height: 28px;"
    f"  padding: 0 14px;"
    f"  border: 1px solid {Theme.border_strong};"
    f"  border-radius: {Theme.radius}px;"
    f"  background-color: {Theme.surface};"
    f"  color: {Theme.gray_700};"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {Theme.gray_50};"
    f"  border-color: {Theme.border_focus};"
    f"  color: {Theme.primary_800};"
    f"}}"
    f"QPushButton:disabled {{"
    f"  background-color: {Theme.gray_100};"
    f"  color: {Theme.gray_400};"
    f"}}"
    f"QPushButton#primaryBtn {{"
    f"  background-color: {Theme.primary_500};"
    f"  color: {Theme.gray_900};"
    f"  border: 1px solid {Theme.primary_600};"
    f"  font-weight: {Theme.font_weight_semi};"
    f"}}"
    f"QPushButton#primaryBtn:hover {{"
    f"  background-color: {Theme.primary_600};"
    f"  border-color: {Theme.primary_700};"
    f"}}"
)


class TestRunDialog(QDialog):
    """Dialog for executing a SQL query and previewing the result table."""

    __test__ = False
    test_completed = Signal(bool, int, str, int)

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
        # Force light-theme surface. See _DIALOG_QSS comment above.
        self.setStyleSheet(_DIALOG_QSS)

        self._build_ui()
        # Prefer the caller's SQL verbatim — the test dialog exists to
        # test the exact query the user is editing on the card. Only
        # show the INFORMATION_SCHEMA fallback when nothing was passed
        # and the card really is empty.
        sql_to_show = initial_sql if initial_sql else _FALLBACK_SQL_WHEN_NO_CARD_QUERY
        self._shell.set_sql_text(sql_to_show)
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
