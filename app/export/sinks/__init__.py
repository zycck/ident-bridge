"""Concrete ExportSink implementations.

The package ships with a single sink — :class:`WebhookSink` — but the
directory layout is intentional: adding S3/Kafka/email later is a new
file here plus a one-line registration in
:mod:`app.export.pipeline.build_pipeline_for_job`.
"""

from __future__ import annotations

from app.export.sinks.webhook import WebhookSink

__all__ = ["WebhookSink"]
