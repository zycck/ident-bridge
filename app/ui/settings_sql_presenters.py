# -*- coding: utf-8 -*-
"""Presentation helpers for SettingsWidget SQL lists."""

from app.config import SqlInstance


def build_instance_items(
    instances: list[SqlInstance],
    *,
    saved_instance: str,
) -> tuple[list[tuple[str, SqlInstance]], int]:
    items = [(inst.display, inst) for inst in instances]
    target_idx = 0
    if saved_instance:
        for idx, (label, _inst) in enumerate(items):
            if label == saved_instance:
                target_idx = idx
                break
    return items, target_idx


def build_database_items(
    databases: list[str],
    *,
    restore: str,
) -> tuple[list[str], int]:
    if not databases:
        return ([restore] if restore else []), 0
    final_idx = 0
    if restore:
        for idx, db in enumerate(databases):
            if db == restore:
                final_idx = idx
                break
    return list(databases), final_idx


def next_instance_index(*, current_index: int, total_count: int) -> int | None:
    nxt = current_index + 1
    if nxt < total_count:
        return nxt
    return None
