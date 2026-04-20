"""Tests for extracted ExportJobEditor bridge/services layer."""

from PySide6.QtCore import QObject

from app.config import ExportHistoryEntry
from app.core.scheduler import ScheduleMode
from app.ui.export_job_editor_bridge import ExportJobEditorBridge


class _FakeShell(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._history: list[ExportHistoryEntry] = []
        self.history_entries: list[ExportHistoryEntry] = []

    def job_name(self) -> str:
        return "Nightly"

    def sql_text(self) -> str:
        return "SELECT 1"

    def webhook_url(self) -> str:
        return "https://example.test/hook"

    def gas_sheet_name(self) -> str:
        return "Exports"

    def schedule_enabled(self) -> bool:
        return True

    def schedule_mode(self) -> ScheduleMode:
        return ScheduleMode.HOURLY

    def schedule_value(self) -> str:
        return "4"

    def history(self) -> list[ExportHistoryEntry]:
        return list(self._history)

    def prepend_history_entry(self, entry: ExportHistoryEntry) -> None:
        self.history_entries.append(entry)


class _FakeWorker(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.progress = _FakeSignal()


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks: list = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeDialog:
    def __init__(self, cfg, *, initial_sql: str, auto_run: bool, parent=None) -> None:
        self.cfg = cfg
        self.initial_sql = initial_sql
        self.auto_run = auto_run
        self.parent = parent


def test_export_job_editor_bridge_builds_job_payload_and_prepends_history() -> None:
    shell = _FakeShell()
    bridge = ExportJobEditorBridge(
        owner=QObject(),
        shell=shell,
        job_id="job-1",
    )
    entry: ExportHistoryEntry = {"ts": "2026-04-17 12:00:00", "ok": True, "rows": 2}

    job = bridge.build_job()
    bridge.add_history_entry(entry)

    assert job["id"] == "job-1"
    assert job["name"] == "Nightly"
    assert job["sql_query"] == "SELECT 1"
    assert job["webhook_url"] == "https://example.test/hook"
    assert job["gas_options"] == {"sheet_name": "Exports"}
    assert job["schedule_enabled"] is True
    assert job["schedule_mode"] == "hourly"
    assert job["schedule_value"] == "4"
    assert shell.history_entries == [entry]


def test_export_job_editor_bridge_starts_worker_with_progress_wired() -> None:
    shell = _FakeShell()
    calls = []
    bridge = ExportJobEditorBridge(
        owner=QObject(),
        shell=shell,
        job_id="job-1",
        run_worker_fn=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    worker = _FakeWorker()
    on_progress = lambda *_args: None

    bridge.start_worker(worker, lambda *_: None, lambda *_: None, on_progress)

    assert worker.progress.callbacks == [on_progress]
    assert len(calls) == 1
    assert calls[0][1]["pin_attr"] == "_worker"


def test_export_job_editor_bridge_creates_test_dialog_with_auto_run() -> None:
    shell = _FakeShell()
    owner = QObject()
    bridge = ExportJobEditorBridge(
        owner=owner,
        shell=shell,
        job_id="job-1",
        test_dialog_factory=_FakeDialog,
    )

    dialog = bridge.create_test_dialog({"sql_instance": "srv"}, "SELECT 1")

    assert dialog.cfg == {"sql_instance": "srv"}
    assert dialog.initial_sql == "SELECT 1"
    assert dialog.auto_run is True
    assert dialog.parent is owner