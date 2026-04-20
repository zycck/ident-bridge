"""Ack parsing helpers for the Google Apps Script sink."""

import json
from dataclasses import dataclass
from typing import Any

SUPPORTED_API_MAJOR = 1


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
    api_version: str = ""
    error_code: str = ""
    details: dict[str, Any] | None = None


def _validate_api_version(payload: dict[str, Any]) -> str:
    api_version = str(payload.get("api_version", "") or "").strip()
    if not api_version:
        return ""

    major_text = api_version.split(".", 1)[0]
    if not major_text.isdigit():
        raise ValueError("Ack содержит некорректный api_version")

    if int(major_text) != SUPPORTED_API_MAJOR:
        raise ValueError("Ack содержит несовместимый api_version")

    return api_version


def parse_gas_ack(raw_body: bytes, *, expected_run_id: str, expected_chunk_index: int) -> GasAck:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Некорректный JSON-ack") from exc

    if not isinstance(payload, dict):
        raise ValueError("Некорректный формат ack")
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
    api_version = _validate_api_version(payload)

    raw_run_id = payload.get("run_id")
    raw_chunk_index = payload.get("chunk_index")

    if ok:
        if raw_run_id != expected_run_id:
            raise ValueError("Ack содержит другой run_id")
        if raw_chunk_index != expected_chunk_index:
            raise ValueError("Ack содержит другой chunk_index")
        run_id = str(raw_run_id)
        chunk_index = int(raw_chunk_index)
    else:
        if raw_run_id not in {"", None, expected_run_id}:
            raise ValueError("Ack содержит другой run_id")
        if raw_chunk_index not in {"", None, expected_chunk_index}:
            raise ValueError("Ack содержит другой chunk_index")
        run_id = str(raw_run_id or expected_run_id)
        chunk_index = int(raw_chunk_index or expected_chunk_index)

    return GasAck(
        ok=ok,
        status=str(payload.get("status", "")),
        run_id=run_id,
        chunk_index=chunk_index,
        rows_received=int(payload.get("rows_received", 0)),
        rows_written=int(payload.get("rows_written", 0)),
        retryable=bool(payload.get("retryable", False)),
        schema_action=str(payload.get("schema_action", "")),
        added_columns=list(payload.get("added_columns") or []),
        message=str(payload.get("message", "")),
        api_version=api_version,
        error_code=str(payload.get("error_code", "")),
        details=payload.get("details") if isinstance(payload.get("details"), dict) else None,
    )


__all__ = ["GasAck", "parse_gas_ack"]
