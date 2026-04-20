import logging

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from app.ui import export_google_sheets_panel as panel_module
from app.ui.export_google_sheets_panel import ExportGoogleSheetsPanel


class _FakeResponse:
    def __init__(self, body: str, *, status: int = 200) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


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


def test_fetch_google_sheet_options_reports_non_json_response(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        assert timeout == 5.0
        if "action=ping" in request.full_url:
            return _FakeResponse('{"ok": true, "status": "ready", "message": "pong"}')
        assert "action=sheets" in request.full_url
        return _FakeResponse("<html>not json</html>")

    monkeypatch.setattr(panel_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="вернул не JSON"):
        panel_module.fetch_google_sheet_options("https://script.google.com/macros/s/abc/exec")


def test_fetch_google_sheet_options_surfaces_access_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        assert timeout == 5.0
        return _FakeResponse('{"ok": false, "error_code": "UNAUTHORIZED", "message": "forbidden"}')

    monkeypatch.setattr(panel_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="запрещён"):
        panel_module.fetch_google_sheet_options("https://script.google.com/macros/s/abc/exec")


def test_sheet_options_worker_logs_fetch_error(caplog) -> None:
    worker = panel_module._SheetOptionsWorker("https://script.google.com/macros/s/abc/exec")
    seen_errors: list[str] = []
    worker.error.connect(seen_errors.append)

    def fail_fetch(url: str, *, timeout: float = 5.0) -> list[str]:
        raise panel_module._SheetOptionsFetchError(
            "Адрес обработки вернул не JSON. Проверьте, что указан адрес /exec опубликованного веб-приложения Apps Script.",
            debug_message="response_preview=<html>not json</html>",
        )

    original = panel_module.fetch_google_sheet_options
    panel_module.fetch_google_sheet_options = fail_fetch
    try:
        with caplog.at_level(logging.WARNING):
            worker.run()
    finally:
        panel_module.fetch_google_sheet_options = original

    assert seen_errors == [
        "Адрес обработки вернул не JSON. Проверьте, что указан адрес /exec опубликованного веб-приложения Apps Script."
    ]
    assert "Не удалось обновить список листов Google Таблиц" in caplog.text
    assert "response_preview=<html>not json</html>" in caplog.text
