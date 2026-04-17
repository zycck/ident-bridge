"""Tests for app.workers.export_worker.ExportWorker."""
import json
from unittest.mock import MagicMock

import pytest

from app.config import AppConfig, ExportJob, SyncResult
from app.workers.export_worker import ExportWorker, build_webhook_payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Suppress time.sleep inside the retry loop so tests run at full speed."""
    # The retry loop now lives in app.export.sinks.webhook after the
    # ExportSink refactor; the worker no longer imports time itself.
    monkeypatch.setattr("app.export.sinks.webhook.time.sleep", lambda *_: None)


@pytest.fixture
def base_cfg() -> AppConfig:
    # AppConfig is a TypedDict — use plain dict construction
    return AppConfig(
        sql_instance="localhost",
        sql_database="test",
        sql_user="",
        sql_password="",
        sql_trust_cert=True,
    )


@pytest.fixture
def simple_job() -> ExportJob:
    # ExportJob is a TypedDict — no webhook URL
    return ExportJob(
        id="t1",
        name="Test Export",
        sql_query="SELECT id FROM users",
        webhook_url="",
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],
    )


@pytest.fixture
def webhook_job() -> ExportJob:
    return ExportJob(
        id="t2",
        name="With Webhook",
        sql_query="SELECT id FROM users",
        webhook_url="https://example.com/hook",
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],
    )


# ---------------------------------------------------------------------------
# Helper: collect signal emissions synchronously
# ---------------------------------------------------------------------------

class _SignalCollector:
    def __init__(self):
        self.progress_emissions: list[tuple[int, str]] = []
        self.finished_emissions: list[SyncResult] = []
        self.error_emissions: list[str] = []

    def attach(self, worker: ExportWorker) -> None:
        worker.progress.connect(
            lambda step, msg: self.progress_emissions.append((step, msg))
        )
        worker.finished.connect(
            lambda result: self.finished_emissions.append(result)
        )
        worker.error.connect(
            lambda msg: self.error_emissions.append(msg)
        )


def _run_worker_sync(worker: ExportWorker) -> _SignalCollector:
    """Call worker.run() directly (single-threaded) and return collected signals."""
    collector = _SignalCollector()
    collector.attach(worker)
    worker.run()
    return collector


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

def test_full_pipeline_success(base_cfg, simple_job, mock_sql_client, qtbot):
    """Pipeline runs through all steps and emits finished(success=True)."""
    worker = ExportWorker(base_cfg, simple_job)
    c = _run_worker_sync(worker)

    assert len(c.progress_emissions) >= 1
    assert len(c.finished_emissions) == 1
    assert c.finished_emissions[0].success is True
    assert len(c.error_emissions) == 0


def test_finished_signal_carries_query_result_count(base_cfg, simple_job, mock_sql_client, qtbot):
    """SyncResult.rows_synced reflects the mocked query row count (2 rows)."""
    worker = ExportWorker(base_cfg, simple_job)
    c = _run_worker_sync(worker)
    # mock_query_result in conftest returns count=2
    assert c.finished_emissions[0].rows_synced == 2


def test_sql_query_is_passed_to_sql_client(base_cfg, simple_job, mock_sql_client, qtbot):
    """The job's SQL query is forwarded to the mock SqlClient."""
    worker = ExportWorker(base_cfg, simple_job)
    _run_worker_sync(worker)
    assert len(mock_sql_client.instances) >= 1
    last = mock_sql_client.instances[-1]
    assert "SELECT id FROM users" in last.queries


def test_sql_client_disconnected_after_run(base_cfg, simple_job, mock_sql_client, qtbot):
    """SqlClient.disconnect() is called in the finally block even on success."""
    worker = ExportWorker(base_cfg, simple_job)
    _run_worker_sync(worker)
    last = mock_sql_client.instances[-1]
    assert last.connected is False


def test_progress_step_sequence(base_cfg, simple_job, mock_sql_client, qtbot):
    """Progress steps are emitted in order: 0, 1, 2, 3."""
    worker = ExportWorker(base_cfg, simple_job)
    c = _run_worker_sync(worker)
    steps = [s for s, _ in c.progress_emissions]
    assert steps == [0, 1, 2, 3]


def test_finished_result_is_syncresult_instance(base_cfg, simple_job, mock_sql_client, qtbot):
    """finished signal payload is a SyncResult dataclass."""
    worker = ExportWorker(base_cfg, simple_job)
    c = _run_worker_sync(worker)
    assert isinstance(c.finished_emissions[0], SyncResult)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_db_connect_failure_emits_error_and_finished_with_failure(
    base_cfg, simple_job, monkeypatch, qtbot,
):
    """If SqlClient.connect() raises, both error and finished(success=False) fire."""
    class _FailingClient:
        instances: list = []

        def __init__(self, cfg):
            _FailingClient.instances.append(self)

        def connect(self):
            raise ConnectionError("DB unreachable")

        def disconnect(self):
            pass

        def query(self, sql):
            raise RuntimeError("never reached")

    _FailingClient.instances.clear()
    monkeypatch.setattr("app.workers.export_worker.SqlClient", _FailingClient)

    worker = ExportWorker(base_cfg, simple_job)
    c = _run_worker_sync(worker)

    # Worker must signal failure via error AND finished(success=False)
    assert len(c.error_emissions) > 0
    assert len(c.finished_emissions) == 1
    assert c.finished_emissions[0].success is False


