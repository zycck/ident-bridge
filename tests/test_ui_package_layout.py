from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "app" / "ui"


def test_canonical_ui_feature_packages_exist() -> None:
    expected_paths = [
        UI_ROOT / "shared" / "__init__.py",
        UI_ROOT / "shared" / "theme.py",
        UI_ROOT / "shared" / "widgets.py",
        UI_ROOT / "shared" / "worker_threads.py",
        UI_ROOT / "shared" / "icons" / "__init__.py",
        UI_ROOT / "main_window" / "__init__.py",
        UI_ROOT / "dashboard" / "__init__.py",
        UI_ROOT / "settings" / "__init__.py",
        UI_ROOT / "settings" / "sql" / "__init__.py",
        UI_ROOT / "export_jobs" / "__init__.py",
        UI_ROOT / "export_jobs" / "editor" / "__init__.py",
        UI_ROOT / "export_jobs" / "editor" / "google_sheets" / "__init__.py",
        UI_ROOT / "export_jobs" / "tiles" / "__init__.py",
        UI_ROOT / "export_jobs" / "history" / "__init__.py",
        UI_ROOT / "sql_editor" / "__init__.py",
        UI_ROOT / "dialogs" / "__init__.py",
        UI_ROOT / "dialogs" / "debug" / "__init__.py",
        UI_ROOT / "dialogs" / "error" / "__init__.py",
        UI_ROOT / "dialogs" / "test_run" / "__init__.py",
        UI_ROOT / "AGENTS.md",
    ]

    missing = [str(path.relative_to(ROOT)) for path in expected_paths if not path.exists()]
    assert not missing, f"Missing canonical UI paths: {missing}"


def test_old_and_new_ui_import_paths_resolve_same_symbols() -> None:
    pairs = [
        ("app.ui.theme", "Theme", "app.ui.shared.theme", "Theme"),
        ("app.ui.widgets", "BusyPushButton", "app.ui.shared.widgets", "BusyPushButton"),
        ("app.ui.threading", "run_worker", "app.ui.shared.worker_threads", "run_worker"),
        ("app.ui.debug_window", "DebugWindow", "app.ui.dialogs.debug.window", "DebugWindow"),
        ("app.ui.error_dialog", "ErrorDialog", "app.ui.dialogs.error.dialog", "ErrorDialog"),
        (
            "app.ui.export_google_sheets_panel",
            "ExportGoogleSheetsPanel",
            "app.ui.export_jobs.editor.google_sheets.panel",
            "ExportGoogleSheetsPanel",
        ),
        ("app.ui.test_run_dialog", "TestRunDialog", "app.ui.dialogs.test_run.dialog", "TestRunDialog"),
    ]

    for old_module_name, old_symbol_name, new_module_name, new_symbol_name in pairs:
        old_module = importlib.import_module(old_module_name)
        new_module = importlib.import_module(new_module_name)
        assert getattr(old_module, old_symbol_name) is getattr(new_module, new_symbol_name)


def test_main_window_package_exposes_main_window_class() -> None:
    package = importlib.import_module("app.ui.main_window")
    module = importlib.import_module("app.ui.main_window.main_window")

    assert package.MainWindow is module.MainWindow

