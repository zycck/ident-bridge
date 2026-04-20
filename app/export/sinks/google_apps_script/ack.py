"""Ack parsing helpers for the Google Apps Script sink."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GasAck:
    ok: bool
    status: str
    retryable: bool
    message: str
    rows_received: int = 0
    rows_written: int = 0
    error_code: str = ""
    details: dict[str, Any] | None = None


def _coerce_int(value: Any, *, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Ack \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439 {field_name}") from exc


def parse_gas_ack(raw_body: bytes) -> GasAck:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("\u041d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439 JSON-ack") from exc

    if not isinstance(payload, dict):
        raise ValueError("\u041d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 ack")

    ok = bool(payload.get("ok"))
    required = ("retryable", "message")
    if ok:
        required += ("status",)

    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(
            "Ack \u043d\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u043f\u043e\u043b\u044f: "
            + ", ".join(missing)
        )

    status = str(payload.get("status", "") or "").strip()
    if ok and not status:
        raise ValueError("Ack \u043d\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u043f\u043e\u043b\u044f: status")

    rows_received = int(payload.get("rows_received", payload.get("chunk_rows", 0)) or 0)
    rows_written = int(payload.get("rows_written", payload.get("chunk_rows", 0)) or 0)
    details = payload.get("details") if isinstance(payload.get("details"), dict) else None

    return GasAck(
        ok=ok,
        status=status,
        retryable=bool(payload.get("retryable", False)),
        message=str(payload.get("message", "") or "").strip(),
        rows_received=rows_received,
        rows_written=rows_written,
        error_code=str(payload.get("error_code", "") or "").strip(),
        details=details,
    )


__all__ = ["GasAck", "parse_gas_ack"]
