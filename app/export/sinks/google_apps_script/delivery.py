"""Delivery transport and sink implementation for Google Apps Script."""

from __future__ import annotations

import logging
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
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

from .ack import GasAck, parse_gas_ack
from .chunking import GasChunkPlan, build_gas_chunk_payload, plan_gas_chunks

_log = logging.getLogger(__name__)
_SSL_CONTEXT = ssl.create_default_context()


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


def build_user_delivery_error(*, delivered_chunks: int, total_chunks: int) -> str:
    return f"Не удалось доставить данные: {delivered_chunks}/{total_chunks} чанков"


def _preview_response_body(raw_body: bytes | None) -> str:
    if not raw_body:
        return ""

    preview = raw_body.decode("utf-8", errors="replace").strip()
    if not preview:
        return ""

    preview = re.sub(r"\s+", " ", preview)
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
    "GoogleAppsScriptDeliveryError",
    "GoogleAppsScriptSink",
    "build_user_delivery_error",
]
