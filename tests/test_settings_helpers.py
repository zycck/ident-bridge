# -*- coding: utf-8 -*-
"""Tests for extracted SettingsWidget helpers."""

from app.ui.settings_persistence import (
    build_connection_config,
    build_settings_payload,
    resolve_autosave_database,
)
from app.ui.settings_workers import instance_from_text


def test_instance_from_text_parses_host_and_name() -> None:
    instance = instance_from_text("server\\SQLEXPRESS")

    assert instance is not None
    assert instance.host == "server"
    assert instance.name == "SQLEXPRESS"
    assert instance.display == "server\\SQLEXPRESS"


def test_instance_from_text_ignores_placeholder_values() -> None:
    assert instance_from_text("Сканирование…") is None
    assert instance_from_text("Нет экземпляров") is None
    assert instance_from_text("Ошибка сканирования") is None


def test_resolve_autosave_database_prefers_real_database_name() -> None:
    assert resolve_autosave_database("db_from_state", "Загрузка…") == "db_from_state"
    assert resolve_autosave_database("", "main_db") == "main_db"
    assert resolve_autosave_database("", "Нет баз данных") == ""


def test_build_settings_payload_helpers_return_expected_keys() -> None:
    connection_cfg = build_connection_config(
        sql_instance="server\\SQLEXPRESS",
        sql_database="db1",
        sql_user="sa",
        sql_password="secret",
    )
    settings_cfg = build_settings_payload(
        sql_instance="server\\SQLEXPRESS",
        sql_database="db1",
        sql_user="sa",
        sql_password="secret",
        auto_update_check=True,
        run_on_startup=False,
        github_repo="owner/repo",
    )

    assert connection_cfg == {
        "sql_instance": "server\\SQLEXPRESS",
        "sql_database": "db1",
        "sql_user": "sa",
        "sql_password": "secret",
    }
    assert settings_cfg["auto_update_check"] is True
    assert settings_cfg["run_on_startup"] is False
    assert settings_cfg["github_repo"] == "owner/repo"
