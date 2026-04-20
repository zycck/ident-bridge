from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from app.ui.export_google_sheets_panel import ExportGoogleSheetsPanel


def test_google_sheets_panel_closes_overlay_popup_with_host(qtbot) -> None:
    host = QWidget()
    host.setLayout(QVBoxLayout())
    panel = ExportGoogleSheetsPanel(host)
    host.layout().addWidget(panel)
    qtbot.addWidget(host)

    panel.set_target_url("https://script.google.com/macros/s/abc/exec")
    panel.set_sheet_options(["Orders", "Archive"])
    host.show()

    field = panel._sheet_name_field
    qtbot.mouseClick(field._edit, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(field._edit, "Or")

    qtbot.waitUntil(
        lambda: field._suggestions_frame.parent() is host and field._suggestions_frame.isVisible(),
        timeout=2000,
    )

    assert "алиасы столбцов" in panel._alias_hint_label.text()

    panel.close()

    qtbot.waitUntil(lambda: host.findChild(QFrame, "sheetSuggestionsFrame") is None, timeout=2000)
