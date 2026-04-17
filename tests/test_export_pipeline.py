"""Tests for app.export.pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.config import AppConfig, ExportJob, QueryResult, SyncResult
from app.export.pipeline import ExportPipeline, build_pipeline_for_job
from app.export.protocol import ExportSink


# --- fakes ---------------------------------------------------------------


class _FakeDb:
    def __init__(self, result: QueryResult, *, fail_on: str | None = None) -> None:
        self._result = result
        self._fail_on = fail_on
        self.connected = False
        self.disconnect_calls = 0
        self.queries: list[str] = []

    def connect(self) -> None:
        if self._fail_on == "connect":
            raise ConnectionError("boom")
        self.connected = True

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.connected = False

    def query(self, sql: str) -> QueryResult:
        self.queries.append(sql)
        if self._fail_on == "query":
            raise RuntimeError("bad sql")
        return self._result


@dataclass
class _CountingSink:
    name: str = "counting"
    pushes: list[tuple[str, QueryResult]] = None  # type: ignore

    def __post_init__(self) -> None:
        self.pushes = []

    def push(self, job_name: str, result: QueryResult) -> None:
        self.pushes.append((job_name, result))


def _job(*, webhook: str = "", sql: str = "SELECT 1") -> ExportJob:
    return ExportJob(
        id="j",
        name="Test Job",
        sql_query=sql,
        webhook_url=webhook,
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],
    )


def _qr(count: int = 2) -> QueryResult:
    return QueryResult(columns=["a"], rows=[(i,) for i in range(count)], count=count, duration_ms=1)


# --- happy path ----------------------------------------------------------


def test_pipeline_runs_connect_query_push():
    db = _FakeDb(_qr())
    sink = _CountingSink()
    p = ExportPipeline(db=db, sink=sink)

    result = p.run(_job())

    assert isinstance(result, SyncResult)
    assert result.success is True
    assert result.rows_synced == 2
    assert db.queries == ["SELECT 1"]
    assert len(sink.pushes) == 1
    assert sink.pushes[0][0] == "Test Job"
    assert db.disconnect_calls == 1


def test_pipeline_without_sink_still_succeeds():
    db = _FakeDb(_qr())
    p = ExportPipeline(db=db, sink=None)
    result = p.run(_job())
    assert result.success is True
    assert db.disconnect_calls == 1


def test_progress_callback_receives_all_four_steps():
    db = _FakeDb(_qr())
    events: list[tuple[int, str]] = []
    p = ExportPipeline(db=db, sink=None)
    p.run(_job(), progress=lambda s, m: events.append((s, m)))
    assert [s for s, _ in events] == [0, 1, 2, 3]


# --- error paths ---------------------------------------------------------


def test_empty_sql_raises_before_connect():
    db = _FakeDb(_qr())
    p = ExportPipeline(db=db, sink=None)
    with pytest.raises(ValueError):
        p.run(_job(sql=""))
    # connect shouldn't have been called
    assert db.connected is False
    assert db.disconnect_calls == 0


def test_connect_failure_still_disconnects():
    db = _FakeDb(_qr(), fail_on="connect")
    p = ExportPipeline(db=db, sink=None)
    with pytest.raises(ConnectionError):
        p.run(_job())
    assert db.disconnect_calls == 1


def test_query_failure_still_disconnects():
    db = _FakeDb(_qr(), fail_on="query")
    p = ExportPipeline(db=db, sink=None)
    with pytest.raises(RuntimeError):
        p.run(_job())
    assert db.disconnect_calls == 1


def test_sink_failure_propagates_and_disconnects():
    class _BadSink:
        name = "bad"

        def push(self, job_name, result):
            raise RuntimeError("network down")

    db = _FakeDb(_qr())
    p = ExportPipeline(db=db, sink=_BadSink())
    with pytest.raises(RuntimeError):
        p.run(_job(webhook="https://example.com/x"))
    assert db.disconnect_calls == 1


# --- factory -------------------------------------------------------------


def test_factory_picks_webhook_sink_when_url_set():
    cfg: AppConfig = AppConfig()
    seen: list[Any] = []

    class _Spy:
        def __init__(self, cfg):
            seen.append(cfg)

    p = build_pipeline_for_job(cfg, _job(webhook="https://example.com/hook"), sql_client_cls=_Spy)
    assert p.sink is not None
    assert isinstance(p.sink, ExportSink)
    assert p.sink.name == "webhook"


def test_factory_no_sink_when_url_empty():
    class _Spy:
        def __init__(self, cfg): pass

    p = build_pipeline_for_job(AppConfig(), _job(webhook=""), sql_client_cls=_Spy)
    assert p.sink is None


def test_factory_uses_provided_sql_client_class():
    seen: list[AppConfig] = []

    class _Spy:
        def __init__(self, cfg):
            seen.append(cfg)

    cfg = AppConfig(sql_instance="xyz")
    p = build_pipeline_for_job(cfg, _job(), sql_client_cls=_Spy)
    assert len(seen) == 1
    assert seen[0] is cfg
    assert isinstance(p.db, _Spy)
