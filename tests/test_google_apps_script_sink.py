"""Tests for app.export.sinks.google_apps_script."""

from __future__ import annotations

import io
import json
import random
import urllib.error

import pytest

from app.config import QueryResult
from app.export.protocol import ExportSink
from app.export.sinks.google_apps_script import (
    GasAck,
    GoogleAppsScriptDeliveryError,
    GoogleAppsScriptSink,
    build_chunk_records,
    build_gas_chunk_payload,
    parse_gas_ack,
    plan_gas_chunks,
)

FIXED_EXPORT_DATE = "2026-04-20"
REAL_PING_BACKEND = GoogleAppsScriptSink._ping_backend


def _qr(columns=("id",), rows=((1,),), duration=1) -> QueryResult:
    return QueryResult(
        columns=list(columns),
        rows=list(rows),
        count=len(rows),
        duration_ms=duration,
    )


def _seeded_qr(seed: int, row_count: int) -> QueryResult:
    rng = random.Random(seed)
    rows = []
    for idx in range(row_count):
        left = "".join(rng.choice("abcдежз") for _ in range(rng.randint(1, 6)))
        right = "".join(rng.choice("01xyzЖ") for _ in range(rng.randint(0, 8)))
        rows.append((idx, f"{left}-{idx}", right))
    return _qr(columns=("id", "label", "payload"), rows=tuple(rows), duration=seed)


