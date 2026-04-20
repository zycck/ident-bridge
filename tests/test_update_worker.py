"""Tests for update workers."""

from app.workers.update_worker import UpdateDownloadWorker, UpdateWorker


def test_update_worker_preserves_release_digest(monkeypatch) -> None:
    digest = "a" * 64

    monkeypatch.setattr(
        "app.workers.update_worker.check_latest",
        lambda repo: ("v1.2.3", "https://example.com/update.exe", f"sha256:{digest}"),
    )
    monkeypatch.setattr("app.workers.update_worker.is_newer", lambda latest, current: True)

    worker = UpdateWorker(current_version="1.0.0", repo="example/repo")
    events: list[tuple[str, str]] = []
    digest_events: list[tuple[str, str, str | None]] = []
    worker.update_available.connect(lambda tag, url: events.append((tag, url)))
    worker.update_available_with_digest.connect(
        lambda tag, url, digest: digest_events.append((tag, url, digest))
    )
    worker.finished.connect(lambda: events.append(("finished", "")))

    worker.check()

    assert worker.latest_digest == f"sha256:{digest}"
    assert events == [("v1.2.3", "https://example.com/update.exe"), ("finished", "")]
    assert digest_events == [("v1.2.3", "https://example.com/update.exe", f"sha256:{digest}")]


def test_update_download_worker_forwards_expected_digest(monkeypatch) -> None:
    digest = "a" * 64
    calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "app.workers.update_worker.download_update",
        lambda url, expected_digest=None: calls.append((url, expected_digest)) or "C:/tmp/payload.exe",
    )

    worker = UpdateDownloadWorker(
        "https://example.com/update.exe",
        expected_digest=f"sha256:{digest}",
    )
    events: list[str] = []
    worker.downloaded.connect(lambda path: events.append(path))
    worker.finished.connect(lambda: events.append("finished"))

    worker.run()

    assert calls == [("https://example.com/update.exe", f"sha256:{digest}")]
    assert events == ["C:/tmp/payload.exe", "finished"]
