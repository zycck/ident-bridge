"""Tests for extracted ExportJobsWidget deletion flow."""

from app.ui.export_jobs_delete_controller import ExportJobsDeleteController


class _FakeSignal:
    def __init__(self, *, disconnect_error: Exception | None = None) -> None:
        self._callbacks: list = []
        self._disconnect_error = disconnect_error
        self.disconnect_calls = 0

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._callbacks.clear()
        if self._disconnect_error is not None:
            raise self._disconnect_error

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class _FakeEditor:
    def __init__(self, name: str, *, running: bool = False) -> None:
        self._name = name
        self._running = running
        self.changed = _FakeSignal()
        self.sync_completed = _FakeSignal()
        self.history_changed = _FakeSignal()
        self.failure_alert = _FakeSignal()
        self.stop_scheduler_calls = 0
        self.stop_timers_calls = 0
        self.deleted = False

    def to_job(self) -> dict:
        return {"id": "job-1", "name": self._name}

    def stop_scheduler(self) -> None:
        self.stop_scheduler_calls += 1

    def stop_timers(self) -> None:
        self.stop_timers_calls += 1

    def deleteLater(self) -> None:  # noqa: N802
        self.deleted = True


class _FakeLater:
    def __init__(self) -> None:
        self.deleted = False

    def deleteLater(self) -> None:  # noqa: N802
        self.deleted = True


class _FakeTilesPage:
    def __init__(self) -> None:
        self.removed_ids: list[str] = []
        self.tile = _FakeLater()
        self.refresh_calls = 0
        self.reflow_calls = 0

    def remove_tile(self, job_id: str):
        self.removed_ids.append(job_id)
        return self.tile

    def refresh_empty(self) -> None:
        self.refresh_calls += 1

    def reflow_tiles(self) -> None:
        self.reflow_calls += 1


class _FakeEditorPage:
    def __init__(self) -> None:
        self.removed_ids: list[str] = []
        self.scroll = _FakeLater()

    def remove_editor(self, job_id: str):
        self.removed_ids.append(job_id)
        return self.scroll


def _build_controller():
    warnings: list[tuple[str, str]] = []
    confirmations: list[str] = []
    saves: list[bool] = []
    show_tiles_calls: list[bool] = []
    history_changed: list[bool] = []
    tiles_page = _FakeTilesPage()
    editor_page = _FakeEditorPage()
    controller = ExportJobsDeleteController(
        tiles_page=tiles_page,
        editor_page=editor_page,
        save_jobs=lambda: saves.append(True),
        show_tiles=lambda: show_tiles_calls.append(True),
        emit_history_changed=lambda: history_changed.append(True),
        warn_running=lambda title, message: warnings.append((title, message)),
        confirm_delete=lambda name: confirmations.append(name) or True,
    )
    return (
        controller,
        tiles_page,
        editor_page,
        warnings,
        confirmations,
        saves,
        show_tiles_calls,
        history_changed,
    )


def test_delete_job_aborts_when_editor_is_running() -> None:
    (
        controller,
        tiles_page,
        editor_page,
        warnings,
        confirmations,
        saves,
        show_tiles_calls,
        history_changed,
    ) = _build_controller()
    editors = {"job-1": _FakeEditor("Orders", running=True)}

    removed = controller.delete_job(
        job_id="job-1",
        editors=editors,
        current_editor_id=None,
    )

    assert removed is False
    assert warnings == [("Выгрузка выполняется", "Дождитесь завершения выгрузки перед удалением.")]
    assert confirmations == []
    assert saves == []
    assert show_tiles_calls == []
    assert history_changed == []
    assert tiles_page.removed_ids == []
    assert editor_page.removed_ids == []
    assert "job-1" in editors


