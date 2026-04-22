"""Tests for short export job identifiers."""

import json

from app.config import generate_export_job_id

_SHORT_JOB_ID_ALPHABET = set("abcdefghijklmnopqrstuvwxyz234567")


def _is_short_job_id(value: str) -> bool:
    return len(value) == 12 and set(value) <= _SHORT_JOB_ID_ALPHABET


def test_generate_export_job_id_returns_short_base32_token() -> None:
    value = generate_export_job_id()

    assert _is_short_job_id(value)


def test_config_manager_keeps_existing_export_job_id(tmp_config, tmp_path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "export_jobs": [
                    {
                        "id": "job-legacy-1",
                        "name": "Nightly",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cfg = tmp_config.load()
    jobs = cfg.get("export_jobs") or []

    assert jobs[0]["id"] == "job-legacy-1"


def test_config_manager_generates_short_export_job_id_for_missing_identity(tmp_config, tmp_path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "export_jobs": [
                    {
                        "sql_query": "SELECT 1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cfg = tmp_config.load()
    jobs = cfg.get("export_jobs") or []

    assert _is_short_job_id(jobs[0]["id"])
    assert jobs[0]["name"] == ""
