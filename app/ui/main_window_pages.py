"""Helpers for building the MainWindow page stack."""

from dataclasses import dataclass

from PySide6.QtWidgets import QStackedWidget, QWidget

from app.config import ConfigManager
from app.ui.dashboard_widget import DashboardWidget
from app.ui.export_jobs_widget import ExportJobsWidget
from app.ui.settings_widget import SettingsWidget


@dataclass(slots=True)
class MainWindowPages:
    stack: QStackedWidget
    dashboard: DashboardWidget
    export_jobs: ExportJobsWidget
    settings_widget: SettingsWidget


def build_main_window_pages(
    config: ConfigManager,
    current_version: str,
    parent: QWidget,
) -> MainWindowPages:
    stack = QStackedWidget()
    dashboard = DashboardWidget(config, parent)
    export_jobs = ExportJobsWidget(config, parent)
    settings_widget = SettingsWidget(config, current_version, parent)
    stack.addWidget(dashboard)
    stack.addWidget(export_jobs)
    stack.addWidget(settings_widget)
    return MainWindowPages(
        stack=stack,
        dashboard=dashboard,
        export_jobs=export_jobs,
        settings_widget=settings_widget,
    )

