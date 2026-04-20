"""Delivery transport and sink implementation for Google Apps Script."""

import json
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


def _build_actionable_ack_message(cause: "_ChunkDeliveryError") -> str:
    if cause.error_code == "UNAUTHORIZED":
        return "Доступ к обработчику запрещён. Проверьте публикацию проекта Apps Script и права доступа."

    if cause.error_code == "INVALID_REQUEST_METHOD":
        return "РђРґСЂРµСЃ РѕР±СЂР°Р±РѕС‚РєРё РЅР°СЃС‚СЂРѕРµРЅ РЅРµРІРµСЂРЅРѕ. РџСЂРѕРІРµСЂСЊС‚Рµ, С‡С‚Рѕ СѓРєР°Р·Р°РЅ Р°РґСЂРµСЃ РІРµР±-РїСЂРёР»РѕР¶РµРЅРёСЏ Apps Script."

    if cause.error_code == "MALFORMED_JSON":
        return (
            "РђРґСЂРµСЃ РѕР±СЂР°Р±РѕС‚РєРё РѕС‚РІРµС‚РёР» РЅРµРєРѕСЂСЂРµРєС‚РЅРѕ. РџСЂРѕРІРµСЂСЊС‚Рµ, С‡С‚Рѕ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ "
            "РѕРїСѓР±Р»РёРєРѕРІР°РЅРЅС‹Р№ Р°РґСЂРµСЃ РїСЂРѕРµРєС‚Р° Apps Script С‚Р°Р±Р»РёС†С‹."
        )

    if cause.error_code == "INVALID_ACTION":
        return "РђРґСЂРµСЃ РѕР±СЂР°Р±РѕС‚РєРё РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚ РѕР¶РёРґР°РµРјС‹Рµ РґРµР№СЃС‚РІРёСЏ. РџСЂРѕРІРµСЂСЊС‚Рµ, С‡С‚Рѕ СЂР°Р·РІРµСЂРЅСѓС‚Р° Р°РєС‚СѓР°Р»СЊРЅР°СЏ РІРµСЂСЃРёСЏ СЃРєСЂРёРїС‚Р°."

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


def _build_gas_get_url(url: str, *, action: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered_query = [(key, value) for key, value in query_items if key != "action"]
    filtered_query.append(("action", action))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(filtered_query),
            parsed.fragment,
        )
    )


@final
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
        self._url = str(os.environ.get("IDENTBRIDGE_GAS_DEV_URL", "") or "").strip() or url
        self._gas_options = gas_options
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
        export_date = datetime.now().date().isoformat()
        self._preflight_or_raise(run_id)

        try:
            chunks = plan_gas_chunks(
                job_name,
                result,
                run_id=run_id,
                max_rows_per_chunk=self._max_rows_per_chunk,
                max_payload_bytes=self._max_payload_bytes,
                gas_options=self._gas_options,
                export_date=export_date,
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
            if on_progress is not None:
                on_progress(f"Отправка данных... {chunk.chunk_index}/{len(chunks)}")

    def _preflight_or_raise(self, run_id: str) -> None:
        try:
            self._ping_backend()
        except Exception as exc:  # noqa: BLE001
            user_message = "Не удалось проверить адрес обработки Google Таблиц"
            if isinstance(exc, _ChunkDeliveryError):
                actionable = _build_actionable_ack_message(exc)
                if actionable:
                    user_message = actionable
            raise GoogleAppsScriptDeliveryError(
                user_message,
                run_id=run_id,
                delivered_chunks=0,
                delivered_rows=0,
                failed_chunk_index=1,
                debug_context={
                    "phase": "ping",
                    "url": self._url,
                    "error": str(exc),
                    "cause_type": getattr(exc, "cause_type", type(exc).__name__),
                    "ack_message": getattr(exc, "ack_message", ""),
                    "error_code": getattr(exc, "error_code", ""),
                    "ack_details": getattr(exc, "ack_details", {}),
                    "http_status": getattr(exc, "http_status", None),
                    "http_body_preview": getattr(exc, "http_body_preview", ""),
                },
            ) from exc

    def _ping_backend(self) -> None:
        req = urllib.request.Request(
            _build_gas_get_url(self._url, action="ping"),
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout, context=self._ssl) as resp:
                raw_body = resp.read()
        except urllib.error.HTTPError as exc:
            http_status = getattr(exc, "code", None)
            body_preview = _preview_response_body(exc.read())
            raise _ChunkDeliveryError(
                _build_http_failure_message(http_status, body_preview),
                cause_type=type(exc).__name__,
                http_status=http_status,
                http_body_preview=body_preview,
            ) from exc

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise _ChunkDeliveryError(
                "Ping вернул некорректный JSON",
                cause_type="PingError",
                http_body_preview=_preview_response_body(raw_body),
            ) from exc

        if not isinstance(payload, dict):
            raise _ChunkDeliveryError(
                "Ping вернул неожиданный формат ответа",
                cause_type="PingError",
                http_body_preview=_preview_response_body(raw_body),
            )

        if bool(payload.get("ok")):
            return

        raise _ChunkDeliveryError(
            str(payload.get("message", "") or payload.get("error_code", "") or "Ping rejected").strip(),
            cause_type="GasAckError",
            ack_message=str(payload.get("message", "") or "").strip(),
            error_code=str(payload.get("error_code", "") or "").strip(),
            ack_details=payload.get("details") if isinstance(payload.get("details"), dict) else None,
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
