from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "app" / "ui"


def _read_ui_source(relative_path: str) -> str:
    return (UI_ROOT / relative_path).read_text(encoding="utf-8")


def test_priority_ui_files_do_not_keep_known_dark_hex_literals() -> None:
    forbidden_literals = {
        "dialogs/debug/window.py": ["#0B0D12", "#1E1E24", "#6B7280", "#D4D4D8"],
        "dialogs/debug/formatting.py": [
            "#22D3EE",
            "#52525B",
            "#71717A",
            "#A1A1AA",
            "#A78BFA",
            "#D4D4D8",
            "#EF4444",
            "#F87171",
            "#FBBF24",
        ],
    }

    for file_name, literals in forbidden_literals.items():
        source = _read_ui_source(file_name)
        for literal in literals:
            assert literal not in source, f"{file_name} still contains {literal}"


def test_popup_and_dialog_sources_use_shared_light_helpers() -> None:
    widgets_source = _read_ui_source("shared/widgets.py")
    tile_source = _read_ui_source("export_jobs/tiles/tile.py")
    lifecycle_source = _read_ui_source("main_window/lifecycle.py")
    debug_source = _read_ui_source("dialogs/debug/window.py")
    error_source = _read_ui_source("dialogs/error/dialog.py")

    assert "def style_menu_popup(" in widgets_source
    assert "def apply_light_window_palette(" in widgets_source
    assert "style_menu_popup(" in tile_source
    assert "style_menu_popup(" in lifecycle_source
    assert "style_combo_popup(" in debug_source
    assert "apply_light_window_palette(" in debug_source
    assert "style_light_dialog(" in error_source
    assert "apply_light_window_palette(" in error_source
