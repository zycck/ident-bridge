"""POST the query result as JSON to a user-configured HTTP(S) endpoint.

Implements :class:`~app.export.protocol.ExportSink` for plain webhooks
(Slack/Discord/n8n/custom). Everything non-trivial lives here so the
worker can stay dumb and swap sinks without a branch per type.

Design choices:
- One module-level :class:`ssl.SSLContext` (mirrors app.core.updater and
  the previous inline ExportWorker usage). Predictable TLS policy, easy
  future pinning.
- Exponential backoff between retries with a configurable base delay
  (env var ``IDENTBRIDGE_WEBHOOK_RETRY_DELAY`` honours legacy behaviour).
- :class:`_SqlJSONEncoder` explicitly handles the types pyodbc actually
  yields (Decimal, datetime.date/datetime/time, bytes, memoryview, UUID,
  Enum) so we don't pay ``default=str`` ``repr()`` cost on every cell.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import enum
import json
import logging
import os
import ssl
import time
import urllib.request
import uuid
from typing import Any

from app.config import QueryResult

_log = logging.getLogger(__name__)

DEFAULT_RETRY_ATTEMPTS: int = 3
DEFAULT_RETRY_BASE_DELAY: float = float(
    os.environ.get("IDENTBRIDGE_WEBHOOK_RETRY_DELAY", "2.0")
)
DEFAULT_TIMEOUT: float = 15.0

_SSL_CONTEXT = ssl.create_default_context()


class _SqlJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles the types pyodbc rows typically contain."""

    def default(self, o: Any) -> Any:  # noqa: D401 - std method
        if isinstance(o, decimal.Decimal):
            # Decimal — emit as string to preserve precision (JSON numbers
            # would silently widen or round through float).
            return str(o)
        if isinstance(o, (_dt.datetime, _dt.date, _dt.time)):
            return o.isoformat()
        if isinstance(o, _dt.timedelta):
            return o.total_seconds()
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, (bytes, bytearray, memoryview)):
            return bytes(o).hex()
        if isinstance(o, enum.Enum):
            return o.value
        return super().default(o)


def build_webhook_payload(job_name: str, result: QueryResult) -> bytes:
    """Serialize one webhook payload without pre-copying all result rows.

    Kept as a module-level function (in addition to :meth:`WebhookSink._serialize`)
    because existing callers in tests + legacy code import it directly.
    """
    return json.dumps(
        {
            "job": job_name,
            "rows": result.count,
            "columns": result.columns,
            "data": result.rows,
        },
        ensure_ascii=False,
        cls=_SqlJSONEncoder,
    ).encode("utf-8")


class WebhookSink:
    """POST a :class:`QueryResult` as JSON to an HTTP(S) endpoint.

    Retries on transient failures with exponential backoff. On terminal
    failure re-raises the last exception so the caller can mark the run
    as failed and surface the error.
    """

    name = "webhook"

    def __init__(
        self,
        url: str,
        *,
        max_rows: int | None = None,
        retries: int = DEFAULT_RETRY_ATTEMPTS,
        base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._url = url
        self._max_rows = max_rows
        self._retries = max(1, retries)
        self._base_delay = base_delay
        self._timeout = timeout
        self._ssl = ssl_context or _SSL_CONTEXT

    # ------------------------------------------------------------------

    def push(
        self,
        job_name: str,
        result: QueryResult,
        *,
        on_progress=None,
    ) -> None:
        if self._max_rows is not None and result.count > self._max_rows:
            msg = (
                f"Слишком много строк для webhook ({result.count} > "
                f"{self._max_rows}). Сократите запрос."
            )
            _log.error(msg)
            raise ValueError(msg)

        payload = self._serialize(job_name, result)
        self._post_with_retries(payload, job_name, result.count)

    # ------------------------------------------------------------------

    def _serialize(self, job_name: str, result: QueryResult) -> bytes:
        return build_webhook_payload(job_name, result)

    def _post_with_retries(self, payload: bytes, job_name: str, row_count: int) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                req = urllib.request.Request(
                    self._url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "User-Agent":   "iDentBridge",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(
                    req, timeout=self._timeout, context=self._ssl,
                ) as resp:
                    _log.info(
                        "Webhook %s → HTTP %d (attempt %d)",
                        self._url, resp.status, attempt,
                    )
                    last_exc = None
                    break
            except Exception as exc:
                last_exc = exc
                _log.warning(
                    "Webhook attempt %d/%d failed: %s",
                    attempt, self._retries, exc,
                )
                if attempt < self._retries:
                    time.sleep(self._base_delay * (2 ** (attempt - 1)))
        if last_exc is not None:
            _log.error(
                "Webhook push failed after %d attempts: %s",
                self._retries, last_exc,
            )
            raise last_exc
        _log.info(
            "Выгрузка '%s': %d строк → webhook %s",
            job_name, row_count, self._url,
        )


__all__ = ["WebhookSink", "build_webhook_payload", "DEFAULT_RETRY_ATTEMPTS",
           "DEFAULT_RETRY_BASE_DELAY", "DEFAULT_TIMEOUT"]
