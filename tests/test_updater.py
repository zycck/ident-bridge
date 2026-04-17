"""Tests for updater download/apply helpers."""
from pathlib import Path

from app.core import updater


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._payload


class _FakeOpener:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.calls: list[tuple[object, int]] = []

    def open(self, url: str, timeout: int = 0):
        self.calls.append((url, timeout))
        return _FakeResponse(self._payload)


def test_download_update_writes_temp_payload(monkeypatch, tmp_path):
    target = tmp_path / "downloads"
    target.mkdir()
    opener = _FakeOpener(b"payload-ok")

    monkeypatch.setattr("app.core.updater.MIN_DOWNLOAD_BYTES", 1)
    monkeypatch.setattr("app.core.updater.tempfile.gettempdir", lambda: str(target))
    monkeypatch.setattr("app.core.updater.urllib.request.build_opener", lambda *a, **k: opener)

    path = updater.download_update("https://example.com/update.exe")

    assert Path(path).exists()
    assert Path(path).read_bytes() == b"payload-ok"
    assert len(opener.calls) == 1
    request, timeout = opener.calls[0]
    assert timeout == 120
    assert request.full_url == "https://example.com/update.exe"
    assert request.headers["User-agent"] == updater.USER_AGENT


def test_pick_download_url_prefers_expected_exe_name():
    release = {
        "assets": [
            {"name": "notes.txt", "browser_download_url": "https://example.com/notes.txt"},
            {"name": "iDentSync.exe", "browser_download_url": "https://example.com/iDentSync.exe"},
            {"name": "other.exe", "browser_download_url": "https://example.com/other.exe"},
        ]
    }

    assert updater._pick_download_url(release) == "https://example.com/iDentSync.exe"


def test_check_latest_ignores_non_executable_assets(monkeypatch):
    class _FakeApiResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return (
                b'{"tag_name":"v1.2.3","assets":['
                b'{"name":"readme.txt","browser_download_url":"https://example.com/readme.txt"},'
                b'{"name":"portable.exe","browser_download_url":"https://example.com/portable.exe"}'
                b"]}"
            )

    monkeypatch.setattr("app.core.updater.urllib.request.urlopen", lambda *a, **k: _FakeApiResponse())

    assert updater.check_latest("example/repo") == ("v1.2.3", "https://example.com/portable.exe")


def test_apply_downloaded_update_uses_exit_hook(monkeypatch, tmp_path):
    downloaded = tmp_path / "payload.exe"
    downloaded.write_bytes(b"payload")
    exe_path = tmp_path / "iDentBridge.exe"
    exe_path.write_bytes(b"current")

    popen_calls = []
    exit_calls = []

    monkeypatch.setattr("app.core.updater.get_exe_path", lambda: str(exe_path))
    monkeypatch.setattr("app.core.updater.tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("app.core.updater.subprocess.Popen", lambda *a, **k: popen_calls.append((a, k)))

    updater.apply_downloaded_update(str(downloaded), exit_hook=lambda: exit_calls.append(True))

    assert exit_calls == [True]
    assert len(popen_calls) == 1
    assert (tmp_path / "_ident_updater.py").exists()
