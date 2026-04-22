from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = (
    ROOT
    / "app"
    / "ui"
    / "export_jobs"
    / "editor"
    / "google_sheets"
    / "panel.py"
)


def test_google_sheets_panel_keeps_sheet_picker_as_overlay_popup() -> None:
    source = PANEL_PATH.read_text(encoding="utf-8")

    assert "from PySide6.QtWidgets import QCompleter" not in source
    assert ".setCompleter(" not in source
    assert "QListView" in source
    assert "_suggestions_frame" in source
    assert "Qt.WindowType.Popup" not in source
    assert "QSpinBox" not in source
    assert "_header_row_spin" not in source
    assert "_dedupe_edit" not in source
    assert 'root.addWidget(self._suggestions_frame)' not in source
    assert "self.window()" in source
    assert "self._sheet_name_field.setText(normalized[0])" not in source
    assert 'self._count_badge.setText(f"{len(self._all_options)}' in source
    assert "_alias_hint_label = QLabel(" in source
    assert "def shutdown(self) -> None:" in source
    assert "self._suggestions_frame.hide()" in source
    assert "self._overlay_parent.removeEventFilter(self)" in source
    assert "self._suggestions_frame.deleteLater()" in source
    assert "@override" in source
    assert "def closeEvent(self, event: QCloseEvent) -> None" in source
    assert "def hideEvent(self, event: QHideEvent) -> None" in source
    assert "QEvent.Type.Close" in source
    assert "auth_token" not in source
