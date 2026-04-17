"""Tests for ExportJobsWidget navigation/lifecycle controller."""

from app.ui.export_jobs_navigation_controller import ExportJobsNavigationController


class _FakeStack:
    def __init__(self) -> None:
        self.indices: list[int] = []

    def setCurrentIndex(self, index: int) -> None:
        self.indices.append(index)


class _FakeEditorPage:
    def __init__(self, *, show_result: bool = True) -> None:
        self.show_calls: list[str] = []
        self._show_result = show_result

    def show_editor(self, job_id: str) -> bool:
        self.show_calls.append(job_id)
        return self._show_result


class _FakeEditor:
    def __init__(self) -> None:
        self.stop_scheduler_calls = 0
        self.stop_timers_calls = 0

    def stop_scheduler(self) -> None:
        self.stop_scheduler_calls += 1

    def stop_timers(self) -> None:
        self.stop_timers_calls += 1


def test_navigation_controller_routes_between_tiles_and_editor() -> None:
    stack = _FakeStack()
    editor_page = _FakeEditorPage()
    sync_calls: list[str] = []
    controller = ExportJobsNavigationController(
        stack=stack,
        editor_page=editor_page,
        editors={"job-1": _FakeEditor()},
        sync_tiles_from_editors=lambda: sync_calls.append("sync"),
    )

    assert controller.show_editor("job-1") is True
    assert controller.current_editor_id == "job-1"
    assert stack.indices == [1]

    controller.show_tiles()

    assert controller.current_editor_id is None
    assert stack.indices == [1, 0]
    assert sync_calls == ["sync"]


def test_navigation_controller_ignores_missing_or_hidden_editor() -> None:
    stack = _FakeStack()
    editor_page = _FakeEditorPage(show_result=False)
    controller = ExportJobsNavigationController(
        stack=stack,
        editor_page=editor_page,
        editors={"job-1": _FakeEditor()},
        sync_tiles_from_editors=lambda: None,
    )

    assert controller.show_editor("missing") is False
    assert controller.show_editor("job-1") is False
    assert controller.current_editor_id is None
    assert stack.indices == []


def test_navigation_controller_stops_all_editors_for_shutdown() -> None:
    first = _FakeEditor()
    second = _FakeEditor()
    controller = ExportJobsNavigationController(
        stack=_FakeStack(),
        editor_page=_FakeEditorPage(),
        editors={"job-1": first, "job-2": second},
        sync_tiles_from_editors=lambda: None,
    )

    controller.stop_all_editors()

    assert first.stop_scheduler_calls == 1
    assert first.stop_timers_calls == 1
    assert second.stop_scheduler_calls == 1
    assert second.stop_timers_calls == 1
