"""Pure data types used across layers.

All types in this package are free of Qt and DB-driver imports so the
core dataclasses / TypedDicts / enums can be consumed from any layer
(UI, workers, database, export) without pulling GUI or ODBC runtimes.

Currently re-exports from the legacy modules; the physical move to this
package is planned for the final wave of the audit-plan Stage 5.
"""

from __future__ import annotations

from app.domain.config_types import (
    AppConfig,
    ExportHistoryEntry,
    ExportJob,
    TriggerType,
)
from app.domain.constants import *  # noqa: F401,F403 - single source of truth
from app.domain.results import QueryResult, SqlInstance, SyncResult

__all__ = [
    "AppConfig",
    "ExportHistoryEntry",
    "ExportJob",
    "TriggerType",
    "QueryResult",
    "SqlInstance",
    "SyncResult",
]
