"""Tests for extracted ExportEditorController."""

from app.config import ExportJob, TriggerType
from app.core.scheduler import ScheduleMode
from app.ui.export_editor_controller import ExportEditorController


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs) -> None:
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class _FakeTimer:
    def __init__(self) -> None:
        self.timeout = _FakeSignal()
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


class _FakeScheduler:
    def __init__(self) -> None:
        self.trigger = _FakeSignal()
        self.start_calls = 0
        self.stop_calls = 0
        self.configure_calls: list[tuple[str, str]] = []

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def configure(self, mode: str, value: str) -> None:
        self.configure_calls.append((mode, value))


class _FakeDialog:
    def __init__(self, *, emit_payload: tuple[bool, int, str] | None = None) -> None:
        self.test_completed = _FakeSignal()
        self.exec_calls = 0
        self._emit_payload = emit_payload

    def exec(self) -> None:
        self.exec_calls += 1
        if self._emit_payload is not None:
            self.test_completed.emit(*self._emit_payload)


class _FakeShell:
    def __init__(self) -> None:
        self.changed = _FakeSignal()
        self.query_changed = _FakeSignal()
        self.schedule_changed = _FakeSignal()
        self.history_changed = _FakeSignal()
        self.test_requested = _FakeSignal()
        self.run_requested = _FakeSignal()
        self._job_name = ""
        self._sql = ""
        self._webhook = ""
        self._schedule_enabled = False
        self._schedule_mode = ScheduleMode.DAILY
        self._schedule_value = ""
        self._gas_sheet_name = ""
        self._history: list[dict] = []
        self.status_calls: list[tuple[str, str]] = []
        self.refresh_calls = 0

    def job_name(self) -> str:
        return self._job_name

    def set_job_name(self, name: str) -> None:
        self._job_name = name

    def sql_text(self) -> str:
        return self._sql

    def set_sql_text(self, sql: str) -> None:
        self._sql = sql

    def webhook_url(self) -> str:
        return self._webhook

    def set_webhook_url(self, url: str) -> None:
        self._webhook = url

    def schedule_enabled(self) -> bool:
        return self._schedule_enabled

    def schedule_mode(self) -> ScheduleMode:
        return self._schedule_mode

    def schedule_value(self) -> str:
        return self._schedule_value

    def set_schedule(self, enabled: bool, mode: ScheduleMode | str, value: str) -> None:
        self._schedule_enabled = enabled
        self._schedule_mode = mode
        self._schedule_value = value

    def gas_sheet_name(self) -> str:
        return self._gas_sheet_name


    def set_gas_options(
        self,
        *,
        sheet_name: str,
    ) -> None:
        self._gas_sheet_name = sheet_name

    def history(self) -> list[dict]:
        return list(self._history)

    def set_history(self, history: list[dict]) -> None:
        self._history = list(history)

    def latest_history_entry(self) -> dict | None:
        if not self._history:
            return None
        return self._history[0]

    def set_status(self, kind: str, text: str) -> None:
        self.status_calls.append((kind, text))

    def refresh_sql_syntax(self) -> None:
        self.refresh_calls += 1


def _make_controller(**overrides) -> ExportEditorController:
    return ExportEditorController(
        shell=overrides.get("shell", _FakeShell()),
        scheduler=overrides.get("scheduler", _FakeScheduler()),
        query_timer=overrides.get("query_timer", _FakeTimer()),
        syntax_timer=overrides.get("syntax_timer", _FakeTimer()),
        load_config=overrides.get("load_config", lambda: {"sql_instance": "srv"}),
        emit_changed=overrides.get("emit_changed", lambda: None),
        emit_history_changed=overrides.get("emit_history_changed", lambda: None),
        run_manual_export=overrides.get("run_manual_export", lambda: None),
        run_scheduled_export=overrides.get("run_scheduled_export", lambda: None),
        record_test_completed=overrides.get("record_test_completed", lambda **_: None),
        create_test_dialog=overrides.get(
            "create_test_dialog",
            lambda cfg, sql: _FakeDialog(),
        ),
    )


