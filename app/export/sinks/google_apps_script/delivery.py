"""Delivery transport and sink implementation for Google Apps Script."""

import logging
import os
import re
import ssl
import time
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, final

from app.config import GasOptions, QueryResult, gas_write_mode_from_raw
from app.export.run_store import ExportRunStore
from app.core.constants import (
    EXPORT_SOURCE_ID,
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


def _build_actionable_ack_message(cause: "_ChunkDeliveryError") -> str:
    if cause.error_code == "UNAUTHORIZED":
        return "Доступ к обработчику запрещён. Проверьте публикацию проекта Apps Script и права доступа."

    if cause.error_code == "INVALID_REQUEST_METHOD":
        return (
            "\u0410\u0434\u0440\u0435\u0441 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438 "
            "\u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d \u043d\u0435\u0432\u0435\u0440\u043d\u043e. "
            "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435, \u0447\u0442\u043e "
            "\u0443\u043a\u0430\u0437\u0430\u043d \u0430\u0434\u0440\u0435\u0441 \u0432\u0435\u0431-\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f Apps Script."
        )

    if cause.error_code == "MALFORMED_JSON":
        return (
            "\u0410\u0434\u0440\u0435\u0441 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438 "
            "\u043e\u0442\u0432\u0435\u0442\u0438\u043b \u043d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u043e. "
            "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435, \u0447\u0442\u043e "
            "\u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442\u0441\u044f "
            "\u043e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u043d\u043d\u044b\u0439 "
            "\u0430\u0434\u0440\u0435\u0441 \u043f\u0440\u043e\u0435\u043a\u0442\u0430 Apps Script \u0442\u0430\u0431\u043b\u0438\u0446\u044b."
        )

    if cause.error_code == "INVALID_ACTION":
        return (
            "\u0410\u0434\u0440\u0435\u0441 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438 "
            "\u043d\u0435 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442 "
            "\u043e\u0436\u0438\u0434\u0430\u0435\u043c\u044b\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f. "
            "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435, \u0447\u0442\u043e "
            "\u0440\u0430\u0437\u0432\u0435\u0440\u043d\u0443\u0442\u0430 "
            "\u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u0430\u044f \u0432\u0435\u0440\u0441\u0438\u044f \u0441\u043a\u0440\u0438\u043f\u0442\u0430."
        )

    return ""

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
    return str(ack.message or ack.error_code or "Ack failure").strip()


@final
class GoogleAppsScriptSink:
    name = "google_apps_script"

    def __init__(
        self,
        url: str,
        *,
        gas_options: GasOptions | None = None,
        source_id: str | None = None,
        job_id: str | None = None,
        run_store: ExportRunStore | None = None,
        max_rows_per_chunk: int = GOOGLE_SCRIPT_MAX_ROWS_PER_CHUNK,
        max_payload_bytes: int = GOOGLE_SCRIPT_MAX_PAYLOAD_BYTES,
        retries: int = GOOGLE_SCRIPT_RETRIES,
        base_delay: float = 2.0,
        timeout: float = GOOGLE_SCRIPT_TIMEOUT,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._url = str(os.environ.get("IDENTBRIDGE_GAS_DEV_URL", "") or "").strip() or url
        self._gas_options = gas_options
        self._source_id = str(source_id or "").strip() or EXPORT_SOURCE_ID
        self._job_id = str(job_id or "").strip() or "job"
        self._run_store = run_store or ExportRunStore()
        self._max_rows_per_chunk = max_rows_per_chunk
        self._max_payload_bytes = max_payload_bytes
        self._retries = max(1, retries)
        self._base_delay = base_delay
        self._timeout = timeout
        self._ssl = ssl_context or _SSL_CONTEXT
        self._last_run_id: str | None = None
        self._last_run_journaled = False
        self._validate_target_url()

    @property
    def last_run_id(self) -> str | None:
        return self._last_run_id

    @property
    def last_run_journaled(self) -> bool:
        return self._last_run_journaled

    def _write_mode(self) -> str:
        return gas_write_mode_from_raw((self._gas_options or {}).get("write_mode")).value

    def _sheet_name(self, job_name: str) -> str:
        configured = str((self._gas_options or {}).get("sheet_name", "") or "").strip()
        return configured or job_name

    def _validate_target_url(self) -> None:
        parsed = urllib.parse.urlsplit(self._url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Webhook URL должен использовать HTTP(S)")
        if parsed.hostname not in GOOGLE_SCRIPT_HOSTS:
            raise ValueError("Google Apps Script sink поддерживает только URL Google Apps Script")

    def push(
        self,
        job_name: str,
        result: QueryResult,
        *,
        on_progress=None,
        trigger: str = "manual",
    ) -> None:
        run_id = str(uuid.uuid4())
        export_date = datetime.now().date().isoformat()
        self._last_run_id = run_id
        self._last_run_journaled = False

        if on_progress is not None:
            on_progress("Подготовка данных...")

        try:
            chunks = plan_gas_chunks(
                job_name,
                result,
                run_id=run_id,
                source_id=self._source_id,
                write_mode=self._write_mode(),
                max_rows_per_chunk=self._max_rows_per_chunk,
                max_payload_bytes=self._max_payload_bytes,
                gas_options=self._gas_options,
                export_date=export_date,
            )
        except ValueError as exc:
            raise GoogleAppsScriptDeliveryError(
                "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u0438\u0442\u044c \u0434\u0430\u043d\u043d\u044b\u0435 \u043a \u043e\u0442\u043f\u0440\u0430\u0432\u043a\u0435",
                run_id=run_id,
                delivered_chunks=0,
                delivered_rows=0,
                failed_chunk_index=1,
                debug_context={"phase": "planning", "error": str(exc), "url": self._url},
            ) from exc

        self._run_store.create_run(
            run_id=run_id,
            job_id=self._job_id,
            job_name=job_name,
            webhook_url=self._url,
            sheet_name=self._sheet_name(job_name),
            source_id=self._source_id,
            write_mode=self._write_mode(),
            export_date=export_date,
            total_chunks=len(chunks),
            total_rows=result.count,
            trigger=trigger,
            sql_duration_us=result.duration_us,
        )
        self._run_store.supersede_unfinished_runs(job_id=self._job_id, new_run_id=run_id)
        self._last_run_journaled = True

        delivered_chunks = 0
        delivered_rows = 0
        started_ns = time.perf_counter_ns()
        try:
            self._run_store.mark_running(run_id)
            for chunk in chunks:
                payload = build_gas_chunk_payload(
                    job_name,
                    chunk,
                    gas_options=self._gas_options,
                    source_id=self._source_id,
                    write_mode=self._write_mode(),
                    export_date=export_date,
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
                delivered_rows += ack.rows_written or ack.rows_received or chunk.chunk_rows
                self._run_store.record_chunk_success(
                    run_id=run_id,
                    chunk_index=chunk.chunk_index,
                    chunk_rows=chunk.chunk_rows,
                    chunk_bytes=chunk.chunk_bytes,
                    delivered_chunks=delivered_chunks,
                    delivered_rows=delivered_rows,
                )
                if on_progress is not None:
                    on_progress(f"\u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430 \u0434\u0430\u043d\u043d\u044b\u0445... {chunk.chunk_index}/{len(chunks)}")
        except Exception as exc:
            self._run_store.mark_failed(
                run_id=run_id,
                error_message=str(exc),
                delivered_chunks=delivered_chunks,
                delivered_rows=delivered_rows,
                total_duration_us=max(
                    result.duration_us,
                    max(0, (time.perf_counter_ns() - started_ns) // 1_000) + result.duration_us,
                ),
            )
            raise

        self._run_store.mark_completed(
            run_id=run_id,
            delivered_chunks=delivered_chunks,
            delivered_rows=delivered_rows,
            total_duration_us=max(
                result.duration_us,
                max(0, (time.perf_counter_ns() - started_ns) // 1_000) + result.duration_us,
            ),
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
                ack = parse_gas_ack(raw_body)
            except urllib.error.HTTPError as exc:
                http_status = getattr(exc, "code", None)
                raw_body = exc.read()
                body_preview = _preview_response_body(raw_body)
                try:
                    ack = parse_gas_ack(raw_body)
                except Exception:  # noqa: BLE001
                    last_exc = _ChunkDeliveryError(
                        _build_http_failure_message(http_status, body_preview),
                        cause_type=type(exc).__name__,
                        http_status=http_status,
                        http_body_preview=body_preview,
                    )
                    ack = None  # type: ignore[assignment]
                else:
                    if not ack.ok and not ack.retryable:
                        raise _ChunkDeliveryError(
                            _build_http_failure_message(http_status, body_preview),
                            cause_type=type(exc).__name__,
                            http_status=http_status,
                            http_body_preview=body_preview,
                            ack_message=ack.message,
                            error_code=ack.error_code,
                            ack_details=ack.details,
                        )
            except ValueError as exc:
                if "неожиданный status" in str(exc):
                    raise _ChunkDeliveryError(
                        str(exc),
                        cause_type="GasAckError",
                    ) from exc
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
        base_user_message = (
            build_user_delivery_error(
                delivered_chunks=delivered_chunks,
                total_chunks=total_chunks,
            )
            if delivered_chunks > 0
            else "Не удалось отправить данные в Google Таблицы"
        )
        user_message = base_user_message
        debug_context = {
            "url": self._url,
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
            actionable_message = _build_actionable_ack_message(cause)
            if actionable_message:
                if delivered_chunks == 0:
                    user_message = actionable_message
                else:
                    user_message = f"{base_user_message}: {actionable_message}"
            debug_context["http_status"] = cause.http_status
            debug_context["http_body_preview"] = cause.http_body_preview
            if cause.ack_message:
                debug_context["ack_message"] = cause.ack_message
            if cause.error_code:
                debug_context["error_code"] = cause.error_code
            if cause.ack_details:
                debug_context["ack_details"] = cause.ack_details
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
