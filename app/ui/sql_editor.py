"""
SqlEditor — QPlainTextEdit subclass with T-SQL syntax highlighting,
tab-to-spaces, and explicit Cascadia Code font. Used by ExportJobEditor
to give users a real SQL editing experience instead of a plain text
input.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QFont,
    QKeyEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from app.ui.theme import Theme
from app.ui.sql_editor_controller import SqlEditorInteractionController
from app.ui.sql_highlighter import SqlHighlighter


class SqlEditor(QPlainTextEdit):
    """QPlainTextEdit with T-SQL syntax highlighting and tab → 4 spaces."""

    TAB_SPACES = 4
    EXPAND_BTN_MARGIN = 6

    expand_requested = Signal()  # emitted when the inline expand icon is clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Force monospace font even though app default is Manrope
        mono = QFont("Cascadia Code", 10)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(mono)
        # Tab width = 4 monospace chars
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self.TAB_SPACES)
        # Disable line wrap so SQL stays on its lines
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        # Attach syntax highlighter to the document
        self._highlighter = SqlHighlighter(self.document())

        # Inline expand button (child of viewport, anchored top-right)
        self._expand_btn = QPushButton(self.viewport())
        from app.ui.lucide_icons import lucide
        self._expand_btn.setIcon(lucide("maximize-2", color=Theme.gray_500, size=12))
        self._expand_btn.setFixedSize(22, 22)
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setToolTip("Открыть в полном окне")
        self._expand_btn.setStyleSheet(
            "QPushButton {"
            "  border: 1px solid transparent;"
            "  background: rgba(255, 255, 255, 200);"
            "  border-radius: 4px;"
            "  padding: 0;"
            "  min-height: 0;"
            "}"
            f"QPushButton:hover {{"
            f"  background-color: {Theme.gray_100};"
            f"  border-color: {Theme.border_strong};"
            f"}}"
        )
        self._expand_btn.clicked.connect(self.expand_requested)
        self._expand_btn.raise_()
        self._controller = SqlEditorInteractionController(
            editor=self,
            expand_button=self._expand_btn,
            tab_spaces=self.TAB_SPACES,
            margin=self.EXPAND_BTN_MARGIN,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._controller.reposition_expand_button()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if self._controller.handle_key_press(event):
            return
        super().keyPressEvent(event)


class SqlEditorDialog(QDialog):
    """
    Standalone full-window SQL editor for users who want the most space
    possible. Wraps a SqlEditor in a large dialog with Save/Cancel buttons.
    The editor's text is pulled from the parent SqlEditor on open and
    written back on accept.
    """

    def __init__(
        self,
        initial_text: str,
        parent: QWidget | None = None,
        *,
        on_format: object = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("SQL запрос — iDentBridge")
        self.resize(1100, 720)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        # Force light theme on the dialog and its plain text edit child.
        # QDialog sometimes ignores the global app stylesheet when shown as
        # a separate top-level window on Windows — force the surface colors
        # explicitly so the SQL editor doesn't render as black-on-black.
        self.setStyleSheet(
            f"QDialog {{"
            f"  background-color: {Theme.surface_tinted};"
            f"}}"
            f"QPlainTextEdit {{"
            f"  background-color: {Theme.surface};"
            f"  color: {Theme.gray_900};"
            f"  border: 1px solid {Theme.border_strong};"
            f"  border-radius: {Theme.radius}px;"
            f"  padding: 12px 14px;"
            f"  selection-background-color: {Theme.primary_200};"
            f"  selection-color: {Theme.primary_900};"
            f"}}"
            f"QPlainTextEdit:focus {{"
            f"  border-color: {Theme.border_focus};"
            f"}}"
            f"QPushButton {{"
            f"  min-height: 32px;"
            f"  padding: 0 16px;"
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
            f"QPushButton#primaryBtn {{"
            f"  background-color: {Theme.primary_500};"
            f"  color: {Theme.gray_900};"
            f"  border: 1px solid {Theme.primary_600};"
            f"  font-weight: 600;"
            f"}}"
            f"QPushButton#primaryBtn:hover {{"
            f"  background-color: {Theme.primary_600};"
            f"  border-color: {Theme.primary_700};"
            f"}}"
        )

        self._on_format = on_format
        from app.ui.sql_editor_dialog_shell import SqlEditorDialogShell

        self._shell = SqlEditorDialogShell(
            initial_text,
            has_formatter=on_format is not None,
            parent=self,
        )
        self._shell.accept_requested.connect(self.accept)
        self._shell.reject_requested.connect(self.reject)
        self._shell.format_requested.connect(self._do_format)

        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._shell)

    def _do_format(self) -> None:
        if self._on_format is None:
            return
        sql = self._shell.text()
        try:
            formatted = self._on_format(sql)
            if formatted:
                self._shell.set_text(formatted)
        except Exception:
            pass

    def text(self) -> str:
        return self._shell.text()
