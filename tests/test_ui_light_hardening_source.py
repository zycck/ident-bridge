from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_ui_source(*parts: str) -> str:
    path = ROOT.joinpath("app", "ui", *parts)
    source = path.read_text(encoding="utf-8")
    stripped = source.lstrip("\ufeff").strip()
    prefix = "from app.ui."
    suffix = " import *"
    if stripped.startswith(prefix) and stripped.endswith(suffix):
        target = stripped[len(prefix):-len(suffix)].replace(".", "/")
        source = (ROOT / "app" / "ui" / f"{target}.py").read_text(encoding="utf-8")
    return source


def test_debug_window_uses_shared_light_helpers_and_no_dark_log_style() -> None:
    source = _read_ui_source("debug_window.py")

    assert "style_combo_popup(self._level_filter)" in source
    assert "apply_light_window_palette(self" in source
    assert "#0B0D12" not in source
    assert "#1E1E24" not in source
    assert "#D4D4D8" not in source


def test_export_job_tile_and_tray_menu_use_shared_light_menu_helper() -> None:
    tile_source = _read_ui_source("export_job_tile.py")
    tray_source = _read_ui_source("main_window_lifecycle.py")

    assert "style_menu_popup(menu)" in tile_source
    assert "style_menu_popup(menu)" in tray_source


def test_export_jobs_pages_pin_light_surface_background() -> None:
    pages_source = _read_ui_source("export_jobs_pages.py")
    shell_source = _read_ui_source("export_editor_shell.py")
    collection_source = _read_ui_source("export_jobs_collection_controller.py")

    assert "Theme.surface_tinted" in pages_source
    assert "exportJobsTilesPage" in pages_source
    assert "exportJobsEditorPage" in pages_source
    assert "apply_light_window_palette(self, background=Theme.surface_tinted)" in pages_source
    assert "apply_light_window_palette(self, background=Theme.surface_tinted)" in shell_source
    assert "Theme.surface_tinted" in collection_source


def test_error_dialog_and_debug_window_drop_footer_monitoring() -> None:
    dialog_source = _read_ui_source("error_dialog.py")
    debug_source = _read_ui_source("debug_window.py")

    assert "apply_light_window_palette(self" in dialog_source
    assert "resource_monitor" not in debug_source
    assert "resource_monitor_bar" not in debug_source


def test_debug_formatting_moves_off_raw_hex_constants() -> None:
    source = _read_ui_source("debug_window_formatting.py")

    for raw_hex in (
        "#22D3EE",
        "#52525B",
        "#71717A",
        "#A1A1AA",
        "#A78BFA",
        "#D4D4D8",
        "#EF4444",
        "#F87171",
        "#FBBF24",
    ):
        assert raw_hex not in source
