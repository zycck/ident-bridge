# -*- coding: utf-8 -*-
"""Standalone T-SQL syntax highlighter used by SqlEditor."""

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QTextDocument

from app.ui.sql_highlight_helpers import TSQL_FUNCTIONS, TSQL_KEYWORDS, make_format
from app.ui.theme import Theme


class SqlHighlighter(QSyntaxHighlighter):
    """T-SQL syntax highlighter — keywords, functions, strings, numbers, comments."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)

        self._kw_fmt = make_format(Theme.syntax_keyword, bold=True)
        self._fn_fmt = make_format(Theme.syntax_function)
        self._string_fmt = make_format(Theme.syntax_string)
        self._number_fmt = make_format(Theme.syntax_number)
        self._comment_fmt = make_format(Theme.syntax_comment, italic=True)
        self._operator_fmt = make_format(Theme.syntax_operator)

        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        kw_pattern = r"\b(?:" + "|".join(TSQL_KEYWORDS) + r")\b"
        self._rules.append(
            (
                QRegularExpression(
                    kw_pattern,
                    QRegularExpression.PatternOption.CaseInsensitiveOption,
                ),
                self._kw_fmt,
            )
        )

        fn_pattern = r"\b(?:" + "|".join(TSQL_FUNCTIONS) + r")\b"
        self._rules.append(
            (
                QRegularExpression(
                    fn_pattern,
                    QRegularExpression.PatternOption.CaseInsensitiveOption,
                ),
                self._fn_fmt,
            )
        )

        self._rules.append((QRegularExpression(r"\b\d+(?:\.\d+)?\b"), self._number_fmt))
        self._rules.append((QRegularExpression(r"[=<>!+\-*/%]+"), self._operator_fmt))
        self._line_comment_re = QRegularExpression(r"--[^\n]*")

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for regex, fmt in self._rules:
            iterator = regex.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        i = 0
        n = len(text)
        while i < n:
            if text[i] == "'":
                start = i
                i += 1
                while i < n:
                    if text[i] == "'":
                        if i + 1 < n and text[i + 1] == "'":
                            i += 2
                            continue
                        i += 1
                        break
                    i += 1
                self.setFormat(start, i - start, self._string_fmt)
            else:
                i += 1

        iterator = self._line_comment_re.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self._comment_fmt)
