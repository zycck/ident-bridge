"""Configuration TypedDicts + TriggerType enum.

Canonical home for the shapes of what the app persists / passes around.
For now re-exports the definitions still physically living in
:mod:`app.config`; the audit plan moves them here in the final wave of
Stage 5 while keeping the legacy module as a shim.
"""

from __future__ import annotations

from app.config import (
    AppConfig,
    ExportHistoryEntry,
    ExportJob,
    TriggerType,
)

__all__ = ["AppConfig", "ExportHistoryEntry", "ExportJob", "TriggerType"]
