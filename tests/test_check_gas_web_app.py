from __future__ import annotations

import urllib.error

from tools.check_gas_web_app import build_action_url, probe_action


class _FakeResponse:
    def __init__(self, body: str, *, status: int = 200, url: str = "https://example.com/exec?action=ping", content_type: str = "application/json; charset=utf-8") -> None:
        self.status = status
        self._body = body.encode("utf-8")
        self._url = url
        self.headers = {"Content-Type": content_type}

    def read(self, _limit: int | None = None) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_build_action_url_replaces_action_query_parameter() -> None:
    url = "https://script.google.com/macros/s/abc/exec?action=old&foo=1"

    result = build_action_url(url, "sheets")

    assert result == "https://script.google.com/macros/s/abc/exec?foo=1&action=sheets"


def test_probe_action_parses_json_payload(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        assert "action=ping" in request.full_url
        assert timeout == 10.0
        return _FakeResponse('{"ok": true, "status": "ready"}', url=request.full_url)

    monkeypatch.setattr("tools.check_gas_web_app.urllib.request.urlopen", fake_urlopen)

    result = probe_action("https://script.google.com/macros/s/abc/exec", "ping")

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["content_type"].startswith("application/json")
    assert result["payload"]["status"] == "ready"


def test_probe_action_keeps_html_preview_for_server_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        return _FakeResponse(
            "<html><title>Error</title><body>TypeError: iDBBackend.handleRequest is not a function</body></html>",
            url=request.full_url,
            content_type="text/html; charset=utf-8",
        )

    monkeypatch.setattr("tools.check_gas_web_app.urllib.request.urlopen", fake_urlopen)

    result = probe_action("https://script.google.com/macros/s/abc/exec", "sheets")

    assert result["ok"] is False
    assert result["content_type"].startswith("text/html")
    assert "TypeError: iDBBackend.handleRequest is not a function" in result["preview"]


def test_probe_action_surfaces_http_error_payload(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001
        raise urllib.error.HTTPError(
            request.full_url,
            500,
            "Internal Server Error",
            hdrs={"Content-Type": "text/html; charset=utf-8"},
            fp=None,
        )

    monkeypatch.setattr("tools.check_gas_web_app.urllib.request.urlopen", fake_urlopen)

    result = probe_action("https://script.google.com/macros/s/abc/exec", "ping")

    assert result["ok"] is False
    assert result["status_code"] == 500
