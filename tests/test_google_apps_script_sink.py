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
        left = "".join(rng.choice("abcдеёжз") for _ in range(rng.randint(1, 6)))
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
    )[0]

    payload = json.loads(build_gas_chunk_payload("Stable", chunk).decode("utf-8"))
    assert payload == {
        "protocol_version": "gas-sheet.v1",
        "job_name": "Stable",
        "run_id": "run-5",
        "chunk_index": 1,
        "total_chunks": 1,
        "total_rows": 1,
        "chunk_rows": 1,
        "chunk_bytes": chunk.chunk_bytes,
        "schema": {
            "mode": "append_only_v1",
            "columns": ["id", "name"],
            "checksum": chunk.checksum,
        },
        "records": [{"id": 1, "name": "alice"}],
    }


def test_build_gas_chunk_payload_includes_target_and_dedupe_blocks_when_configured():
    chunk = plan_gas_chunks(
        "Configured",
        _qr(columns=("id", "updated_at"), rows=((1, "2026-04-18"),)),
        run_id="run-5b",
        max_rows_per_chunk=10_000,
        max_payload_bytes=5 * 1024 * 1024,
    )[0]

    payload = json.loads(
        build_gas_chunk_payload(
            "Configured",
            chunk,
            gas_options={
                "sheet_name": "Exports",
                "header_row": 2,
                "dedupe_key_columns": ["id", "updated_at"],
            },
        ).decode("utf-8")
    )

    assert payload["target"] == {
        "sheet_name": "Exports",
        "header_row": 2,
    }
    assert payload["dedupe"] == {
        "key_columns": ["id", "updated_at"],
    }
    assert "gas_options" not in payload


def test_build_gas_chunk_payload_includes_auth_token_in_body():
    chunk = plan_gas_chunks(
        "Authenticated",
        _qr(columns=("id",), rows=((1,),)),
        run_id="run-auth",
        max_rows_per_chunk=10_000,
        max_payload_bytes=5 * 1024 * 1024,
    )[0]

    payload = json.loads(
        build_gas_chunk_payload(
            "Authenticated",
            chunk,
            gas_options={
                "auth_token": "secret-token",
            },
        ).decode("utf-8")
    )

    assert payload["auth_token"] == "secret-token"


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
    )

    assert len(chunks) == row_count
    assert all(chunk.total_chunks == row_count for chunk in chunks)

    for chunk in chunks:
        planned_bytes = chunk.chunk_bytes
        payload = build_gas_chunk_payload("Digit total chunks", chunk)
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
    )

    assert len(chunks) == 1

    chunk = chunks[0]
    planned_bytes = chunk.chunk_bytes
    payload = build_gas_chunk_payload("Digit chunk rows", chunk)
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
        payload = build_gas_chunk_payload("Seeded random", chunk)
        assert len(payload) == planned_bytes
        assert chunk.chunk_bytes == planned_bytes


def test_parse_gas_ack_accepts_success_and_ignores_extra_fields():
    ack = parse_gas_ack(
        json.dumps(
            {
                "ok": True,
                "status": "accepted",
                "run_id": "run-6",
                "chunk_index": 1,
                "rows_received": 2,
                "rows_written": 2,
                "retryable": False,
                "schema_action": "unchanged",
                "added_columns": [],
                "message": "ok",
                "extra": "ignored",
            }
        ).encode("utf-8"),
        expected_run_id="run-6",
        expected_chunk_index=1,
    )

    assert isinstance(ack, GasAck)
    assert ack.ok is True
    assert ack.status == "accepted"
    assert ack.rows_written == 2


def test_parse_gas_ack_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_gas_ack(b"not-json", expected_run_id="run-7", expected_chunk_index=1)


