#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight tracemalloc-based UI lifecycle smoke for iDentBridge.

This script is intentionally non-invasive: it exercises repeated widget
construction/teardown cycles and reports retained allocations so future
performance work can start from evidence instead of guesswork.
"""

import argparse
import gc
import os
import sys
import tempfile
import tracemalloc
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication, QWidget

import app.config as config_module
from app.config import ConfigManager
from app.core.constants import APP_VERSION
from app.ui.debug_window import DebugWindow
from app.ui.error_dialog import ErrorDialog
from app.ui.export_job_editor import ExportJobEditor
from app.ui.main_window import MainWindow
from app.ui.settings_widget import SettingsWidget
from app.ui.sql_editor import SqlEditorDialog
from app.ui.test_run_dialog import TestRunDialog
from main import _load_app_icon, _load_fonts, _load_theme


def _process_events(app: QApplication, rounds: int = 6) -> None:
    for _ in range(rounds):
        app.processEvents()


def _prepare_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        _load_app_icon(app)
        _load_fonts(app)
        theme = _load_theme()
        if theme:
            app.setStyleSheet(theme)
    return app


def _rebind_temp_config_dir(temp_root: Path) -> None:
    config_module.CONFIG_DIR = temp_root / "config"
    config_module.CONFIG_PATH = config_module.CONFIG_DIR / "config.json"


def _dispose_widget(widget: QWidget, app: QApplication) -> None:
    widget.hide()
    widget.deleteLater()
    _process_events(app)


def _run_main_window_cycle(app: QApplication, iteration: int) -> None:
    with tempfile.TemporaryDirectory(prefix=f"ident-perf-main-{iteration}-") as tmp:
        _rebind_temp_config_dir(Path(tmp))
        config = ConfigManager()
        window = MainWindow(config, APP_VERSION)
        window.show()
        _process_events(app)
        window._cleanup()
        window._tray.hide()
        _dispose_widget(window, app)


def _run_debug_window_cycle(app: QApplication, iteration: int) -> None:
    dialog = DebugWindow(parent=None)
    dialog.show()
    _process_events(app)
    _dispose_widget(dialog, app)


def _run_sql_editor_cycle(app: QApplication, iteration: int) -> None:
    dialog = SqlEditorDialog("SELECT 1 AS demo", parent=None)
    dialog.show()
    _process_events(app)
    _dispose_widget(dialog, app)


def _run_error_dialog_cycle(app: QApplication, iteration: int) -> None:
    dialog = ErrorDialog(RuntimeError(f"perf-cycle-{iteration}"), parent=None)
    dialog.show()
    _process_events(app)
    _dispose_widget(dialog, app)


def _sample_export_job(iteration: int) -> dict:
    return {
        "id": f"perf-job-{iteration}",
        "name": f"Perf export {iteration}",
        "sql_query": "SELECT 1",
        "webhook_url": "",
        "schedule_enabled": False,
        "schedule_mode": "daily",
        "schedule_value": "",
        "history": [],
    }


def _run_export_editor_cycle(app: QApplication, iteration: int) -> None:
    with tempfile.TemporaryDirectory(prefix=f"ident-perf-export-{iteration}-") as tmp:
        _rebind_temp_config_dir(Path(tmp))
        config = ConfigManager()
        editor = ExportJobEditor(_sample_export_job(iteration), config)
        editor.show()
        _process_events(app)
        editor.stop_scheduler()
        editor.stop_timers()
        _dispose_widget(editor, app)


def _run_settings_widget_cycle(app: QApplication, iteration: int) -> None:
    with tempfile.TemporaryDirectory(prefix=f"ident-perf-settings-{iteration}-") as tmp:
        _rebind_temp_config_dir(Path(tmp))
        config = ConfigManager()
        widget = SettingsWidget(config, APP_VERSION)
        widget.show()
        _process_events(app)
        _dispose_widget(widget, app)


def _run_test_run_dialog_cycle(app: QApplication, iteration: int) -> None:
    dialog = TestRunDialog({}, initial_sql="SELECT 1", auto_run=False, parent=None)
    dialog.show()
    _process_events(app)
    _dispose_widget(dialog, app)


SCENARIOS = {
    "main-window": _run_main_window_cycle,
    "debug-window": _run_debug_window_cycle,
    "sql-editor": _run_sql_editor_cycle,
    "error-dialog": _run_error_dialog_cycle,
    "export-editor": _run_export_editor_cycle,
    "settings-widget": _run_settings_widget_cycle,
    "test-run-dialog": _run_test_run_dialog_cycle,
}


def _run_cycles(app: QApplication, scenario: str, cycles: int) -> None:
    names = list(SCENARIOS) if scenario == "all" else [scenario]
    for iteration in range(cycles):
        for name in names:
            SCENARIOS[name](app, iteration)
        gc.collect()
        _process_events(app)


def _format_top_stats(stats: list[tracemalloc.StatisticDiff], top: int) -> str:
    lines = []
    for stat in stats[:top]:
        size_kib = stat.size_diff / 1024
        lines.append(f"{stat.traceback[0].filename}:{stat.traceback[0].lineno} -> {size_kib:+.1f} KiB")
    return "\n".join(lines) if lines else "(no tracked allocations)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(*SCENARIOS.keys(), "all"),
        default="all",
        help="Which lifecycle to exercise.",
    )
    parser.add_argument("--cycles", type=int, default=5, help="How many repeated cycles to run.")
    parser.add_argument("--top", type=int, default=8, help="How many allocation diffs to print.")
    parser.add_argument(
        "--fail-over-kib",
        type=float,
        default=None,
        help="Optional non-zero exit threshold for positive retained KiB.",
    )
    args = parser.parse_args()

    app = _prepare_app()
    gc.collect()
    tracemalloc.start(25)
    before = tracemalloc.take_snapshot()

    _run_cycles(app, args.scenario, args.cycles)

    gc.collect()
    _process_events(app, rounds=10)
    after = tracemalloc.take_snapshot()
    stats = after.compare_to(before, "filename")
    positive_kib = sum(stat.size_diff for stat in stats if stat.size_diff > 0) / 1024

    print(f"scenario={args.scenario}")
    print(f"cycles={args.cycles}")
    print(f"positive_retained_kib={positive_kib:.1f}")
    print("top_diffs:")
    print(_format_top_stats(stats, args.top))

    if args.fail_over_kib is not None and positive_kib > args.fail_over_kib:
        print(
            f"FAIL: retained allocations {positive_kib:.1f} KiB exceed "
            f"threshold {args.fail_over_kib:.1f} KiB"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
