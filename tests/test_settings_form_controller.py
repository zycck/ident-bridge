"""Tests for extracted SettingsWidget form persistence/orchestration."""

from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit

from app.config import AppConfig, ConfigManager
from app.ui.settings_form_controller import SettingsFormController
from app.ui.settings_sql_flow import SettingsSqlFlowState


def _build_controller(qtbot, tmp_config: ConfigManager, *, startup_enabled: bool = False):
    instance_combo = QComboBox()
    instance_combo.setEditable(True)
    db_combo = QComboBox()
    login_edit = QLineEdit()
    password_edit = QLineEdit()
    startup_check = QCheckBox()
    auto_update_check = QCheckBox()

    for widget in (
        instance_combo,
        db_combo,
        login_edit,
        password_edit,
        startup_check,
        auto_update_check,
    ):
        qtbot.addWidget(widget)

    selected_indices: list[int] = []
    flow = SettingsSqlFlowState()
    controller = SettingsFormController(
        config=tmp_config,
        flow=flow,
        instance_combo=instance_combo,
        db_combo=db_combo,
        login_edit=login_edit,
        password_edit=password_edit,
        startup_check=startup_check,
        auto_update_check=auto_update_check,
        github_repo="owner/repo",
        is_startup_enabled_fn=lambda: startup_enabled,
        on_instance_selected=lambda idx: selected_indices.append(idx),
    )
    return (
        controller,
        flow,
        selected_indices,
        instance_combo,
        db_combo,
        login_edit,
        password_edit,
        startup_check,
        auto_update_check,
    )


def test_load_fields_restores_saved_instance_and_flags(qtbot, tmp_config) -> None:
    tmp_config.save(AppConfig(
        sql_instance="server\\SQLEXPRESS",
        sql_database="main_db",
        sql_user="sa",
        sql_password="secret",
        auto_update_check=False,
    ))
    controller, flow, selected, instance_combo, _, login_edit, password_edit, startup_check, auto_update_check = _build_controller(
        qtbot,
        tmp_config,
        startup_enabled=True,
    )

    controller.load_fields()

    assert flow.loading is False
    assert login_edit.text() == "sa"
    assert password_edit.text() == "secret"
    assert flow.selected_database == "main_db"
    assert instance_combo.currentText() == "server\\SQLEXPRESS"
    assert selected == [0]
    assert startup_check.isChecked() is True
    assert auto_update_check.isChecked() is False


def test_handle_database_changed_tracks_selection_and_auto_saves(qtbot, tmp_config) -> None:
    controller, flow, _, instance_combo, db_combo, login_edit, password_edit, startup_check, auto_update_check = _build_controller(
        qtbot,
        tmp_config,
    )
    instance_combo.addItem("server\\SQLEXPRESS")
    db_combo.addItem("main_db")
    login_edit.setText("sa")
    password_edit.setText("secret")
    startup_check.setChecked(True)
    auto_update_check.setChecked(True)

    controller.handle_database_changed(0)
    cfg = tmp_config.load()

    assert flow.selected_database == "main_db"
    assert cfg["sql_database"] == "main_db"
    assert cfg["sql_instance"] == "server\\SQLEXPRESS"
    assert cfg["run_on_startup"] is True


def test_auto_save_skips_while_loading(qtbot, tmp_config) -> None:
    controller, flow, _, instance_combo, db_combo, login_edit, password_edit, _, auto_update_check = _build_controller(
        qtbot,
        tmp_config,
    )
    flow.begin_load()
    instance_combo.addItem("server\\SQLEXPRESS")
    db_combo.addItem("main_db")
    login_edit.setText("sa")
    password_edit.setText("secret")
    auto_update_check.setChecked(True)

    assert controller.auto_save() is False
    assert tmp_config.load() == {}


def test_auto_save_prefers_selected_database_over_placeholder_text(qtbot, tmp_config) -> None:
    controller, flow, _, instance_combo, db_combo, login_edit, password_edit, _, auto_update_check = _build_controller(
        qtbot,
        tmp_config,
    )
    instance_combo.addItem("server\\SQLEXPRESS")
    db_combo.addItem("Загрузка…")
    flow.remember_database_selection("db_from_state")
    login_edit.setText("sa")
    password_edit.setText("secret")
    auto_update_check.setChecked(True)

    assert controller.auto_save() is True
    assert tmp_config.load()["sql_database"] == "db_from_state"


def test_save_merges_existing_config_without_dropping_export_jobs(qtbot, tmp_config) -> None:
    tmp_config.save(AppConfig(
        sql_instance="old\\SQLEXPRESS",
        export_jobs=[{"id": "job-1", "name": "Nightly"}],
    ))
    controller, flow, _, instance_combo, db_combo, login_edit, password_edit, startup_check, auto_update_check = _build_controller(
        qtbot,
        tmp_config,
    )
    instance_combo.addItem("new\\SQLEXPRESS")
    db_combo.addItem("reporting")
    login_edit.setText("sa")
    password_edit.setText("secret")
    startup_check.setChecked(False)
    auto_update_check.setChecked(True)
    flow.remember_database_selection("reporting")

    controller.save()
    cfg = tmp_config.load()

    assert cfg["sql_instance"] == "new\\SQLEXPRESS"
    assert cfg["sql_database"] == "reporting"
    assert cfg["export_jobs"] == [{"id": "job-1", "name": "Nightly"}]
