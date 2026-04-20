"""Persistence helpers for ExportJobsWidget."""

import uuid
from collections.abc import Iterable, Mapping

from app.config import ConfigManager, ExportJob


def _normalize_gas_options(raw: object) -> dict[str, object]:
    source = raw if isinstance(raw, Mapping) else {}
    header_row = source.get("header_row", 1)
    try:
        normalized_header_row = max(1, int(header_row))
    except (TypeError, ValueError):
        normalized_header_row = 1
    dedupe_columns = source.get("dedupe_key_columns") or []
    return {
        "sheet_name": str(source.get("sheet_name", "") or ""),
        "header_row": normalized_header_row,
        "dedupe_key_columns": [
            str(column).strip()
            for column in dedupe_columns
            if str(column).strip()
        ],
    }


def job_from_raw(raw: Mapping[str, object]) -> ExportJob:
    """Normalize a raw config payload into the widget's job shape."""
    return ExportJob(
        id=str(raw.get("id", str(uuid.uuid4()))),
        name=str(raw.get("name", "")),
        sql_query=str(raw.get("sql_query", "")),
        webhook_url=str(raw.get("webhook_url", "")),
        gas_options=_normalize_gas_options(raw.get("gas_options")),
        schedule_enabled=bool(raw.get("schedule_enabled", False)),
        schedule_mode=str(raw.get("schedule_mode", "daily")),
        schedule_value=str(raw.get("schedule_value", "")),
        history=list(raw.get("history") or []),  # type: ignore[typeddict-item]
    )


def load_export_jobs(config: ConfigManager) -> list[ExportJob]:
    cfg = config.load()
    raw_jobs = cfg.get("export_jobs") or []
    return [job_from_raw(raw) for raw in raw_jobs]


def persist_export_jobs(
    config: ConfigManager,
    jobs: Iterable[ExportJob],
) -> None:
    cfg = config.load()
    cfg["export_jobs"] = list(jobs)  # type: ignore[typeddict-unknown-key]
    config.save(cfg)


def new_export_job() -> ExportJob:
    return ExportJob(
        id=str(uuid.uuid4()),
        name="",
        sql_query="",
        webhook_url="",
        gas_options={
            "sheet_name": "",
            "header_row": 1,
            "dedupe_key_columns": [],
        },
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],  # type: ignore[typeddict-unknown-key]
    )
