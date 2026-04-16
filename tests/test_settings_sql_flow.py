# -*- coding: utf-8 -*-
"""Tests for extracted SettingsWidget SQL flow state."""

from app.config import SqlInstance
from app.ui.settings_sql_flow import SettingsSqlFlowState


def _instance(name: str) -> SqlInstance:
    return SqlInstance(name="SQLEXPRESS", host=name, display=f"{name}\\SQLEXPRESS")


def test_database_fetch_queues_pending_instance_when_busy() -> None:
    flow = SettingsSqlFlowState()

    assert flow.begin_database_fetch(_instance("primary")) is True
    assert flow.begin_database_fetch(_instance("secondary")) is False
    assert flow.pending_database_instance == _instance("secondary")


def test_finish_database_fetch_returns_restore_value_and_pending() -> None:
    flow = SettingsSqlFlowState()
    flow.remember_loaded_database("saved_db")
    flow.begin_database_fetch(_instance("primary"))
    flow.begin_database_fetch(_instance("secondary"))

    restore, pending = flow.finish_database_fetch(saved_database="")

    assert restore == "saved_db"
    assert pending == _instance("secondary")
    assert flow.pending_database_instance is None


def test_loading_and_connection_test_flags_roundtrip() -> None:
    flow = SettingsSqlFlowState()

    flow.begin_load()
    assert flow.loading is True
    assert flow.should_skip_autosave() is True
    flow.end_load()
    assert flow.loading is False

    assert flow.begin_connection_test() is True
    assert flow.begin_connection_test() is False
    flow.finish_connection_test()
    assert flow.begin_connection_test() is True


def test_remember_database_selection_ignores_placeholder_text() -> None:
    flow = SettingsSqlFlowState()

    flow.remember_database_selection("Загрузка…")
    flow.remember_database_selection("main_db")

    assert flow.selected_database == "main_db"
