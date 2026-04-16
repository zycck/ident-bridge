# -*- coding: utf-8 -*-
"""Tests for extracted SQL highlighter."""

from PySide6.QtGui import QTextDocument

from app.ui.sql_highlighter import SqlHighlighter
from app.ui.theme import Theme


def _spans_for(text: str) -> list[tuple[int, int, str]]:
    document = QTextDocument()
    highlighter = SqlHighlighter(document)
    document.setPlainText(text)
    highlighter.rehighlight()
    block = document.firstBlock()
    return [
        (
            fmt_range.start,
            fmt_range.length,
            fmt_range.format.foreground().color().name(),
        )
        for fmt_range in block.layout().formats()
    ]


def test_sql_highlighter_marks_keywords_numbers_and_comments(qapp_session) -> None:
    spans = _spans_for("SELECT 42 -- comment")

    assert (0, 6, Theme.syntax_keyword.lower()) in spans
    assert (7, 2, Theme.syntax_number.lower()) in spans
    assert (10, 10, Theme.syntax_comment.lower()) in spans


def test_sql_highlighter_marks_strings_and_comment_priority(qapp_session) -> None:
    spans = _spans_for("SELECT 'GO' -- SELECT")

    assert (0, 6, Theme.syntax_keyword.lower()) in spans
    assert (7, 4, Theme.syntax_string.lower()) in spans
    assert (12, 9, Theme.syntax_comment.lower()) in spans
