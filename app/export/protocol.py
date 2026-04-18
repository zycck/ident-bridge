"""Protocol contract for anything that can receive an export result.

A sink is anything with:

* a string ``name`` (used for logging and future selection/registry),
* a ``push(job_name, result, *, on_progress=None)`` method that does
  whatever I/O the sink needs and raises on failure.

Marking the protocol ``runtime_checkable`` lets tests assert structural
conformance without forcing inheritance.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from app.config import QueryResult


@runtime_checkable
class ExportSink(Protocol):
    """Receiver of a query result.

    Implementations:
    - :class:`app.export.sinks.webhook.WebhookSink` — POSTs JSON.
    - (future) S3, Kafka, email digest, file drop, etc.
    """

    name: str

    def push(
        self,
        job_name: str,
        result: QueryResult,
        *,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        """Deliver ``result`` to the sink. Raise on failure."""
        ...


__all__ = ["ExportSink"]
