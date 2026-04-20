"""Persistence helpers for ExportJobsWidget."""

import uuid
from collections.abc import Iterable, Mapping

from app.config import ConfigManager, ExportJob
from app.core.scheduler import ScheduleMode, schedule_mode_from_raw


def _normalize_gas_options(raw: object) -> dict[str, object]:
    source = raw if isinstance(raw, Mapping) else {}
    return {
        "sheet_name": str(source.get("sheet_name", "") or "").strip(),
        "auth_token": str(source.get("auth_token", "") or "").strip(),
    }


def _gas_target_key(job: Mapping[str, object]) -> tuple[str, str] | None:
    webhook_url = str(job.get("webhook_url", "") or "").strip()
    gas_options = job.get("gas_options")
    sheet_name = ""
    if isinstance(gas_options, Mapping):
        sheet_name = str(gas_options.get("sheet_name", "") or "").strip()
    if not webhook_url or not sheet_name:
        return None
    return webhook_url, sheet_name


def find_duplicate_export_target(jobs: Iterable[ExportJob]) -> tuple[str, str, str, str] | None:
    """Return the first pair of jobs that target the same webhook URL and sheet."""

    seen: dict[tuple[str, str], str] = {}
    for job in jobs:
        key = _gas_target_key(job)
        if key is None:
            continue
        previous_job_id = seen.get(key)
        if previous_job_id is not None and previous_job_id != job["id"]:
            return previous_job_id, job["id"], key[0], key[1]
        seen[key] = job["id"]
    return None


def job_from_raw(raw: Mapping[str, object]) -> ExportJob:
    """Normalize a raw config payload into the widget's job shape."""
    return ExportJob(
        id=str(raw.get("id") or uuid.uuid4()),
        name=str(raw.get("name", "") or ""),
        sql_query=str(raw.get("sql_query", "") or ""),
        webhook_url=str(raw.get("webhook_url", "") or ""),
        gas_options=_normalize_gas_options(raw.get("gas_options")),
        schedule_enabled=bool(raw.get("schedule_enabled", False)),
        schedule_mode=schedule_mode_from_raw(raw.get("schedule_mode", ScheduleMode.DAILY)).value,
        schedule_value=str(raw.get("schedule_value", "") or ""),
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
    cfg["export_jobs"] = list(jobs)
    config.save(cfg)


def new_export_job() -> ExportJob:
    return ExportJob(
        id=str(uuid.uuid4()),
        name="",
        sql_query="",
        webhook_url="",
        gas_options={
            "sheet_name": "",
            "auth_token": "",
        },
        schedule_enabled=False,
        schedule_mode=ScheduleMode.DAILY.value,
        schedule_value="",
        history=[],
    )
