"""Tests for UpdateApplyWorker."""

from app.workers.update_worker import UpdateApplyWorker


def test_update_apply_worker_emits_applied_and_finished(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        "app.workers.update_worker.apply_downloaded_update",
        lambda path, exit_hook=None: calls.append((path, callable(exit_hook))),
    )

    worker = UpdateApplyWorker("C:/tmp/payload.exe")
    events: list[str] = []
    worker.applied.connect(lambda: events.append("applied"))
    worker.finished.connect(lambda: events.append("finished"))

    worker.run()

    assert calls == [("C:/tmp/payload.exe", True)]
    assert events == ["applied", "finished"]


def test_update_apply_worker_emits_error_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.workers.update_worker.apply_downloaded_update",
        lambda path, exit_hook=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    worker = UpdateApplyWorker("C:/tmp/payload.exe")
    events: list[tuple[str, str]] = []
    worker.error.connect(lambda message: events.append(("error", message)))
    worker.finished.connect(lambda: events.append(("finished", "")))

    worker.run()

    assert events == [("error", "boom"), ("finished", "")]
