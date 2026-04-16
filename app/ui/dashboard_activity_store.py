# -*- coding: utf-8 -*-
"""Pure helpers for dashboard activity/history mutations."""


def clear_job_histories(jobs: list[dict]) -> tuple[int, list[dict]]:
    total = 0
    cleared: list[dict] = []
    for job in jobs:
        copied = dict(job)
        history = list(job.get("history") or [])
        total += len(history)
        if "history" in copied:
            copied["history"] = []
        cleared.append(copied)
    return total, cleared

