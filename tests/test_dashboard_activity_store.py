# -*- coding: utf-8 -*-
"""Tests for the clear_job_histories helper (now living in
app.ui.dashboard_activity after audit A-2 merge)."""

from app.ui.dashboard_activity import clear_job_histories


def test_clear_job_histories_returns_total_and_preserves_other_fields() -> None:
    jobs = [
        {
            "id": "a",
            "name": "Orders",
            "history": [
                {"ts": "2026-04-16 12:00:00", "ok": True, "rows": 2},
                {"ts": "2026-04-16 11:00:00", "ok": False, "err": "boom"},
            ],
            "webhook_url": "https://example.com",
        },
        {
            "id": "b",
            "name": "Users",
            "history": [{"ts": "2026-04-16 10:00:00", "ok": True, "rows": 1}],
            "schedule_enabled": True,
        },
    ]

    total, cleared = clear_job_histories(jobs)

    assert total == 3
    assert cleared == [
        {
            "id": "a",
            "name": "Orders",
            "history": [],
            "webhook_url": "https://example.com",
        },
        {
            "id": "b",
            "name": "Users",
            "history": [],
            "schedule_enabled": True,
        },
    ]


def test_clear_job_histories_handles_missing_history_keys() -> None:
    jobs = [
        {"id": "a", "name": "Orders"},
        {"id": "b", "name": "Users", "history": []},
    ]

    total, cleared = clear_job_histories(jobs)

    assert total == 0
    assert cleared == [
        {"id": "a", "name": "Orders"},
        {"id": "b", "name": "Users", "history": []},
    ]
