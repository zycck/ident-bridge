# -*- coding: utf-8 -*-
"""Tests for extracted SQL editor interaction controller."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPlainTextEdit, QPushButton

from app.ui.sql_editor_controller import SqlEditorInteractionController


def test_sql_editor_controller_repositions_expand_button(qtbot) -> None:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.resize(320, 200)
    button = QPushButton(editor.viewport())
    button.resize(22, 22)
    controller = SqlEditorInteractionController(
        editor=editor,
        expand_button=button,
        tab_spaces=4,
        margin=6,
    )

    controller.reposition_expand_button()

    expected_x = editor.viewport().width() - button.width() - 6
    assert button.pos() == QPoint(expected_x, 6)


def test_sql_editor_controller_handles_tab_and_backtab(qtbot) -> None:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    button = QPushButton(editor.viewport())
    controller = SqlEditorInteractionController(
        editor=editor,
        expand_button=button,
        tab_spaces=4,
        margin=6,
    )

    tab_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    assert controller.handle_key_press(tab_event) is True
    assert editor.toPlainText() == "    "

    editor.setPlainText("    SELECT 1")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    backtab_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)

    assert controller.handle_key_press(backtab_event) is True
    assert editor.toPlainText() == "SELECT 1"
