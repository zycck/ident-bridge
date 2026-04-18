"""Concrete ExportSink implementations.

The package ships with legacy :class:`WebhookSink` plus the
Google Apps Script sink. The directory layout is intentional: adding
S3/Kafka/email later is a new file here plus a one-line registration in
:mod:`app.export.pipeline.resolve_export_sink`.
"""

from __future__ import annotations

from app.export.sinks.google_apps_script import GoogleAppsScriptSink
from app.export.sinks.webhook import WebhookSink

__all__ = ["GoogleAppsScriptSink", "WebhookSink"]