def test_delete_job_cancel_keeps_all_state_intact() -> None:
    (
        _controller,
        tiles_page,
        editor_page,
        warnings,
        confirmations,
        saves,
        show_tiles_calls,
        history_changed,
    ) = _build_controller()
    controller = ExportJobsDeleteController(
        tiles_page=tiles_page,
        editor_page=editor_page,
        save_jobs=lambda: saves.append(True),
        show_tiles=lambda: show_tiles_calls.append(True),
        emit_history_changed=lambda: history_changed.append(True),
        warn_running=lambda title, message: warnings.append((title, message)),
        confirm_delete=lambda name: confirmations.append(name) or False,
    )
    editors = {"job-1": _FakeEditor("Orders")}

    removed = controller.delete_job(
        job_id="job-1",
        editors=editors,
        current_editor_id=None,
    )

    assert removed is False
    assert confirmations == ["Orders"]
    assert saves == []
    assert show_tiles_calls == []
    assert history_changed == []
    assert tiles_page.removed_ids == []
    assert editor_page.removed_ids == []
    assert "job-1" in editors


def test_delete_job_confirm_removes_editor_tile_and_saves() -> None:
    (
        controller,
        tiles_page,
        editor_page,
        _warnings,
        confirmations,
        saves,
        show_tiles_calls,
        history_changed,
    ) = _build_controller()
    editor = _FakeEditor("Orders")
    editors = {"job-1": editor}

    removed = controller.delete_job(
        job_id="job-1",
        editors=editors,
        current_editor_id=None,
    )

    assert removed is True
    assert confirmations == ["Orders"]
    assert editor.stop_scheduler_calls == 1
    assert editor.stop_timers_calls == 1
    assert editor.deleted is True
    assert editor_page.removed_ids == ["job-1"]
    assert editor_page.scroll.deleted is True
    assert tiles_page.removed_ids == ["job-1"]
    assert tiles_page.tile.deleted is True
    assert saves == [True]
    assert tiles_page.refresh_calls == 1
    assert tiles_page.reflow_calls == 1
    assert history_changed == [True]
    assert show_tiles_calls == []
    assert editors == {}


def test_delete_job_disconnects_editor_signals_after_changed_emits() -> None:
    (
        controller,
        _tiles_page,
        _editor_page,
        _warnings,
        _confirmations,
        saves,
        _show_tiles_calls,
        _history_changed,
    ) = _build_controller()
    editor = _FakeEditor("Orders")
    editor.changed = _FakeSignal(disconnect_error=RuntimeError("already gone"))
    editor.sync_completed = _FakeSignal(disconnect_error=TypeError("already gone"))
    editor.history_changed = _FakeSignal(disconnect_error=RuntimeError("already gone"))
    editor.failure_alert = _FakeSignal(disconnect_error=TypeError("already gone"))
    editors = {"job-1": editor}
    changed_events: list[object] = []
    sync_events: list[object] = []
    history_events: list[bool] = []
    failure_events: list[tuple[str, int]] = []

    editor.changed.connect(lambda payload: changed_events.append(payload))
    editor.sync_completed.connect(lambda payload: sync_events.append(payload))
    editor.history_changed.connect(lambda: history_events.append(True))
    editor.failure_alert.connect(lambda name, count: failure_events.append((name, count)))

    editor.changed.emit({"job_id": "job-1"})

    removed = controller.delete_job(
        job_id="job-1",
        editors=editors,
        current_editor_id=None,
    )

    editor.changed.emit({"job_id": "job-1"})
    editor.sync_completed.emit({"rows_synced": 1})
    editor.history_changed.emit()
    editor.failure_alert.emit("Orders", 3)

    assert removed is True
    assert changed_events == [{"job_id": "job-1"}]
    assert sync_events == []
    assert history_events == []
    assert failure_events == []
    assert editor.changed.disconnect_calls == 1
    assert editor.sync_completed.disconnect_calls == 1
    assert editor.history_changed.disconnect_calls == 1
    assert editor.failure_alert.disconnect_calls == 1
    assert saves == [True]
    assert editors == {}


def test_delete_job_current_editor_returns_to_tiles() -> None:
    (
        controller,
        _tiles_page,
        _editor_page,
        _warnings,
        _confirmations,
        _saves,
        show_tiles_calls,
        _history_changed,
    ) = _build_controller()
    editors = {"job-1": _FakeEditor("Orders")}

    removed = controller.delete_job(
        job_id="job-1",
        editors=editors,
        current_editor_id="job-1",
    )

    assert removed is True
    assert show_tiles_calls == [True]
