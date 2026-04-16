# -*- coding: utf-8 -*-
"""Tests for extracted Settings SQL view adapter."""

from PySide6.QtWidgets import QComboBox

from app.config import SqlInstance
from app.ui.settings_sql_view import SettingsSqlView
from app.ui.widgets import status_label


def _instance(host: str, name: str = "SQLEXPRESS") -> SqlInstance:
    return SqlInstance(name=name, host=host, display=f"{host}\\{name}")


def test_settings_sql_view_handles_scan_states(qtbot) -> None:
    instance_combo = QComboBox()
    db_combo = QComboBox()
    conn_status = status_label()
    for widget in (instance_combo, db_combo, conn_status):
        qtbot.addWidget(widget)
    view = SettingsSqlView(
        instance_combo=instance_combo,
        db_combo=db_combo,
        conn_status=conn_status,
    )

    view.show_scan_in_progress()
    assert instance_combo.currentText() == "Сканирование…"
    assert instance_combo.isEnabled() is False

    target_idx = view.populate_instances([_instance("a"), _instance("b")], saved_instance="b\\SQLEXPRESS")
    assert instance_combo.isEnabled() is True
    assert instance_combo.count() == 2
    assert target_idx == 1

    view.show_scan_error("timeout")
    assert instance_combo.currentText() == "Ошибка сканирования"
    assert conn_status.text() == "Сканирование: timeout"


def test_settings_sql_view_handles_database_list_states(qtbot) -> None:
    instance_combo = QComboBox()
    db_combo = QComboBox()
    conn_status = status_label()
    for widget in (instance_combo, db_combo, conn_status):
        qtbot.addWidget(widget)
    view = SettingsSqlView(
        instance_combo=instance_combo,
        db_combo=db_combo,
        conn_status=conn_status,
    )

    view.show_databases_loading()
    assert db_combo.currentText() == "Загрузка…"
    assert db_combo.isEnabled() is False

    idx = view.populate_databases(["main", "archive"], restore="archive")
    assert db_combo.isEnabled() is True
    assert db_combo.count() == 2
    assert idx == 1
    assert db_combo.currentText() == "archive"

    view.show_database_error("db list failed")
    assert conn_status.text() == "Список БД: db list failed"
    assert db_combo.count() == 0


def test_settings_sql_view_supports_empty_instance_and_database_lists(qtbot) -> None:
    instance_combo = QComboBox()
    db_combo = QComboBox()
    conn_status = status_label()
    for widget in (instance_combo, db_combo, conn_status):
        qtbot.addWidget(widget)
    view = SettingsSqlView(
        instance_combo=instance_combo,
        db_combo=db_combo,
        conn_status=conn_status,
    )

    assert view.populate_instances([], saved_instance="") is None
    assert instance_combo.currentText() == "Нет экземпляров"

    idx = view.populate_databases([], restore="fallback_db")
    assert idx == 0
    assert db_combo.currentText() == "fallback_db"
