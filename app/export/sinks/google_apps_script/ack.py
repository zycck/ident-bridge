"""Ack parsing helpers for the Google Apps Script sink."""

import json
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GasAck:
    ok: bool
    status: str
    run_id: str
    chunk_index: int
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
        raise ValueError(f"Ack содержит некорректный {field_name}") from exc


def parse_gas_ack(raw_body: bytes, *, expected_run_id: str, expected_chunk_index: int) -> GasAck:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Некорректный JSON-ack") from exc

    if not isinstance(payload, dict):
        raise ValueError("Некорректный формат ack")

    ok = bool(payload.get("ok"))
    if ok:
        required = ("status", "run_id", "chunk_index", "retryable", "message")
    else:
        required = ("retryable", "message")
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"Ack не содержит обязательные поля: {', '.join(missing)}")

    status = str(payload.get("status", "") or "").strip()
    if ok and not status:
        raise ValueError("Ack не содержит обязательные поля: status")

    raw_run_id = payload.get("run_id")
    raw_chunk_index = payload.get("chunk_index")
    if ok:
        if str(raw_run_id) != expected_run_id:
            raise ValueError("Ack содержит другой run_id")
        if _coerce_int(raw_chunk_index, field_name="chunk_index") != expected_chunk_index:
            raise ValueError("Ack содержит другой chunk_index")
        run_id = str(raw_run_id)
        chunk_index = expected_chunk_index
    else:
        if raw_run_id not in {"", None, expected_run_id}:
            raise ValueError("Ack содержит другой run_id")
        if raw_chunk_index not in {"", None, expected_chunk_index}:
            raise ValueError("Ack содержит другой chunk_index")
        run_id = str(raw_run_id or expected_run_id)
        chunk_index = _coerce_int(raw_chunk_index or expected_chunk_index, field_name="chunk_index")

    rows_received = int(payload.get("rows_received", payload.get("chunk_rows", 0)) or 0)
    rows_written = int(payload.get("rows_written", payload.get("chunk_rows", 0)) or 0)
    details = payload.get("details") if isinstance(payload.get("details"), dict) else None

    return GasAck(
        ok=ok,
        status=status,
        run_id=run_id,
        chunk_index=chunk_index,
        retryable=bool(payload.get("retryable", False)),
        message=str(payload.get("message", "") or "").strip(),
        rows_received=rows_received,
        rows_written=rows_written,
        error_code=str(payload.get("error_code", "") or "").strip(),
        details=details,
    )


__all__ = ["GasAck", "parse_gas_ack"]
