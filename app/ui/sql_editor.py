# -*- coding: utf-8 -*-
"""
SqlEditor — QPlainTextEdit subclass with T-SQL syntax highlighting,
tab-to-spaces, and explicit Cascadia Code font. Used by ExportJobEditor
to give users a real SQL editing experience instead of a plain text
input.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from app.ui.theme import Theme


# ── T-SQL keyword sets ────────────────────────────────────────────────
_TSQL_KEYWORDS = {
    # DML
    "SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "VALUES", "INTO",
    "OUTPUT", "RETURNING",
    # DDL
    "CREATE", "DROP", "ALTER", "TRUNCATE", "TABLE", "VIEW", "INDEX",
    "PROCEDURE", "FUNCTION", "TRIGGER", "DATABASE", "SCHEMA",
    # Clauses
    "FROM", "WHERE", "GROUP", "HAVING", "ORDER", "BY", "LIMIT", "OFFSET",
    "TOP", "DISTINCT", "ALL", "UNION", "INTERSECT", "EXCEPT", "WITH",
    "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS", "ON",
    "USING", "AS", "ASC", "DESC",
    # Predicates
    "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN", "LIKE", "IS", "NULL",
    "TRUE", "FALSE", "ANY", "SOME",
    # Flow
    "CASE", "WHEN", "THEN", "ELSE", "END", "IF", "BEGIN", "WHILE",
    "RETURN", "DECLARE", "SET", "PRINT", "EXEC", "EXECUTE", "GO",
    # Constraints / types referenced as keywords
    "PRIMARY", "FOREIGN", "KEY", "REFERENCES", "DEFAULT", "CHECK",
    "UNIQUE", "CONSTRAINT", "IDENTITY", "CASCADE",
}

_TSQL_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "ISNULL", "NULLIF",
    "CAST", "CONVERT", "TRY_CAST", "TRY_CONVERT", "FORMAT", "LEN",
    "LEFT", "RIGHT", "SUBSTRING", "REPLACE", "TRIM", "LTRIM", "RTRIM",
    "UPPER", "LOWER", "CONCAT", "CHAR", "ASCII", "GETDATE", "SYSDATETIME",
    "DATEADD", "DATEDIFF", "DATEPART", "YEAR", "MONTH", "DAY",
    "ROW_NUMBER", "RANK", "DENSE_RANK", "PARTITION", "OVER", "ABS",
    "ROUND", "FLOOR", "CEILING", "POWER", "SQRT",
}


def _make_format(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class SqlHighlighter(QSyntaxHighlighter):
    """T-SQL syntax highlighter — keywords, functions, strings, numbers, comments."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)

        # Color choices tuned for the lime brand on a white surface
        self._kw_fmt        = _make_format("#1D4ED8", bold=True)   # blue-700
        self._fn_fmt        = _make_format("#9333EA")              # purple-600
        self._string_fmt    = _make_format("#15803D")              # green-700
        self._number_fmt    = _make_format("#C2410C")              # orange-700
        self._comment_fmt   = _make_format("#94A3B8", italic=True) # slate-400
        self._operator_fmt  = _make_format("#475569")              # slate-600

        # Pre-compile regex rules
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        # Keywords (whole-word, case-insensitive)
        kw_pattern = r"\b(?:" + "|".join(_TSQL_KEYWORDS) + r")\b"
        self._rules.append((
            QRegularExpression(
                kw_pattern,
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            ),
            self._kw_fmt,
        ))

        # Functions (whole-word, case-insensitive)
        fn_pattern = r"\b(?:" + "|".join(_TSQL_FUNCTIONS) + r")\b"
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
