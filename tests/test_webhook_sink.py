"""Tests for app.export.sinks.webhook."""

from __future__ import annotations

import datetime as dt
import decimal
import enum
import json
import uuid

import pytest

from app.config import QueryResult
from app.export.protocol import ExportSink
from app.export.sinks import webhook as webhook_mod
from app.export.sinks.webhook import WebhookSink, build_webhook_payload


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("app.export.sinks.webhook.time.sleep", lambda *_: None)


def _qr(columns=("id",), rows=((1,),), duration=1) -> QueryResult:
    return QueryResult(
        columns=list(columns),
        rows=list(rows),
        count=len(rows),
        duration_ms=duration,
    )


class _FakeResp:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- Protocol conformance ------------------------------------------------


def test_webhook_sink_is_a_protocol_sink():
    sink = WebhookSink("https://example.com/hook")
    assert isinstance(sink, ExportSink)
    assert sink.name == "webhook"


# --- Serialisation -------------------------------------------------------


def test_payload_shape_is_stable():
    result = _qr(columns=("id", "name"), rows=((1, "alice"), (2, "bob")))
    decoded = json.loads(build_webhook_payload("My Job", result).decode("utf-8"))
    assert decoded == {
        "job": "My Job",
        "rows": 2,
        "columns": ["id", "name"],
        "data": [[1, "alice"], [2, "bob"]],
    }


def test_encoder_handles_decimal_as_string():
    result = _qr(columns=("price",), rows=((decimal.Decimal("3.1415926535"),),))
    decoded = json.loads(build_webhook_payload("d", result).decode("utf-8"))
    assert decoded["data"] == [["3.1415926535"]]


def test_encoder_handles_datetime_date_time():
    row = (
        dt.datetime(2026, 4, 17, 12, 0, 0),
        dt.date(2026, 4, 17),
        dt.time(9, 30),
    )
    result = _qr(columns=("a", "b", "c"), rows=(row,))
    decoded = json.loads(build_webhook_payload("ts", result).decode("utf-8"))
    assert decoded["data"][0] == [
        "2026-04-17T12:00:00",
        "2026-04-17",
        "09:30:00",
    ]


def test_encoder_handles_timedelta_as_seconds():
    result = _qr(columns=("dur",), rows=((dt.timedelta(minutes=1, seconds=30),),))
    decoded = json.loads(build_webhook_payload("d", result).decode("utf-8"))
    assert decoded["data"][0] == [90.0]


def test_encoder_handles_bytes_as_hex():
    result = _qr(columns=("blob",), rows=((b"\x01\x02\xff",),))
    decoded = json.loads(build_webhook_payload("b", result).decode("utf-8"))
    assert decoded["data"][0] == ["0102ff"]


def test_encoder_handles_uuid():
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    result = _qr(columns=("gid",), rows=((u,),))
    decoded = json.loads(build_webhook_payload("u", result).decode("utf-8"))
    assert decoded["data"][0] == [str(u)]


def test_encoder_handles_enum():
    class Color(enum.Enum):
        RED = "red"

    result = _qr(columns=("c",), rows=((Color.RED,),))
    decoded = json.loads(build_webhook_payload("e", result).decode("utf-8"))
    assert decoded["data"][0] == ["red"]


# --- Push & retry behaviour ----------------------------------------------


def test_push_calls_urlopen_once_on_success(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.export.sinks.webhook.urllib.request.urlopen",
        lambda req, **kw: (calls.append(req), _FakeResp(200))[1],
    )
    sink = WebhookSink("https://example.com/hook")
    sink.push("Job", _qr())
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].full_url == "https://example.com/hook"


def test_push_retries_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def _flaky(req, **kw):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("transient")
        return _FakeResp(200)

    monkeypatch.setattr(
        "app.export.sinks.webhook.urllib.request.urlopen", _flaky,
    )
    sink = WebhookSink("https://example.com/hook", retries=3)
    sink.push("Job", _qr())
    assert attempts["n"] == 3


def test_push_reraises_after_all_retries(monkeypatch):
    def _always_fail(req, **kw):
        raise OSError("down")

    monkeypatch.setattr(
        "app.export.sinks.webhook.urllib.request.urlopen", _always_fail,
    )
    sink = WebhookSink("https://example.com/hook", retries=2)
    with pytest.raises(OSError):
        sink.push("Job", _qr())


def test_push_raises_when_over_max_rows():
    sink = WebhookSink("https://example.com/hook", max_rows=1)
    with pytest.raises(ValueError, match="Слишком много строк"):
        sink.push("Job", _qr(rows=((1,), (2,), (3,))))


def test_push_uses_configured_ssl_context(monkeypatch):
    captured_kwargs = {}

    def _spy(req, **kw):
        captured_kwargs.update(kw)
        return _FakeResp(200)

    monkeypatch.setattr(
        "app.export.sinks.webhook.urllib.request.urlopen", _spy,
    )
    import ssl
    ctx = ssl.create_default_context()
    sink = WebhookSink("https://example.com/hook", ssl_context=ctx)
    sink.push("J", _qr())
    assert captured_kwargs.get("context") is ctx


def test_push_sets_content_type_and_user_agent(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "app.export.sinks.webhook.urllib.request.urlopen",
        lambda req, **kw: (captured.append(req), _FakeResp(200))[1],
    )
    WebhookSink("https://example.com/hook").push("J", _qr())
    headers = dict(captured[0].headers)
    # urllib canonicalises header names to Title-Case
    assert headers.get("Content-type") == "application/json; charset=utf-8"
    assert headers.get("User-agent") == "iDentBridge"
