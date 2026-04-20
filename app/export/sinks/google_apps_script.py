"""Chunked Google Apps Script webhook transport."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from app.config import GasOptions, QueryResult
from app.core.constants import (
    GOOGLE_SCRIPT_HOSTS,
    GOOGLE_SCRIPT_MAX_PAYLOAD_BYTES,
    GOOGLE_SCRIPT_MAX_ROWS_PER_CHUNK,
    GOOGLE_SCRIPT_RETRIES,
    GOOGLE_SCRIPT_TIMEOUT,
    USER_AGENT,
)
from app.export.sinks.webhook import _SqlJSONEncoder

_log = logging.getLogger(__name__)
_SSL_CONTEXT = ssl.create_default_context()
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class GasChunkPlan:
    run_id: str
    chunk_index: int
    total_chunks: int
    total_rows: int
    chunk_rows: int
    chunk_bytes: int
    columns: list[str]
    records: list[dict[str, Any]]
    checksum: str


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


class GoogleAppsScriptDeliveryError(RuntimeError):
    def __init__(
        self,
        user_message: str,
        *,
        run_id: str,
        delivered_chunks: int,
        delivered_rows: int,
        failed_chunk_index: int,
        debug_context: dict[str, Any],
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.run_id = run_id
        self.delivered_chunks = delivered_chunks
        self.delivered_rows = delivered_rows
        self.failed_chunk_index = failed_chunk_index
        self.debug_context = debug_context


class _RetryableAckError(RuntimeError):
    pass


class _ChunkDeliveryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        cause_type: str,
        http_status: int | None = None,
        http_body_preview: str = "",
        ack_message: str = "",
        error_code: str = "",
        ack_details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.cause_type = cause_type
        self.http_status = http_status
        self.http_body_preview = http_body_preview
        self.ack_message = ack_message
        self.error_code = error_code
        self.ack_details = ack_details or {}


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
    target = _payload_target_block(normalized_gas_options)
    if target is not None:
        payload["target"] = target
    dedupe = _payload_dedupe_block(normalized_gas_options)
    if dedupe is not None:
        payload["dedupe"] = dedupe
    return payload


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
        required = ("status", "rows_received", "rows_written", "retryable", "schema_action", "added_columns", "message")
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


def build_user_delivery_error(*, delivered_chunks: int, total_chunks: int) -> str:
    return f"Не удалось доставить данные: {delivered_chunks}/{total_chunks} чанков"


def _preview_response_body(raw_body: bytes | None) -> str:
    if not raw_body:
        return ""

    preview = raw_body.decode("utf-8", errors="replace").strip()
    if not preview:
        return ""

    preview = _WHITESPACE_RE.sub(" ", preview)
    return preview[:240]


def _build_http_failure_message(http_status: int | None, body_preview: str) -> str:
    if http_status is None:
        return body_preview or "HTTP error"
    if body_preview:
        return f"HTTP {http_status}: {body_preview}"
    return f"HTTP {http_status}"


def _build_ack_failure_message(ack: GasAck) -> str:
    details = ack.details or {}
    internal_message = str(details.get("internal_message", "") or "").strip()
    base_message = str(ack.message or ack.error_code or "Ack failure").strip()

    if internal_message and internal_message not in base_message:
        return f"{base_message}: {internal_message}"
    return base_message


class GoogleAppsScriptSink:
    name = "google_apps_script"

    def __init__(
        self,
        url: str,
        *,
        gas_options: GasOptions | None = None,
        max_rows_per_chunk: int = GOOGLE_SCRIPT_MAX_ROWS_PER_CHUNK,
        max_payload_bytes: int = GOOGLE_SCRIPT_MAX_PAYLOAD_BYTES,
        retries: int = GOOGLE_SCRIPT_RETRIES,
        base_delay: float = 2.0,
        timeout: float = GOOGLE_SCRIPT_TIMEOUT,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._url = url
        self._gas_options = _normalize_gas_options(gas_options)
        self._max_rows_per_chunk = max_rows_per_chunk
        self._max_payload_bytes = max_payload_bytes
        self._retries = max(1, retries)
        self._base_delay = base_delay
        self._timeout = timeout
        self._ssl = ssl_context or _SSL_CONTEXT
        self._validate_target_url()

    def _validate_target_url(self) -> None:
        parsed = urllib.parse.urlsplit(self._url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Webhook URL должен использовать HTTP(S)")
        if parsed.hostname not in GOOGLE_SCRIPT_HOSTS:
            raise ValueError("Google Apps Script sink поддерживает только URL Google Apps Script")

    def push(self, job_name: str, result: QueryResult, *, on_progress=None) -> None:
        run_id = str(uuid.uuid4())
        try:
            chunks = plan_gas_chunks(
                job_name,
                result,
                run_id=run_id,
                max_rows_per_chunk=self._max_rows_per_chunk,
                max_payload_bytes=self._max_payload_bytes,
                gas_options=self._gas_options,
            )
        except ValueError as exc:
            raise GoogleAppsScriptDeliveryError(
                "Не удалось подготовить данные к отправке",
                run_id=run_id,
                delivered_chunks=0,
                delivered_rows=0,
                failed_chunk_index=1,
                debug_context={"phase": "planning", "error": str(exc), "url": self._url},
            ) from exc

        delivered_chunks = 0
        delivered_rows = 0
        for chunk in chunks:
            payload = build_gas_chunk_payload(
                job_name,
                chunk,
                gas_options=self._gas_options,
            )
            try:
                ack = self._post_chunk(payload, chunk)
            except Exception as exc:  # noqa: BLE001
                raise self._delivery_error(
                    run_id=run_id,
                    total_chunks=len(chunks),
                    delivered_chunks=delivered_chunks,
                    delivered_rows=delivered_rows,
                    failed_chunk=chunk,
                    cause=exc,
                ) from exc

            delivered_chunks += 1
            delivered_rows += ack.rows_received
            if on_progress is not None:
                on_progress(f"Отправка данных... {chunk.chunk_index}/{len(chunks)}")
            if ack.status == "schema_extended":
                _log.info(
                    "event=export.schema.extended run_id=%s chunk=%s/%s added_columns=%s",
                    run_id,
                    chunk.chunk_index,
                    len(chunks),
                    ",".join(ack.added_columns),
                )

    def _post_chunk(self, payload: bytes, chunk: GasChunkPlan) -> GasAck:
        last_exc: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                req = urllib.request.Request(
                    self._url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "User-Agent": USER_AGENT,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self._timeout, context=self._ssl) as resp:
                    raw_body = resp.read()
                ack = parse_gas_ack(
                    raw_body,
                    expected_run_id=chunk.run_id,
                    expected_chunk_index=chunk.chunk_index,
                )
            except urllib.error.HTTPError as exc:
                http_status = getattr(exc, "code", None)
                raw_body = exc.read()
                body_preview = _preview_response_body(raw_body)
                try:
                    ack = parse_gas_ack(
                        raw_body,
                        expected_run_id=chunk.run_id,
                        expected_chunk_index=chunk.chunk_index,
                    )
                except Exception as parse_exc:  # noqa: BLE001
                    last_exc = _ChunkDeliveryError(
                        _build_http_failure_message(http_status, body_preview),
                        cause_type=type(exc).__name__,
                        http_status=http_status,
                        http_body_preview=body_preview,
                    )
                    ack = None  # type: ignore[assignment]
                else:
                    if ack.ok or ack.retryable:
                        pass
                    else:
                        raise _ChunkDeliveryError(
                            _build_http_failure_message(http_status, ack.message or body_preview),
                            cause_type=type(exc).__name__,
                            http_status=http_status,
                            http_body_preview=body_preview,
                            ack_message=ack.message,
                            error_code=ack.error_code,
                            ack_details=ack.details,
                        )
            except ValueError as exc:
                last_exc = _RetryableAckError(str(exc))
                ack = None  # type: ignore[assignment]
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                ack = None  # type: ignore[assignment]

            if ack is not None:
                if ack.ok:
                    return ack
                if not ack.retryable:
                    raise _ChunkDeliveryError(
                        _build_ack_failure_message(ack),
                        cause_type="GasAckError",
                        ack_message=ack.message,
                        error_code=ack.error_code,
                        ack_details=ack.details,
                    )
                last_exc = _ChunkDeliveryError(
                    _build_ack_failure_message(ack),
                    cause_type="GasAckError",
                    ack_message=ack.message,
                    error_code=ack.error_code,
                    ack_details=ack.details,
                )

            if attempt < self._retries:
                time.sleep(self._base_delay * (2 ** (attempt - 1)))
                continue
            if last_exc is None:
                last_exc = RuntimeError("Неизвестная ошибка отправки чанка")
            raise last_exc

        raise RuntimeError("Не удалось отправить чанк")

    def _delivery_error(
        self,
        *,
        run_id: str,
        total_chunks: int,
        delivered_chunks: int,
        delivered_rows: int,
        failed_chunk: GasChunkPlan,
        cause: Exception,
    ) -> GoogleAppsScriptDeliveryError:
        user_message = build_user_delivery_error(
            delivered_chunks=delivered_chunks,
            total_chunks=total_chunks,
        )
        debug_context = {
            "url": self._url,
            "run_id": run_id,
            "delivered_chunks": delivered_chunks,
            "delivered_rows": delivered_rows,
            "failed_chunk_index": failed_chunk.chunk_index,
            "total_chunks": total_chunks,
            "chunk_rows": failed_chunk.chunk_rows,
            "chunk_bytes": failed_chunk.chunk_bytes,
            "error": str(cause),
            "cause_type": getattr(cause, "cause_type", type(cause).__name__),
        }
        if isinstance(cause, _ChunkDeliveryError):
            debug_context["http_status"] = cause.http_status
            debug_context["http_body_preview"] = cause.http_body_preview
            if cause.ack_message:
                debug_context["ack_message"] = cause.ack_message
            if cause.error_code:
                debug_context["error_code"] = cause.error_code
            if cause.ack_details:
                debug_context["ack_details"] = cause.ack_details
            if (
                cause.error_code == "INTERNAL_WRITE_ERROR"
                and cause.ack_message == "Unexpected server error"
                and not cause.ack_details
            ):
                debug_context["hint"] = (
                    "Backend returned a generic internal error without details. "
                    "If you are using an Apps Script /exec deployment, publish the latest backend version."
                )
        return GoogleAppsScriptDeliveryError(
            user_message,
            run_id=run_id,
            delivered_chunks=delivered_chunks,
            delivered_rows=delivered_rows,
            failed_chunk_index=failed_chunk.chunk_index,
            debug_context=debug_context,
        )


__all__ = [
    "GasAck",
    "GasChunkPlan",
    "GoogleAppsScriptDeliveryError",
    "GoogleAppsScriptSink",
    "build_chunk_records",
    "build_gas_chunk_payload",
    "build_user_delivery_error",
    "canonicalize_column_name",
    "parse_gas_ack",
    "plan_gas_chunks",
]
