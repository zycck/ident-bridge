"""Chunk planning and payload construction for the Google Apps Script sink."""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import GasOptions, GasWriteMode, QueryResult, gas_write_mode_from_raw
from app.core.constants import (
    GOOGLE_SCRIPT_MAX_PAYLOAD_BYTES,
    GOOGLE_SCRIPT_MAX_ROWS_PER_CHUNK,
)
from app.export.sinks.webhook import _SqlJSONEncoder

_log = logging.getLogger(__name__)
_WHITESPACE_RE = re.compile(r"\s+")
_PROTOCOL_VERSION = "gas-sheet.v2"


@dataclass(kw_only=True, slots=True)
class GasChunkPlan:
    """Precomputed metadata and row payload for one GAS delivery chunk."""

    run_id: str
    chunk_index: int
    total_chunks: int
    total_rows: int
    chunk_rows: int
    chunk_bytes: int
    columns: list[str]
    records: list[dict[str, Any]]
    checksum: str


def canonicalize_column_name(name: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(name).strip()).casefold()


def build_chunk_records(
    columns: list[str],
    rows: list[tuple[Any, ...]] | tuple[tuple[Any, ...], ...],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        if len(row) != len(columns):
            raise ValueError("Количество значений в строке не совпадает с числом колонок")
        records.append({column: value for column, value in zip(columns, row)})
    return records


def _validate_columns(columns: list[str]) -> None:
    seen: set[str] = set()
    for column in columns:
        canonical = canonicalize_column_name(column)
        if not canonical:
            raise ValueError("Обнаружено пустое имя столбца")
        if canonical in seen:
            raise ValueError("Обнаружены дублирующиеся имена столбцов")
        seen.add(canonical)


def _resolve_export_date(export_date: str | None = None) -> str:
    value = str(export_date or "").strip()
    return value or datetime.now().date().isoformat()


def _normalize_sheet_name(
    job_name: str,
    gas_options: GasOptions | None,
) -> str:
    raw = gas_options or {}
    sheet_name = str(raw.get("sheet_name", "") or "").strip() or str(job_name or "").strip()
    return sheet_name


def _normalize_write_mode(gas_options: GasOptions | None) -> str:
    raw = gas_options or {}
    return gas_write_mode_from_raw(raw.get("write_mode")).value


def _normalize_source_id(source_id: str | None, job_name: str) -> str:
    return str(source_id or "").strip() or str(job_name or "").strip() or "job"


def _payload_without_checksum(
    job_name: str,
    sheet_name: str,
    export_date: str,
    source_id: str,
    write_mode: str,
    chunk: GasChunkPlan,
) -> dict[str, Any]:
    return {
        "protocol_version": _PROTOCOL_VERSION,
        "job_name": job_name,
        "run_id": chunk.run_id,
        "chunk_index": chunk.chunk_index,
        "total_chunks": chunk.total_chunks,
        "total_rows": chunk.total_rows,
        "chunk_rows": chunk.chunk_rows,
        "sheet_name": sheet_name,
        "export_date": export_date,
        "source_id": source_id,
        "write_mode": write_mode,
        "columns": chunk.columns,
        "records": chunk.records,
    }


def _compute_checksum(
    job_name: str,
    sheet_name: str,
    export_date: str,
    source_id: str,
    write_mode: str,
    chunk: GasChunkPlan,
) -> str:
    payload = json.dumps(
        _payload_without_checksum(job_name, sheet_name, export_date, source_id, write_mode, chunk),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        cls=_SqlJSONEncoder,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _payload_object(
    job_name: str,
    sheet_name: str,
    export_date: str,
    source_id: str,
    write_mode: str,
    chunk: GasChunkPlan,
) -> dict[str, Any]:
    payload = _payload_without_checksum(job_name, sheet_name, export_date, source_id, write_mode, chunk)
    payload["checksum"] = chunk.checksum
    return payload


def _measure_chunk_bytes(
    job_name: str,
    sheet_name: str,
    export_date: str,
    source_id: str,
    write_mode: str,
    chunk: GasChunkPlan,
) -> int:
    return len(
        json.dumps(
            _payload_object(job_name, sheet_name, export_date, source_id, write_mode, chunk),
            ensure_ascii=False,
            cls=_SqlJSONEncoder,
        ).encode("utf-8")
    )


def _finalize_chunk(
    *,
    job_name: str,
    sheet_name: str,
    export_date: str,
    source_id: str,
    write_mode: str,
    chunk: GasChunkPlan,
) -> GasChunkPlan:
    chunk.checksum = _compute_checksum(job_name, sheet_name, export_date, source_id, write_mode, chunk)
    chunk.chunk_bytes = _measure_chunk_bytes(job_name, sheet_name, export_date, source_id, write_mode, chunk)
    return chunk


def _make_chunk(
    *,
    run_id: str,
    columns: list[str],
    records: list[dict[str, Any]],
    chunk_index: int,
    total_chunks: int,
    total_rows: int,
) -> GasChunkPlan:
    return GasChunkPlan(
        run_id=run_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        total_rows=total_rows,
        chunk_rows=len(records),
        chunk_bytes=0,
        columns=columns,
        records=records,
        checksum="",
    )


def _split_chunks(
    *,
    job_name: str,
    result: QueryResult,
    run_id: str,
    source_id: str | None,
    max_rows_per_chunk: int,
    max_payload_bytes: int,
    total_chunks_hint: int,
    gas_options: GasOptions | None = None,
    export_date: str | None = None,
) -> list[GasChunkPlan]:
    sheet_name = _normalize_sheet_name(job_name, gas_options)
    source_id_value = _normalize_source_id(source_id, job_name)
    write_mode = _normalize_write_mode(gas_options)
    export_date_value = _resolve_export_date(export_date)
    columns = list(result.columns)
    total_rows = result.count
    row_dicts = build_chunk_records(columns, result.rows)

    if not row_dicts:
        chunk = _make_chunk(
            run_id=run_id,
            columns=columns,
            records=[],
            chunk_index=1,
            total_chunks=1,
            total_rows=0,
        )
        return [
            _finalize_chunk(
                job_name=job_name,
                sheet_name=sheet_name,
                export_date=export_date_value,
                source_id=source_id_value,
                write_mode=write_mode,
                chunk=chunk,
            )
        ]

    chunks_records: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for record in row_dicts:
        candidate_records = current + [record]
        candidate = _make_chunk(
            run_id=run_id,
            columns=columns,
            records=candidate_records,
            chunk_index=len(chunks_records) + 1,
            total_chunks=total_chunks_hint,
            total_rows=total_rows,
        )
        _finalize_chunk(
            job_name=job_name,
            sheet_name=sheet_name,
            export_date=export_date_value,
            source_id=source_id_value,
            write_mode=write_mode,
            chunk=candidate,
        )

        if len(candidate_records) <= max_rows_per_chunk and candidate.chunk_bytes <= max_payload_bytes:
            current = candidate_records
            continue

        if not current:
            raise ValueError("Одна строка превышает допустимый размер чанка")

        chunks_records.append(current)
        current = [record]
        single = _make_chunk(
            run_id=run_id,
            columns=columns,
            records=current,
            chunk_index=len(chunks_records) + 1,
            total_chunks=total_chunks_hint,
            total_rows=total_rows,
        )
        _finalize_chunk(
            job_name=job_name,
            sheet_name=sheet_name,
            export_date=export_date_value,
            source_id=source_id_value,
            write_mode=write_mode,
            chunk=single,
        )
        if len(current) > max_rows_per_chunk or single.chunk_bytes > max_payload_bytes:
            raise ValueError("Одна строка превышает допустимый размер чанка")

    if current or not chunks_records:
        chunks_records.append(current)

    total_chunks = len(chunks_records)
    chunks: list[GasChunkPlan] = []
    for index, records in enumerate(chunks_records, start=1):
        chunk = _make_chunk(
            run_id=run_id,
            columns=columns,
            records=records,
            chunk_index=index,
            total_chunks=total_chunks,
            total_rows=total_rows,
        )
        chunks.append(
            _finalize_chunk(
                job_name=job_name,
                sheet_name=sheet_name,
                export_date=export_date_value,
                source_id=source_id_value,
                write_mode=write_mode,
                chunk=chunk,
            )
        )
    return chunks


def plan_gas_chunks(
    job_name: str,
    result: QueryResult,
    *,
    run_id: str,
    source_id: str | None = None,
    write_mode: str | None = None,
    max_rows_per_chunk: int = GOOGLE_SCRIPT_MAX_ROWS_PER_CHUNK,
    max_payload_bytes: int = GOOGLE_SCRIPT_MAX_PAYLOAD_BYTES,
    gas_options: GasOptions | None = None,
    export_date: str | None = None,
) -> list[GasChunkPlan]:
    _validate_columns(list(result.columns))
    normalized_gas_options = dict(gas_options or {})
    if write_mode is not None:
        normalized_gas_options["write_mode"] = gas_write_mode_from_raw(write_mode).value

    hint = 1
    while True:
        chunks = _split_chunks(
            job_name=job_name,
            result=result,
            run_id=run_id,
            source_id=source_id,
            max_rows_per_chunk=max_rows_per_chunk,
            max_payload_bytes=max_payload_bytes,
            total_chunks_hint=hint,
            gas_options=normalized_gas_options,
            export_date=export_date,
        )
        final_total = len(chunks)
        if hint == final_total and all(chunk.chunk_bytes <= max_payload_bytes for chunk in chunks):
            return chunks
        hint = final_total


def build_gas_chunk_payload(
    job_name: str,
    chunk: GasChunkPlan,
    *,
    gas_options: GasOptions | None = None,
    source_id: str | None = None,
    write_mode: str | None = None,
    export_date: str | None = None,
) -> bytes:
    normalized_gas_options = dict(gas_options or {})
    if write_mode is not None:
        normalized_gas_options["write_mode"] = gas_write_mode_from_raw(write_mode).value
    sheet_name = _normalize_sheet_name(job_name, normalized_gas_options)
    source_id_value = _normalize_source_id(source_id, job_name)
    write_mode_value = _normalize_write_mode(normalized_gas_options)
    export_date_value = _resolve_export_date(export_date)
    _finalize_chunk(
        job_name=job_name,
        sheet_name=sheet_name,
        export_date=export_date_value,
        source_id=source_id_value,
        write_mode=write_mode_value,
        chunk=chunk,
    )
    return json.dumps(
        _payload_object(job_name, sheet_name, export_date_value, source_id_value, write_mode_value, chunk),
        ensure_ascii=False,
        cls=_SqlJSONEncoder,
    ).encode("utf-8")


__all__ = [
    "GasChunkPlan",
    "build_chunk_records",
    "build_gas_chunk_payload",
    "canonicalize_column_name",
    "plan_gas_chunks",
]
