# -*- coding: utf-8 -*-
"""Tests for extracted settings SQL presenter helpers."""

from app.config import SqlInstance
from app.ui.settings_sql_presenters import (
    build_database_items,
    build_instance_items,
    next_instance_index,
)


def _instance(host: str, name: str = "SQLEXPRESS") -> SqlInstance:
    return SqlInstance(name=name, host=host, display=f"{host}\\{name}")


def test_build_instance_items_restores_saved_instance_index() -> None:
    items, target_idx = build_instance_items(
        [_instance("server-a"), _instance("server-b")],
        saved_instance="server-b\\SQLEXPRESS",
    )

    assert [label for label, _ in items] == ["server-a\\SQLEXPRESS", "server-b\\SQLEXPRESS"]
    assert target_idx == 1


def test_build_database_items_keeps_restore_value_when_list_empty() -> None:
    items, final_idx = build_database_items([], restore="main_db")

    assert items == ["main_db"]
    assert final_idx == 0


def test_next_instance_index_advances_only_when_possible() -> None:
    assert next_instance_index(current_index=0, total_count=3) == 1
    assert next_instance_index(current_index=2, total_count=3) is None