def test_export_editor_controller_loads_job_restores_status_and_starts_schedule_without_eager_sql_validation(
    monkeypatch,
) -> None:
    shell = _FakeShell()
    scheduler = _FakeScheduler()
    single_shot_calls: list[int] = []
    monkeypatch.setattr(
        "app.ui.export_editor_controller.QTimer.singleShot",
        lambda ms, callback: single_shot_calls.append(ms),
    )

    controller = _make_controller(
        shell=shell,
        scheduler=scheduler,
    )
    job = ExportJob(
        id="job-1",
        name="Nightly export",
        sql_query="SELECT 1",
        webhook_url="https://example.test/hook",
        gas_options={
            "sheet_name": "Exports",
        },
        schedule_enabled=True,
        schedule_mode="hourly",
        schedule_value="2",
        history=[
            {
                "ts": "2026-04-16 09:10:11",
                "trigger": TriggerType.MANUAL.value,
                "ok": True,
                "rows": 3,
                "err": "",
                "duration_us": 9_000,
            }
        ],
    )

    controller.load_job(job)

    assert shell.job_name() == "Nightly export"
    assert shell.sql_text() == "SELECT 1"
    assert shell.webhook_url() == "https://example.test/hook"
    assert shell.gas_sheet_name() == "Exports"
    assert shell.history()[0]["rows"] == 3
    assert shell.status_calls == [("ok", "✓ 3 строк · 09:10:11 · 9 мс")]
    assert shell.refresh_calls == 0
    assert single_shot_calls == []
    assert scheduler.stop_calls == 1
    assert scheduler.configure_calls == [(ScheduleMode.HOURLY, "2")]
    assert scheduler.start_calls == 1


def test_export_editor_controller_wires_query_schedule_history_and_run_signals() -> None:
    shell = _FakeShell()
    shell.set_schedule(True, ScheduleMode.DAILY, "08:30")
    scheduler = _FakeScheduler()
    query_timer = _FakeTimer()
    syntax_timer = _FakeTimer()
    manual_calls: list[str] = []
    scheduled_calls: list[str] = []
    changed_calls: list[str] = []
    history_calls: list[str] = []
    controller = _make_controller(
        shell=shell,
        scheduler=scheduler,
        query_timer=query_timer,
        syntax_timer=syntax_timer,
        emit_changed=lambda: changed_calls.append("changed"),
        emit_history_changed=lambda: history_calls.append("history"),
        run_manual_export=lambda: manual_calls.append("manual"),
        run_scheduled_export=lambda: scheduled_calls.append("scheduled"),
    )

    controller.wire()
    shell.query_changed.emit()
    shell.schedule_changed.emit()
    shell.history_changed.emit()
    shell.run_requested.emit()
    scheduler.trigger.emit()

    assert query_timer.start_calls == 1
    assert syntax_timer.start_calls == 1
    assert scheduler.stop_calls == 1
    assert scheduler.configure_calls == [(ScheduleMode.DAILY, "08:30")]
    assert scheduler.start_calls == 1
    assert changed_calls == ["changed", "changed"]
    assert history_calls == ["history"]
    assert manual_calls == ["manual"]
    assert scheduled_calls == ["scheduled"]


def test_export_editor_controller_opens_test_dialog_and_records_completion() -> None:
    shell = _FakeShell()
    shell.set_sql_text("SELECT 1")
    records: list[tuple[bool, int, str]] = []
    dialog = _FakeDialog(emit_payload=(True, 5, ""))
    dialog_inputs: list[tuple[dict, str]] = []
    controller = _make_controller(
        shell=shell,
        load_config=lambda: {"sql_instance": "srv", "sql_database": "db"},
        record_test_completed=lambda **kwargs: records.append(
            (kwargs["ok"], kwargs["rows"], kwargs["err"])
        ),
        create_test_dialog=lambda cfg, sql: dialog_inputs.append((cfg, sql)) or dialog,
    )

    controller.open_test_dialog()

    assert dialog_inputs == [({"sql_instance": "srv", "sql_database": "db"}, "SELECT 1")]
    assert dialog.exec_calls == 1
    assert records == [(True, 5, "")]


def test_export_editor_controller_stop_helpers_delegate_to_scheduler_and_timers() -> None:
    scheduler = _FakeScheduler()
    query_timer = _FakeTimer()
    syntax_timer = _FakeTimer()
    controller = _make_controller(
        scheduler=scheduler,
        query_timer=query_timer,
        syntax_timer=syntax_timer,
    )

    controller.stop_scheduler()
    controller.stop_timers()

    assert scheduler.stop_calls == 1
    assert query_timer.stop_calls == 1
    assert syntax_timer.stop_calls == 1