class _FakeResp:
    def __init__(self, body: object, status: int = 200) -> None:
        self.status = status
        if isinstance(body, bytes):
            self._body = body
        elif isinstance(body, str):
            self._body = body.encode("utf-8")
        else:
            self._body = json.dumps(body, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_google_apps_script_sink_is_a_protocol_sink():
    sink = GoogleAppsScriptSink("https://script.google.com/macros/s/abc/exec")
    assert isinstance(sink, ExportSink)
    assert sink.name == "google_apps_script"


def test_google_apps_script_sink_prefers_dev_url_env_override(monkeypatch):
    monkeypatch.setenv(
        "IDENTBRIDGE_GAS_DEV_URL",
        "https://script.google.com/macros/s/dev-override/exec",
    )

    sink = GoogleAppsScriptSink("https://script.google.com/macros/s/prod/exec")

    assert sink._url == "https://script.google.com/macros/s/dev-override/exec"


def test_build_chunk_records_maps_rows_to_objects():
    records = build_chunk_records(["id", "name"], [(1, "alice"), (2, "bob")])
    assert records == [
        {"id": 1, "name": "alice"},
        {"id": 2, "name": "bob"},
    ]


def test_plan_gas_chunks_keeps_single_chunk_under_limits():
    chunks = plan_gas_chunks(
        "Job",
        _qr(columns=("id", "name"), rows=((1, "alice"), (2, "bob"))),
        run_id="run-1",
        max_rows_per_chunk=10_000,
        max_payload_bytes=5 * 1024 * 1024,
        export_date=FIXED_EXPORT_DATE,
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 1
    assert chunks[0].total_chunks == 1
    assert chunks[0].chunk_rows == 2
    assert chunks[0].columns == ["id", "name"]
    assert chunks[0].records == [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]


def test_plan_gas_chunks_splits_by_row_limit():
    rows = [(idx,) for idx in range(10_001)]
    chunks = plan_gas_chunks(
        "Rows",
        _qr(rows=rows),
        run_id="run-2",
        max_rows_per_chunk=10_000,
        max_payload_bytes=50 * 1024 * 1024,
        export_date=FIXED_EXPORT_DATE,
    )

    assert len(chunks) == 2
    assert [chunk.chunk_rows for chunk in chunks] == [10_000, 1]
    assert all(chunk.total_chunks == 2 for chunk in chunks)


def test_plan_gas_chunks_splits_by_payload_bytes():
    rows = [("ж" * 400,), ("ж" * 400,), ("ж" * 400,)]
    chunks = plan_gas_chunks(
        "Bytes",
        _qr(columns=("payload",), rows=rows),
        run_id="run-3",
        max_rows_per_chunk=10_000,
        max_payload_bytes=2_000,
        export_date=FIXED_EXPORT_DATE,
    )

    assert len(chunks) == 2
    assert sum(chunk.chunk_rows for chunk in chunks) == 3
    assert all(chunk.chunk_bytes <= 2_000 for chunk in chunks)


def test_plan_gas_chunks_builds_one_empty_chunk_for_empty_results():
    chunks = plan_gas_chunks(
        "Empty",
        _qr(rows=()),
        run_id="run-4",
        max_rows_per_chunk=10_000,
        max_payload_bytes=5 * 1024 * 1024,
        export_date=FIXED_EXPORT_DATE,
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_rows == 0
    assert chunks[0].records == []


def test_build_gas_chunk_payload_shape_is_stable():
    chunk = plan_gas_chunks(
        "Stable",
        _qr(columns=("id", "name"), rows=((1, "alice"),)),
        run_id="run-5",
        max_rows_per_chunk=10_000,
        max_payload_bytes=5 * 1024 * 1024,
        export_date=FIXED_EXPORT_DATE,
    )[0]

    payload = json.loads(
        build_gas_chunk_payload(
            "Stable",
            chunk,
            gas_options={"sheet_name": "Exports"},
            export_date=FIXED_EXPORT_DATE,
        ).decode("utf-8")
    )

    assert payload == {
        "protocol_version": "gas-sheet.v2",
        "job_name": "Stable",
        "sheet_name": "Exports",
        "export_date": FIXED_EXPORT_DATE,
        "run_id": "run-5",
        "chunk_index": 1,
        "total_chunks": 1,
        "total_rows": 1,
        "chunk_rows": 1,
        "columns": ["id", "name"],
        "records": [{"id": 1, "name": "alice"}],
        "checksum": chunk.checksum,
    }


def test_build_gas_chunk_payload_uses_job_name_as_sheet_name_when_not_configured():
    chunk = plan_gas_chunks(
        "Fallback sheet",
        _qr(rows=((1,),)),
        run_id="run-5b",
        max_rows_per_chunk=10_000,
        max_payload_bytes=5 * 1024 * 1024,
        export_date=FIXED_EXPORT_DATE,
    )[0]

    payload = json.loads(
        build_gas_chunk_payload(
            "Fallback sheet",
            chunk,
            export_date=FIXED_EXPORT_DATE,
        ).decode("utf-8")
    )

    assert payload["sheet_name"] == "Fallback sheet"


@pytest.mark.parametrize("row_count", [9, 10, 99, 100])
def test_plan_gas_chunks_keeps_payload_size_exact_when_total_chunks_cross_digit_boundaries(
    row_count: int,
) -> None:
    result = _seeded_qr(seed=1000 + row_count, row_count=row_count)
    chunks = plan_gas_chunks(
        "Digit total chunks",
        result,
        run_id=f"run-total-{row_count}",
        max_rows_per_chunk=1,
        max_payload_bytes=10_000_000,
        export_date=FIXED_EXPORT_DATE,
    )

    assert len(chunks) == row_count
    assert all(chunk.total_chunks == row_count for chunk in chunks)

    for chunk in chunks:
        planned_bytes = chunk.chunk_bytes
        payload = build_gas_chunk_payload(
            "Digit total chunks",
            chunk,
            export_date=FIXED_EXPORT_DATE,
        )
        assert len(payload) == planned_bytes
        assert chunk.chunk_bytes == planned_bytes


@pytest.mark.parametrize("row_count", [9, 10, 99, 100])
def test_plan_gas_chunks_keeps_payload_size_exact_when_chunk_rows_cross_digit_boundaries(
    row_count: int,
) -> None:
    result = _seeded_qr(seed=2000 + row_count, row_count=row_count)
    chunks = plan_gas_chunks(
        "Digit chunk rows",
        result,
        run_id=f"run-rows-{row_count}",
        max_rows_per_chunk=row_count + 5,
        max_payload_bytes=10_000_000,
        export_date=FIXED_EXPORT_DATE,
    )

    assert len(chunks) == 1

    chunk = chunks[0]
    planned_bytes = chunk.chunk_bytes
    payload = build_gas_chunk_payload(
        "Digit chunk rows",
        chunk,
        export_date=FIXED_EXPORT_DATE,
    )
    assert len(payload) == planned_bytes
    assert chunk.chunk_bytes == planned_bytes
    assert chunk.chunk_rows == row_count


@pytest.mark.parametrize(
    ("seed", "row_count", "max_rows_per_chunk"),
    [
        (3, 37, 4),
        (17, 64, 5),
        (29, 123, 6),
    ],
)
def test_plan_gas_chunks_is_deterministic_for_seeded_random_scenarios(
    seed: int,
    row_count: int,
    max_rows_per_chunk: int,
) -> None:
    result = _seeded_qr(seed=seed, row_count=row_count)
    plan_kwargs = {
        "run_id": f"seeded-{seed}",
        "max_rows_per_chunk": max_rows_per_chunk,
        "max_payload_bytes": 10_000_000,
        "export_date": FIXED_EXPORT_DATE,
    }

    chunks_a = plan_gas_chunks("Seeded random", result, **plan_kwargs)
    chunks_b = plan_gas_chunks("Seeded random", result, **plan_kwargs)

    summary_a = [
        (chunk.chunk_index, chunk.total_chunks, chunk.chunk_rows, chunk.chunk_bytes, chunk.checksum)
        for chunk in chunks_a
    ]
    summary_b = [
        (chunk.chunk_index, chunk.total_chunks, chunk.chunk_rows, chunk.chunk_bytes, chunk.checksum)
        for chunk in chunks_b
    ]
    assert summary_a == summary_b

    for chunk in chunks_a:
        planned_bytes = chunk.chunk_bytes
        payload = build_gas_chunk_payload(
            "Seeded random",
            chunk,
            export_date=FIXED_EXPORT_DATE,
        )
        assert len(payload) == planned_bytes
        assert chunk.chunk_bytes == planned_bytes


def test_parse_gas_ack_accepts_success_and_ignores_extra_fields():
    ack = parse_gas_ack(
        json.dumps(
            {
                "ok": True,
                "status": "accepted",
                "rows_received": 2,
                "rows_written": 2,
                "retryable": False,
                "message": "ok",
                "extra": "ignored",
            }
        ).encode("utf-8")
    )

    assert isinstance(ack, GasAck)
    assert ack.ok is True
    assert ack.status == "accepted"
    assert ack.rows_written == 2


def test_parse_gas_ack_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_gas_ack(b"not-json")


def test_parse_gas_ack_rejects_success_ack_without_status():
    with pytest.raises(ValueError):
        parse_gas_ack(
            json.dumps(
                {
                    "ok": True,
                    "retryable": False,
                    "message": "ok",
                }
            ).encode("utf-8")
        )


def test_parse_gas_ack_accepts_minimal_failure_ack():
    ack = parse_gas_ack(
        json.dumps(
            {
                "ok": False,
                "error_code": "UNAUTHORIZED",
                "retryable": False,
                "message": "Invalid auth token",
                "details": {"field": "auth_token"},
            }
        ).encode("utf-8")
    )

    assert ack.ok is False
    assert ack.error_code == "UNAUTHORIZED"
    assert ack.message == "Invalid auth token"
    assert ack.details == {"field": "auth_token"}

@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("app.export.sinks.google_apps_script.time.sleep", lambda *_: None)
    monkeypatch.setattr("app.export.sinks.google_apps_script.GoogleAppsScriptSink._ping_backend", lambda self: None)


def test_push_reports_progress_for_each_chunk(monkeypatch):
    attempts = []

    def _urlopen(req, **kwargs):
        attempts.append(req)
        body = json.loads(req.data.decode("utf-8"))
        row_count = len(body["records"])
        return _FakeResp(
            {
                "ok": True,
                "status": "accepted",
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "rows_received": row_count,
                "rows_written": row_count,
                "retryable": False,
                "message": "ok",
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    sink = GoogleAppsScriptSink(
        "https://script.google.com/macros/s/abc/exec",
        max_rows_per_chunk=2,
        max_payload_bytes=5 * 1024 * 1024,
    )
    progress = []
    sink.push("Progress", _qr(rows=((1,), (2,), (3,))), on_progress=progress.append)

    assert len(attempts) == 2
    assert progress == ["Отправка данных... 1/2", "Отправка данных... 2/2"]


def test_push_does_not_send_legacy_auth_token_field(monkeypatch):
    seen = {}

    def _urlopen(req, **kwargs):
        seen["headers"] = dict(req.headers)
        seen["body"] = json.loads(req.data.decode("utf-8"))
        row_count = len(seen["body"]["records"])
        return _FakeResp(
            {
                "ok": True,
                "status": "accepted",
                "run_id": seen["body"]["run_id"],
                "chunk_index": seen["body"]["chunk_index"],
                "rows_received": row_count,
                "rows_written": row_count,
                "retryable": False,
                "message": "ok",
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    sink = GoogleAppsScriptSink("https://script.google.com/macros/s/abc/exec")
    sink.push("Body auth", _qr())

    assert "auth_token" not in seen["body"]
    assert "X-iDentBridge-Token" not in seen["headers"]


def test_push_treats_duplicate_ack_as_success(monkeypatch):
    def _urlopen(req, **kwargs):
        body = json.loads(req.data.decode("utf-8"))
        return _FakeResp(
            {
                "ok": True,
                "status": "duplicate",
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "rows_received": len(body["records"]),
                "rows_written": 0,
                "retryable": False,
                "message": "already applied",
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)
    GoogleAppsScriptSink("https://script.google.com/macros/s/abc/exec").push("Dup", _qr())


def test_push_retries_on_retryable_ack(monkeypatch):
    attempts = {"count": 0}

    def _urlopen(req, **kwargs):
        attempts["count"] += 1
        body = json.loads(req.data.decode("utf-8"))
        row_count = len(body["records"])
        if attempts["count"] == 1:
            return _FakeResp(
                {
                    "ok": False,
                    "status": "retry",
                    "error_code": "LOCK_TIMEOUT",
                    "retryable": True,
                    "run_id": body["run_id"],
                    "chunk_index": body["chunk_index"],
                    "message": "lock busy",
                    "details": {"wait_ms": 1000},
                }
            )
        return _FakeResp(
            {
                "ok": True,
                "status": "accepted",
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "rows_received": row_count,
                "rows_written": row_count,
                "retryable": False,
                "message": "ok",
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    GoogleAppsScriptSink(
        "https://script.google.com/macros/s/abc/exec",
        retries=2,
    ).push("Retry", _qr())
    assert attempts["count"] == 2


def test_push_retries_on_malformed_ack_then_succeeds(monkeypatch):
    attempts = {"count": 0}

    def _urlopen(req, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return _FakeResp("oops")
        body = json.loads(req.data.decode("utf-8"))
        row_count = len(body["records"])
        return _FakeResp(
            {
                "ok": True,
                "status": "accepted",
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "rows_received": row_count,
                "rows_written": row_count,
                "retryable": False,
                "message": "ok",
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    GoogleAppsScriptSink(
        "https://script.google.com/macros/s/abc/exec",
        retries=2,
    ).push("Malformed", _qr())
    assert attempts["count"] == 2


def test_push_raises_structured_error_on_partial_delivery(monkeypatch):
    attempts = {"count": 0}

    def _urlopen(req, **kwargs):
        attempts["count"] += 1
        body = json.loads(req.data.decode("utf-8"))
        row_count = len(body["records"])
        if body["chunk_index"] == 1:
            return _FakeResp(
                {
                    "ok": True,
                    "status": "accepted",
                    "run_id": body["run_id"],
                    "chunk_index": body["chunk_index"],
                    "rows_received": row_count,
                    "rows_written": row_count,
                    "retryable": False,
                    "message": "ok",
                }
            )
        return _FakeResp(
            {
                "ok": False,
                "status": "rejected",
                "error_code": "SCHEMA_MISMATCH_MISSING_COLUMNS",
                "retryable": False,
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "message": "missing columns",
                "details": {"missing_columns": ["legacy"]},
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    sink = GoogleAppsScriptSink(
        "https://script.google.com/macros/s/abc/exec",
        max_rows_per_chunk=2,
        max_payload_bytes=5 * 1024 * 1024,
    )

    with pytest.raises(GoogleAppsScriptDeliveryError) as exc_info:
        sink.push("Partial", _qr(rows=((1,), (2,), (3,))))

    exc = exc_info.value
    assert exc.delivered_chunks == 1
    assert exc.failed_chunk_index == 2
    assert exc.delivered_rows == 2
    assert exc.run_id
    assert "missing columns" not in exc.user_message
    assert "run_id" not in exc.debug_context


def test_push_surfaces_early_auth_failure_as_actionable_message(monkeypatch):
    monkeypatch.setattr(
        "app.export.sinks.google_apps_script.GoogleAppsScriptSink._ping_backend",
        REAL_PING_BACKEND,
    )

    def _urlopen(req, **kwargs):
        if req.get_method() == "GET":
            return _FakeResp(
                {
                    "ok": False,
                    "error_code": "UNAUTHORIZED",
                    "retryable": False,
                    "message": "Invalid auth token",
                    "details": {"field": "auth_token"},
                }
            )
        return _FakeResp(
            {
                "ok": False,
                "error_code": "UNAUTHORIZED",
                "retryable": False,
                "message": "Invalid auth token",
                "details": {"field": "auth_token"},
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    sink = GoogleAppsScriptSink(
        "https://script.google.com/macros/s/abc/exec",
        retries=1,
    )

    with pytest.raises(GoogleAppsScriptDeliveryError) as exc_info:
        sink.push("Auth failure", _qr())

    exc = exc_info.value
    assert "Invalid auth token" not in exc.user_message
    assert "UNAUTHORIZED" not in exc.user_message
    assert exc.debug_context["cause_type"] == "GasAckError"
    assert exc.debug_context["ack_message"] == "Invalid auth token"
    assert exc.debug_context["error_code"] == "UNAUTHORIZED"

def test_push_includes_http_status_and_body_preview_on_http_error(monkeypatch):
    body = b"Internal Server Error: backend exploded"

    def _urlopen(req, **kwargs):
        raise urllib.error.HTTPError(
            req.full_url,
            500,
            "Internal Server Error",
            hdrs=None,
            fp=io.BytesIO(body),
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    sink = GoogleAppsScriptSink("https://script.google.com/macros/s/abc/exec")

    with pytest.raises(GoogleAppsScriptDeliveryError) as exc_info:
        sink.push("HTTP failure", _qr())

    exc = exc_info.value
    assert "HTTP 500" in exc.debug_context["error"]
    assert "Internal Server Error" in exc.debug_context["error"]
    assert exc.debug_context["http_status"] == 500
    assert exc.debug_context["http_body_preview"] == "Internal Server Error: backend exploded"
    assert exc.debug_context["cause_type"] == "HTTPError"


def test_push_preserves_retryable_ack_details_in_debug_context(monkeypatch):
    def _urlopen(req, **kwargs):
        body = json.loads(req.data.decode("utf-8"))
        return _FakeResp(
            {
                "ok": False,
                "status": "retry",
                "error_code": "INTERNAL_WRITE_ERROR",
                "retryable": True,
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "message": "Unexpected server error",
                "details": {
                    "internal_message": "Sheets is not defined",
                },
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    sink = GoogleAppsScriptSink(
        "https://script.google.com/macros/s/abc/exec",
        retries=1,
    )

    with pytest.raises(GoogleAppsScriptDeliveryError) as exc_info:
        sink.push("Retryable ack", _qr())

    exc = exc_info.value
    assert exc.user_message == "Не удалось отправить данные в Google Таблицы"
    assert exc.debug_context["cause_type"] == "GasAckError"
    assert exc.debug_context["error"] == "Unexpected server error"
    assert exc.debug_context["ack_message"] == "Unexpected server error"
    assert exc.debug_context["error_code"] == "INTERNAL_WRITE_ERROR"
    assert exc.debug_context["ack_details"] == {
        "internal_message": "Sheets is not defined",
    }


def test_push_stays_user_neutral_for_generic_internal_error(monkeypatch):
    def _urlopen(req, **kwargs):
        body = json.loads(req.data.decode("utf-8"))
        return _FakeResp(
            {
                "ok": False,
                "status": "retry",
                "error_code": "INTERNAL_WRITE_ERROR",
                "retryable": True,
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "message": "Unexpected server error",
                "details": {},
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    sink = GoogleAppsScriptSink(
        "https://script.google.com/macros/s/abc/exec",
        retries=1,
    )

    with pytest.raises(GoogleAppsScriptDeliveryError) as exc_info:
        sink.push("Generic internal", _qr())

    exc = exc_info.value
    assert exc.user_message == "Не удалось отправить данные в Google Таблицы"
    assert "Unexpected server error" not in exc.user_message
    assert exc.debug_context["cause_type"] == "GasAckError"
