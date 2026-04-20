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
    rows_received: int
    rows_written: int
    retryable: bool
    schema_action: str
    added_columns: list[str]
    message: str
    error_code: str = ""
    details: dict[str, Any] | None = None


def parse_gas_ack(raw_body: bytes, *, expected_run_id: str, expected_chunk_index: int) -> GasAck:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Некорректный JSON-ack") from exc

    if not isinstance(payload, dict):
        raise ValueError("Некорректный формат ack")
    if payload.get("run_id") != expected_run_id:
        raise ValueError("Ack содержит другой run_id")
    if payload.get("chunk_index") != expected_chunk_index:
        raise ValueError("Ack содержит другой chunk_index")

    ok = bool(payload.get("ok"))
    if ok:
        required = (
            "status",
            "rows_received",
            "rows_written",
            "retryable",
            "schema_action",
            "added_columns",
            "message",
        )
    else:
        required = ("retryable", "message")
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"Ack не содержит обязательные поля: {', '.join(missing)}")

    return GasAck(
        ok=ok,
        status=str(payload.get("status", "")),
        run_id=str(payload["run_id"]),
        chunk_index=int(payload["chunk_index"]),
        rows_received=int(payload.get("rows_received", 0)),
        rows_written=int(payload.get("rows_written", 0)),
        retryable=bool(payload.get("retryable", False)),
        schema_action=str(payload.get("schema_action", "")),
        added_columns=list(payload.get("added_columns") or []),
        message=str(payload.get("message", "")),
        error_code=str(payload.get("error_code", "")),
        details=payload.get("details") if isinstance(payload.get("details"), dict) else None,
    )


__all__ = ["GasAck", "parse_gas_ack"]
