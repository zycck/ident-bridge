# -*- coding: utf-8 -*-
"""
SqlEditor — QPlainTextEdit subclass with T-SQL syntax highlighting,
tab-to-spaces, and explicit Cascadia Code font. Used by ExportJobEditor
to give users a real SQL editing experience instead of a plain text
input.
"""
from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QFont,
    QKeyEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Theme
from app.ui.sql_highlight_helpers import TSQL_FUNCTIONS, TSQL_KEYWORDS, make_format


class SqlHighlighter(QSyntaxHighlighter):
    """T-SQL syntax highlighter — keywords, functions, strings, numbers, comments."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)

        # Color choices tuned for the lime brand on a white surface
        self._kw_fmt        = make_format(Theme.syntax_keyword, bold=True)
        self._fn_fmt        = make_format(Theme.syntax_function)
        self._string_fmt    = make_format(Theme.syntax_string)
        self._number_fmt    = make_format(Theme.syntax_number)
        self._comment_fmt   = make_format(Theme.syntax_comment, italic=True)
        self._operator_fmt  = make_format(Theme.syntax_operator)

        # Pre-compile regex rules
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        # Keywords (whole-word, case-insensitive)
        kw_pattern = r"\b(?:" + "|".join(TSQL_KEYWORDS) + r")\b"
        self._rules.append((
            QRegularExpression(
                kw_pattern,
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            ),
            self._kw_fmt,
        ))

        # Functions (whole-word, case-insensitive)
        fn_pattern = r"\b(?:" + "|".join(TSQL_FUNCTIONS) + r")\b"
        self._rules.append((
            QRegularExpression(
                fn_pattern,
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            ),
            self._fn_fmt,
        ))

        # Numbers (integers and decimals)
        self._rules.append((
            QRegularExpression(r"\b\d+(?:\.\d+)?\b"),
            self._number_fmt,
        ))

        # Operators (subtle)
        self._rules.append((
            QRegularExpression(r"[=<>!+\-*/%]+"),
            self._operator_fmt,
        ))

        # Strings: 'literal' with '' as escape — handled per-line
        # Single-quoted string: from ' to next ' (handle '' as escape via greedy [^']*)
        # Two passes: 1) find ranges of strings to mark, 2) mark them
        # Done in highlightBlock to handle multi-character escapes properly.

        # Single-line comments -- ...
        self._line_comment_re = QRegularExpression(r"--[^\n]*")

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        # Apply all simple rules first
        for regex, fmt in self._rules:
            iterator = regex.globalMatch(text)
            while iterator.hasNext():
                m = iterator.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

        # Strings — process character by character to handle '' escapes
        i = 0
        n = len(text)
        while i < n:
            if text[i] == "'":
                start = i
                i += 1
                while i < n:
                    if text[i] == "'":
                        if i + 1 < n and text[i + 1] == "'":
                            i += 2  # escaped quote
                            continue
                        i += 1  # closing quote
                        break
                    i += 1
                self.setFormat(start, i - start, self._string_fmt)
            else:
                i += 1

        # Single-line comments override everything (highest priority)
        iterator = self._line_comment_re.globalMatch(text)
        while iterator.hasNext():
            m = iterator.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._comment_fmt)


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

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition_expand_btn()

    def _reposition_expand_btn(self) -> None:
        vp = self.viewport()
        sz = self._expand_btn.size()
        x = vp.width() - sz.width() - self.EXPAND_BTN_MARGIN
        y = self.EXPAND_BTN_MARGIN
        self._expand_btn.move(max(0, x), max(0, y))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Tab inserts 4 spaces instead of \t
        if event.key() == Qt.Key.Key_Tab and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            cursor = self.textCursor()
            cursor.insertText(" " * self.TAB_SPACES)
            event.accept()
            return
        # Shift+Tab: dedent the current line by up to 4 spaces from the start
        if event.key() == Qt.Key.Key_Backtab:
            cursor = self.textCursor()
            cursor.movePosition(cursor.MoveOperation.StartOfLine)
            line_start = cursor.position()
            # Look at the next 4 chars
            block_text = cursor.block().text()
            spaces_to_remove = 0
            for ch in block_text[: self.TAB_SPACES]:
                if ch == " ":
                    spaces_to_remove += 1
                else:
                    break
            if spaces_to_remove > 0:
                cursor.setPosition(line_start)
                cursor.setPosition(line_start + spaces_to_remove, cursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
            event.accept()
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._editor = SqlEditor()
        self._editor.setPlainText(initial_text)
        self._editor.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._editor, stretch=1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        if on_format is not None:
            format_btn = QPushButton("Форматировать")
            format_btn.setFixedHeight(32)
            format_btn.clicked.connect(self._do_format)
            btn_row.addWidget(format_btn)
            self._on_format = on_format
        else:
            self._on_format = None

        btn_row.addStretch()

        cancel_btn = QPushButton("Отмена")
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("primaryBtn")
        save_btn.setFixedHeight(32)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _do_format(self) -> None:
        if self._on_format is None:
            return
        sql = self._editor.toPlainText()
        try:
            formatted = self._on_format(sql)
            if formatted:
                self._editor.setPlainText(formatted)
        except Exception:
            pass

    def text(self) -> str:
        return self._editor.toPlainText()