def test_parse_gas_ack_rejects_wrong_run_or_chunk():
    with pytest.raises(ValueError):
        parse_gas_ack(
            json.dumps(
                {
                    "ok": True,
                    "status": "accepted",
                    "run_id": "other-run",
                    "chunk_index": 1,
                    "rows_received": 1,
                    "rows_written": 1,
                    "retryable": False,
                    "schema_action": "unchanged",
                    "added_columns": [],
                    "message": "ok",
                }
            ).encode("utf-8"),
            expected_run_id="run-8",
            expected_chunk_index=1,
        )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("app.export.sinks.google_apps_script.time.sleep", lambda *_: None)


def test_push_reports_progress_for_each_chunk(monkeypatch):
    attempts = []

    def _urlopen(req, **kwargs):
        attempts.append(req)
        body = json.loads(req.data.decode("utf-8"))
        return _FakeResp(
            {
                "ok": True,
                "status": "accepted",
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "rows_received": body["chunk_rows"],
                "rows_written": body["chunk_rows"],
                "retryable": False,
                "schema_action": "unchanged",
                "added_columns": [],
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


def test_push_sends_auth_token_in_json_body_not_headers(monkeypatch):
    seen = {}

    def _urlopen(req, **kwargs):
        seen["headers"] = dict(req.headers)
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp(
            {
                "ok": True,
                "status": "accepted",
                "run_id": seen["body"]["run_id"],
                "chunk_index": seen["body"]["chunk_index"],
                "rows_received": seen["body"]["chunk_rows"],
                "rows_written": seen["body"]["chunk_rows"],
                "retryable": False,
                "schema_action": "unchanged",
                "added_columns": [],
                "message": "ok",
            }
        )

    monkeypatch.setattr("app.export.sinks.google_apps_script.urllib.request.urlopen", _urlopen)

    sink = GoogleAppsScriptSink(
        "https://script.google.com/macros/s/abc/exec",
        gas_options={"auth_token": "secret-token"},
    )
    sink.push("Body auth", _qr())

    assert seen["body"]["auth_token"] == "secret-token"
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
                "rows_received": body["chunk_rows"],
                "rows_written": 0,
                "retryable": False,
                "schema_action": "unchanged",
                "added_columns": [],
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
        if attempts["count"] == 1:
            return _FakeResp(
                {
                    "ok": False,
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
                "rows_received": body["chunk_rows"],
                "rows_written": body["chunk_rows"],
                "retryable": False,
                "schema_action": "unchanged",
                "added_columns": [],
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
        return _FakeResp(
            {
                "ok": True,
                "status": "accepted",
                "run_id": body["run_id"],
                "chunk_index": body["chunk_index"],
                "rows_received": body["chunk_rows"],
                "rows_written": body["chunk_rows"],
                "retryable": False,
                "schema_action": "unchanged",
                "added_columns": [],
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
        if body["chunk_index"] == 1:
            return _FakeResp(
                {
                    "ok": True,
                    "status": "accepted",
                    "run_id": body["run_id"],
                    "chunk_index": body["chunk_index"],
                    "rows_received": body["chunk_rows"],
                    "rows_written": body["chunk_rows"],
                    "retryable": False,
                    "schema_action": "unchanged",
                    "added_columns": [],
                    "message": "ok",
                }
            )
        return _FakeResp(
            {
                "ok": False,
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
    assert "1/2 чанков" in exc.user_message


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
    assert exc.debug_context["cause_type"] == "GasAckError"
    assert exc.debug_context["error"] == "Unexpected server error: Sheets is not defined"
    assert exc.debug_context["ack_message"] == "Unexpected server error"
    assert exc.debug_context["error_code"] == "INTERNAL_WRITE_ERROR"
    assert exc.debug_context["ack_details"] == {
        "internal_message": "Sheets is not defined",
    }


def test_push_adds_deployment_hint_for_generic_internal_error_without_details(monkeypatch):
    def _urlopen(req, **kwargs):
        body = json.loads(req.data.decode("utf-8"))
        return _FakeResp(
            {
                "ok": False,
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
    assert exc.debug_context["cause_type"] == "GasAckError"
    assert exc.debug_context["error"] == "Unexpected server error"
    assert "publish the latest backend version" in exc.debug_context["hint"]