def test_db_connect_failure_disconnect_still_called(
    base_cfg, simple_job, monkeypatch, qtbot,
):
    """SqlClient.disconnect() is called even when connect() raises (finally block)."""
    disconnect_calls = []

    class _FailingClient:
        def __init__(self, cfg): pass
        def connect(self): raise ConnectionError("down")
        def disconnect(self): disconnect_calls.append(True)
        def query(self, sql): pass

    monkeypatch.setattr("app.workers.export_worker.SqlClient", _FailingClient)

    worker = ExportWorker(base_cfg, simple_job)
    _run_worker_sync(worker)

    assert len(disconnect_calls) == 1


def test_query_failure_emits_error_and_finished_failure(
    base_cfg, simple_job, monkeypatch, qtbot,
):
    """If SqlClient.query() raises, error and finished(success=False) are emitted."""
    class _QueryFailClient:
        instances: list = []

        def __init__(self, cfg):
            _QueryFailClient.instances.clear()
            _QueryFailClient.instances.append(self)

        def connect(self): pass
        def disconnect(self): pass
        def query(self, sql): raise RuntimeError("syntax error near SELECT")

    monkeypatch.setattr("app.workers.export_worker.SqlClient", _QueryFailClient)

    worker = ExportWorker(base_cfg, simple_job)
    c = _run_worker_sync(worker)

    assert len(c.error_emissions) > 0
    assert c.finished_emissions[0].success is False


def test_empty_sql_query_emits_error(base_cfg, mock_sql_client, qtbot):
    """An ExportJob with empty sql_query triggers an error (ValueError)."""
    job = ExportJob(
        id="empty",
        name="Empty SQL",
        sql_query="",        # intentionally blank
        webhook_url="",
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],
    )
    worker = ExportWorker(base_cfg, job)
    c = _run_worker_sync(worker)

    assert len(c.error_emissions) > 0
    assert c.finished_emissions[0].success is False


# ---------------------------------------------------------------------------
# Webhook handling
# ---------------------------------------------------------------------------

def test_webhook_skipped_when_url_empty(base_cfg, simple_job, mock_sql_client, monkeypatch, qtbot):
    """No webhook URL → urllib.request.urlopen is never called."""
    urlopen_calls: list = []

    class _FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def _spy(req, *args, **kwargs):
        urlopen_calls.append(req)
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", _spy)

    worker = ExportWorker(base_cfg, simple_job)
    _run_worker_sync(worker)

    assert len(urlopen_calls) == 0


def test_webhook_called_when_url_set(base_cfg, webhook_job, mock_sql_client, monkeypatch, qtbot):
    """Webhook URL is set → urllib.request.urlopen is called exactly once."""
    urlopen_calls: list = []

    class _FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def _spy(req, *args, **kwargs):
        urlopen_calls.append(req)
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", _spy)

    worker = ExportWorker(base_cfg, webhook_job)
    _run_worker_sync(worker)

    assert len(urlopen_calls) == 1


def test_webhook_request_method_is_post(base_cfg, webhook_job, mock_sql_client, monkeypatch, qtbot):
    """The urllib Request sent to urlopen uses POST method."""
    import urllib.request as _urllibmod

    captured: list = []

    class _FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def _spy(req, *args, **kwargs):
        captured.append(req)
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", _spy)

    worker = ExportWorker(base_cfg, webhook_job)
    _run_worker_sync(worker)

    assert len(captured) == 1
    req = captured[0]
    assert isinstance(req, _urllibmod.Request)
    assert req.method == "POST"


def test_webhook_url_in_request(base_cfg, webhook_job, mock_sql_client, monkeypatch, qtbot):
    """The urllib Request targets the job's webhook_url."""
    captured: list = []

    class _FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def _spy(req, *args, **kwargs):
        captured.append(req)
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", _spy)

    worker = ExportWorker(base_cfg, webhook_job)
    _run_worker_sync(worker)

    assert captured[0].full_url == "https://example.com/hook"


def test_build_webhook_payload_serializes_rows_without_shape_change(mock_query_result) -> None:
    payload = build_webhook_payload("Demo Job", mock_query_result)
    decoded = json.loads(payload.decode("utf-8"))

    assert decoded == {
        "job": "Demo Job",
        "rows": 2,
        "columns": ["id", "name"],
        "data": [[1, "alice"], [2, "bob"]],
    }


def test_webhook_failure_emits_error_and_finished_failure(
    base_cfg, webhook_job, mock_sql_client, monkeypatch, qtbot,
):
    """Webhook POST raises OSError → error and finished(success=False) emitted."""
    def _failing_urlopen(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", _failing_urlopen)

    worker = ExportWorker(base_cfg, webhook_job)
    c = _run_worker_sync(worker)

    assert len(c.error_emissions) > 0
    assert c.finished_emissions[0].success is False


def test_finished_always_emitted_on_webhook_failure(
    base_cfg, webhook_job, mock_sql_client, monkeypatch, qtbot,
):
    """finished signal is emitted even when webhook raises (exception re-raised)."""
    def _failing_urlopen(*args, **kwargs):
        raise OSError("timeout")

    monkeypatch.setattr("urllib.request.urlopen", _failing_urlopen)

    worker = ExportWorker(base_cfg, webhook_job)
    c = _run_worker_sync(worker)

    assert len(c.finished_emissions) == 1
