"""Standalone T-SQL syntax highlighter used by SqlEditor."""

from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QTextDocument

from app.ui.sql_highlight_helpers import build_highlighter_assets


class SqlHighlighter(QSyntaxHighlighter):
    """T-SQL syntax highlighter — keywords, functions, strings, numbers, comments."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        (
            self._rules,
            self._line_comment_re,
            self._string_fmt,
            self._comment_fmt,
        ) = build_highlighter_assets()

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
