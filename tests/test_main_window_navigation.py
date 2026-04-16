# -*- coding: utf-8 -*-
"""Tests for extracted MainWindow navigation shell."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QPushButton, QStackedWidget, QWidget

from app.ui.dashboard_widget import DashboardWidget
from app.ui.export_jobs_widget import ExportJobsWidget
from app.ui.main_window import MainWindow
from app.ui.main_window_navigation import MainWindowNavigationController
from app.ui.settings_widget import SettingsWidget


def _icon(color: str) -> QIcon:
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def _buttons(qtbot, count: int) -> list[QPushButton]:
    buttons = []
    for _ in range(count):
        button = QPushButton("x")
        qtbot.addWidget(button)
        buttons.append(button)
    return buttons


def test_navigation_controller_switches_stack_and_active_buttons(qtbot) -> None:
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    for _ in range(3):
        page = QWidget()
        qtbot.addWidget(page)
        stack.addWidget(page)
    buttons = _buttons(qtbot, 3)
    normal = [_icon("gray") for _ in range(3)]
    active = [_icon("green") for _ in range(3)]

    controller = MainWindowNavigationController(
        stack=stack,
        buttons=buttons,
        normal_icons=normal,
        active_icons=active,
    )

    controller.navigate(2)

    assert stack.currentIndex() == 2
    assert buttons[2].objectName() == "navBtnActive"
    assert buttons[0].objectName() == "navBtn"
    assert buttons[2].icon().cacheKey() == active[2].cacheKey()
    assert buttons[0].icon().cacheKey() == normal[0].cacheKey()


def test_navigation_controller_reselecting_same_index_is_idempotent(qtbot) -> None:
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    for _ in range(2):
        page = QWidget()
        qtbot.addWidget(page)
        stack.addWidget(page)
    buttons = _buttons(qtbot, 2)
    normal = [_icon("gray") for _ in range(2)]
    active = [_icon("green") for _ in range(2)]

    controller = MainWindowNavigationController(
        stack=stack,
        buttons=buttons,
        normal_icons=normal,
        active_icons=active,
    )

    controller.navigate(0)
    before_key = buttons[0].icon().cacheKey()
    controller.navigate(0)

    assert stack.currentIndex() == 0
    assert buttons[0].objectName() == "navBtnActive"
    assert buttons[0].icon().cacheKey() == before_key


def test_main_window_navigation_keeps_expected_page_order(qtbot, tmp_config) -> None:
    window = MainWindow(tmp_config, "0.0.1-test")
    qtbot.addWidget(window)
    try:
        assert isinstance(window._stack.widget(0), DashboardWidget)
        assert isinstance(window._stack.widget(1), ExportJobsWidget)
        assert isinstance(window._stack.widget(2), SettingsWidget)
    finally:
        window._cleanup()


def test_main_window_nav_buttons_switch_expected_pages(qtbot, tmp_config) -> None:
    window = MainWindow(tmp_config, "0.0.1-test")
    qtbot.addWidget(window)
    try:
        qtbot.mouseClick(window._nav_btns[1], Qt.MouseButton.LeftButton)
        assert window._stack.currentIndex() == 1
        qtbot.mouseClick(window._nav_btns[2], Qt.MouseButton.LeftButton)
        assert window._stack.currentIndex() == 2
    finally:
        window._cleanup()
