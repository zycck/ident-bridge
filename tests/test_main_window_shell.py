# -*- coding: utf-8 -*-
"""Tests for extracted MainWindow shell/composite layout."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget

from app.ui.main_window_shell import MainWindowShell
from app.ui.title_bar import CustomTitleBar


def test_main_window_shell_exposes_titlebar_stack_and_nav_buttons(qtbot) -> None:
    stack = QStackedWidget()
    stack.addWidget(QWidget())
    stack.addWidget(QWidget())
    qtbot.addWidget(stack)

    shell = MainWindowShell(
        current_version="3.14.4",
        stack=stack,
        on_navigate=lambda _idx: None,
        on_debug=lambda: None,
    )
    qtbot.addWidget(shell)

    assert isinstance(shell.title_bar(), CustomTitleBar)
    assert shell.stack() is stack
    assert len(shell.nav_buttons()) == 3
    assert shell.normal_icons()[0].isNull() is False
    assert shell.active_icons()[0].isNull() is False


def test_main_window_shell_uses_passed_stack_in_layout(qtbot) -> None:
    stack = QStackedWidget()
    page = QLabel("page")
    qtbot.addWidget(page)
    stack.addWidget(page)
    qtbot.addWidget(stack)

    shell = MainWindowShell(
        current_version="3.14.4",
        stack=stack,
        on_navigate=lambda _idx: None,
        on_debug=lambda: None,
    )
    qtbot.addWidget(shell)

    assert shell.stack().currentWidget() is page
    assert shell.stack().parent() is not None
    assert shell.title_bar().parent() is shell
    assert int(shell.layout().alignment()) == 0
