"""Chunk planning and payload construction for the Google Apps Script sink."""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.config import GasOptions, QueryResult
from app.core.constants import (
    GOOGLE_SCRIPT_MAX_PAYLOAD_BYTES,
    GOOGLE_SCRIPT_MAX_ROWS_PER_CHUNK,
)
from app.export.sinks.webhook import _SqlJSONEncoder

_log = logging.getLogger(__name__)
_WHITESPACE_RE = re.compile(r"\s+")


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


def build_chunk_records(columns: list[str], rows: list[tuple[Any, ...]] | tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
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


def _compute_checksum(columns: list[str], records: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        {"columns": columns, "records": records},
        ensure_ascii=False,
        sort_keys=True,
        cls=_SqlJSONEncoder,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_gas_options(gas_options: GasOptions | None) -> GasOptions:
    raw = gas_options or {}
    header_row = raw.get("header_row", 1)
    try:
        normalized_header_row = max(1, int(header_row))
    except (TypeError, ValueError):
        normalized_header_row = 1
    dedupe_columns = raw.get("dedupe_key_columns") or []
    return {
        "sheet_name": str(raw.get("sheet_name", "") or "").strip(),
        "header_row": normalized_header_row,
        "dedupe_key_columns": [
            str(column).strip()
            for column in dedupe_columns
            if str(column).strip()
        ],
        "auth_token": str(raw.get("auth_token", "") or "").strip(),
    }


def _payload_target_block(gas_options: GasOptions) -> dict[str, Any] | None:
    sheet_name = str(gas_options.get("sheet_name", "") or "").strip()
    header_row = int(gas_options.get("header_row", 1) or 1)
    if not sheet_name and header_row == 1:
        return None
    return {
        "sheet_name": sheet_name,
        "header_row": header_row,
    }


def _payload_dedupe_block(gas_options: GasOptions) -> dict[str, Any] | None:
    key_columns = [
        str(column).strip()
        for column in (gas_options.get("dedupe_key_columns") or [])
        if str(column).strip()
    ]
    if not key_columns:
        return None
    return {
        "key_columns": key_columns,
    }


def _payload_object(
    job_name: str,
    chunk: GasChunkPlan,
    *,
    chunk_bytes: int | None = None,
    gas_options: GasOptions | None = None,
) -> dict[str, Any]:
    payload = {
        "protocol_version": "gas-sheet.v1",
        "job_name": job_name,
        "run_id": chunk.run_id,
        "chunk_index": chunk.chunk_index,
        "total_chunks": chunk.total_chunks,
        "total_rows": chunk.total_rows,
        "chunk_rows": chunk.chunk_rows,
        "chunk_bytes": chunk.chunk_bytes if chunk_bytes is None else chunk_bytes,
        "schema": {
            "mode": "append_only_v1",
            "columns": chunk.columns,
            "checksum": chunk.checksum,
        },
        "records": chunk.records,
    }
    normalized_gas_options = _normalize_gas_options(gas_options)
    auth_token = str(normalized_gas_options.get("auth_token", "") or "").strip()
    if auth_token:
        payload["auth_token"] = auth_token
    target = _payload_target_block(normalized_gas_options)
    if target is not None:
        payload["target"] = target
    dedupe = _payload_dedupe_block(normalized_gas_options)
    if dedupe is not None:
        payload["dedupe"] = dedupe
    return payload


def _measure_chunk_bytes(
    job_name: str,
    chunk: GasChunkPlan,
    *,
    gas_options: GasOptions | None = None,
) -> int:
    candidate = _payload_object(
        job_name,
        chunk,
        chunk_bytes=0,
        gas_options=gas_options,
    )
    previous = -1
    current = len(json.dumps(candidate, ensure_ascii=False, cls=_SqlJSONEncoder).encode("utf-8"))
    while current != previous:
        previous = current
        candidate["chunk_bytes"] = current
        current = len(json.dumps(candidate, ensure_ascii=False, cls=_SqlJSONEncoder).encode("utf-8"))
    return current


def _make_chunk(
    *,
    job_name: str,
    run_id: str,
    columns: list[str],
    records: list[dict[str, Any]],
    chunk_index: int,
    total_chunks: int,
    total_rows: int,
) -> GasChunkPlan:
    chunk = GasChunkPlan(
        run_id=run_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        total_rows=total_rows,
        chunk_rows=len(records),
        chunk_bytes=0,
        columns=columns,
        records=records,
        checksum=_compute_checksum(columns, records),
    )
    chunk.chunk_bytes = _measure_chunk_bytes(job_name, chunk)
    return chunk


def _estimate_payload_size(
    *,
    job_name: str,
    run_id: str,
    columns: list[str],
    chunk_index: int,
    total_chunks: int,
    total_rows: int,
    chunk_rows: int,
    records_bytes: int,
    gas_options: GasOptions | None = None,
) -> int:
    job_name_json = json.dumps(job_name, ensure_ascii=False, cls=_SqlJSONEncoder)
    run_id_json = json.dumps(run_id, ensure_ascii=False, cls=_SqlJSONEncoder)
    columns_json = json.dumps(columns, ensure_ascii=False, cls=_SqlJSONEncoder)
    checksum_json = json.dumps("0" * 64, ensure_ascii=False)
    normalized_gas_options = _normalize_gas_options(gas_options)
    optional_suffix = ""
    auth_token = str(normalized_gas_options.get("auth_token", "") or "").strip()
    if auth_token:
        optional_suffix += ',"auth_token":' + json.dumps(auth_token, ensure_ascii=False, cls=_SqlJSONEncoder)
    target = _payload_target_block(normalized_gas_options)
    dedupe = _payload_dedupe_block(normalized_gas_options)
    if target is not None:
        optional_suffix += ',"target":' + json.dumps(target, ensure_ascii=False, cls=_SqlJSONEncoder)
    if dedupe is not None:
        optional_suffix += ',"dedupe":' + json.dumps(dedupe, ensure_ascii=False, cls=_SqlJSONEncoder)

    previous = -1
    current = 0
    while current != previous:
        previous = current
        prefix = (
            '{"protocol_version":"gas-sheet.v1","job_name":'
            + job_name_json
            + ',"run_id":'
            + run_id_json
            + ',"chunk_index":'
            + str(chunk_index)
            + ',"total_chunks":'
            + str(total_chunks)
            + ',"total_rows":'
            + str(total_rows)
            + ',"chunk_rows":'
            + str(chunk_rows)
            + ',"chunk_bytes":'
            + str(max(current, 0))
            + ',"schema":{"mode":"append_only_v1","columns":'
            + columns_json
            + ',"checksum":'
            + checksum_json
            + '},"records":'
        )
        current = len(prefix.encode("utf-8")) + records_bytes + len(optional_suffix.encode("utf-8")) + 1
    return current


def _split_chunks(
    *,
    job_name: str,
    result: QueryResult,
    run_id: str,
    max_rows_per_chunk: int,
    max_payload_bytes: int,
    total_chunks_hint: int,
    gas_options: GasOptions | None = None,
) -> list[GasChunkPlan]:
    columns = list(result.columns)
    total_rows = result.count
    row_dicts = build_chunk_records(columns, result.rows)
    row_jsons = [
        json.dumps(record, ensure_ascii=False, cls=_SqlJSONEncoder, separators=(",", ":"))
        for record in row_dicts
    ]
    row_json_sizes = [len(row_json.encode("utf-8")) for row_json in row_jsons]

    if not row_dicts:
        return [
            _make_chunk(
                job_name=job_name,
                run_id=run_id,
                columns=columns,
                records=[],
                chunk_index=1,
                total_chunks=1,
                total_rows=0,
            )
        ]

    chunks_records: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_bytes = 0

    for record, row_size in zip(row_dicts, row_json_sizes):
        chunk_index = len(chunks_records) + 1
        candidate_count = len(current) + 1
        candidate_records_bytes = 2 + current_bytes + row_size + max(candidate_count - 1, 0)
        candidate_bytes = _estimate_payload_size(
            job_name=job_name,
            run_id=run_id,
            columns=columns,
            chunk_index=chunk_index,
            total_chunks=total_chunks_hint,
            total_rows=total_rows,
            chunk_rows=candidate_count,
            records_bytes=candidate_records_bytes,
            gas_options=gas_options,
        )
        if candidate_count <= max_rows_per_chunk and candidate_bytes <= max_payload_bytes:
            current.append(record)
            current_bytes += row_size
            continue
        if not current:
            raise ValueError("Одна строка превышает допустимый размер чанка")
        chunks_records.append(current)
        current = [record]
        current_bytes = row_size
        single_record_bytes = _estimate_payload_size(
            job_name=job_name,
            run_id=run_id,
            columns=columns,
            chunk_index=len(chunks_records) + 1,
            total_chunks=total_chunks_hint,
            total_rows=total_rows,
            chunk_rows=1,
            records_bytes=2 + row_size,
            gas_options=gas_options,
        )
        if single_record_bytes > max_payload_bytes:
            raise ValueError("Одна строка превышает допустимый размер чанка")

    if current or not chunks_records:
        chunks_records.append(current)

    total_chunks = len(chunks_records)
    return [
        _make_chunk(
            job_name=job_name,
            run_id=run_id,
            columns=columns,
            records=records,
            chunk_index=index,
            total_chunks=total_chunks,
            total_rows=total_rows,
        )
        for index, records in enumerate(chunks_records, start=1)
    ]


def plan_gas_chunks(
    job_name: str,
    result: QueryResult,
    *,
    run_id: str,
    max_rows_per_chunk: int = GOOGLE_SCRIPT_MAX_ROWS_PER_CHUNK,
    max_payload_bytes: int = GOOGLE_SCRIPT_MAX_PAYLOAD_BYTES,
    gas_options: GasOptions | None = None,
) -> list[GasChunkPlan]:
    _validate_columns(list(result.columns))

    hint = 1
    while True:
        chunks = _split_chunks(
            job_name=job_name,
            result=result,
            run_id=run_id,
            max_rows_per_chunk=max_rows_per_chunk,
            max_payload_bytes=max_payload_bytes,
            total_chunks_hint=hint,
            gas_options=gas_options,
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
) -> bytes:
    chunk.chunk_bytes = _measure_chunk_bytes(
        job_name,
        chunk,
        gas_options=gas_options,
    )
    return json.dumps(
        _payload_object(job_name, chunk, gas_options=gas_options),
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
