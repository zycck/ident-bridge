"""Tests for extracted MainWindow pages helper."""

from PySide6.QtWidgets import QStackedWidget, QWidget

from app.ui.dashboard_widget import DashboardWidget
from app.ui.export_jobs_widget import ExportJobsWidget
from app.ui.main_window_pages import build_main_window_pages
from app.ui.settings_widget import SettingsWidget


def test_build_main_window_pages_keeps_expected_page_order(qtbot, tmp_config) -> None:
    host = QWidget()
    qtbot.addWidget(host)

    pages = build_main_window_pages(tmp_config, "0.0.1-test", host)

    assert isinstance(pages.stack, QStackedWidget)
    assert isinstance(pages.dashboard, DashboardWidget)
    assert isinstance(pages.export_jobs, ExportJobsWidget)
    assert isinstance(pages.settings_widget, SettingsWidget)
    assert pages.stack.widget(0) is pages.dashboard
    assert pages.stack.widget(1) is pages.export_jobs
    assert pages.stack.widget(2) is pages.settings_widget
