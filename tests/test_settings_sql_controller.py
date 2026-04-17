"""Tests for extracted SettingsWidget SQL orchestration."""

from dataclasses import dataclass

from PySide6.QtWidgets import QComboBox, QLineEdit

from app.config import SqlInstance
from app.ui.settings_sql_controller import SettingsSqlController
from app.ui.settings_sql_flow import SettingsSqlFlowState
from app.ui.widgets import status_label


def _instance(host: str, name: str = "SQLEXPRESS") -> SqlInstance:
    return SqlInstance(name=name, host=host, display=f"{host}\\{name}")


@dataclass
class _FakeDatabaseListWorker:
    inst: SqlInstance
    user: str
    password: str


@dataclass
class _FakeTestConnectionWorker:
    cfg: dict


def _build_controller(qtbot, *, load_config=None):
    instance_combo = QComboBox()
    db_combo = QComboBox()
    login_edit = QLineEdit()
    password_edit = QLineEdit()
    conn_status = status_label()

    for widget in (instance_combo, db_combo, login_edit, password_edit, conn_status):
        qtbot.addWidget(widget)

    calls: list[dict] = []

    def fake_run_worker(parent, worker, **kwargs):
        pin_attr = kwargs.get("pin_attr")
        if pin_attr:
            setattr(parent, pin_attr, worker)
        calls.append({"parent": parent, "worker": worker, **kwargs})
        return object()

    controller = SettingsSqlController(
        instance_combo=instance_combo,
        db_combo=db_combo,
        login_edit=login_edit,
        password_edit=password_edit,
        conn_status=conn_status,
        flow=SettingsSqlFlowState(),
        load_config=load_config or (lambda: {}),
        run_worker_fn=fake_run_worker,
        scan_worker_factory=lambda: object(),
        database_list_worker_factory=lambda inst, user, password: _FakeDatabaseListWorker(
            inst=inst,
            user=user,
            password=password,
        ),
        test_connection_worker_factory=lambda cfg: _FakeTestConnectionWorker(cfg=cfg),
    )
    return controller, calls, instance_combo, db_combo, login_edit, password_edit, conn_status


def test_scan_instances_is_idempotent_while_running(qtbot) -> None:
    controller, calls, instance_combo, *_ = _build_controller(qtbot)

    assert controller.scan_instances() is True
    assert controller.scan_instances() is False

    assert len(calls) == 1
    assert instance_combo.currentText() == "Сканирование…"
    assert instance_combo.isEnabled() is False


def test_scan_success_restores_saved_instance_and_triggers_database_fetch(qtbot) -> None:
    saved_instance = _instance("server-b")
    controller, calls, instance_combo, db_combo, login_edit, password_edit, _ = _build_controller(
        qtbot,
        load_config=lambda: {
            "sql_instance": saved_instance.display,
            "sql_database": "main_db",
        },
    )
    login_edit.setText("sa")
    password_edit.setText("secret")

    controller.scan_instances()
    calls[0]["on_finished"]([_instance("server-a"), saved_instance])

    assert len(calls) == 2
    assert instance_combo.currentText() == saved_instance.display
    db_worker = calls[1]["worker"]
    assert db_worker.inst == saved_instance
    assert db_worker.user == "sa"
    assert db_combo.currentText() == "Загрузка…"
    assert db_combo.isEnabled() is False


def test_database_fetch_replays_pending_instance_after_finish(qtbot) -> None:
    controller, calls, instance_combo, *_ = _build_controller(qtbot)
    primary = _instance("server-a")
    secondary = _instance("server-b")
    instance_combo.addItem(primary.display, userData=primary)
    instance_combo.addItem(secondary.display, userData=secondary)

    assert controller.handle_instance_changed(0) is True
    assert controller.handle_instance_changed(1) is False

    assert len(calls) == 1
    calls[0]["on_finished"](["db1"])

    assert len(calls) == 2
    assert calls[1]["worker"].inst == secondary


def test_database_fetch_error_advances_to_next_instance(qtbot) -> None:
    controller, calls, instance_combo, _, _, _, conn_status = _build_controller(qtbot)
    primary = _instance("server-a")
    secondary = _instance("server-b")
    instance_combo.addItem(primary.display, userData=primary)
    instance_combo.addItem(secondary.display, userData=secondary)

    assert controller.handle_instance_changed(0) is True
    calls[0]["on_error"]("db list failed")

    assert conn_status.text() == "Список БД: db list failed"
    assert instance_combo.currentText() == secondary.display
    assert len(calls) == 2
    assert calls[1]["worker"].inst == secondary


def test_test_connection_resets_running_state_after_finish(qtbot) -> None:
    controller, calls, instance_combo, db_combo, login_edit, password_edit, conn_status = _build_controller(qtbot)
    instance_combo.addItem("server\\SQLEXPRESS")
    db_combo.addItem("main_db")
    login_edit.setText("sa")
    password_edit.setText("secret")

    assert controller.test_connection() is True
    assert controller.test_connection() is False

    assert conn_status.text() == "Проверка подключения…"
    assert len(calls) == 1
    assert calls[0]["worker"].cfg["sql_database"] == "main_db"

    calls[0]["on_finished"](False, "db down")

    assert conn_status.text() == "db down"
    assert controller.test_connection() is True
    assert len(calls) == 2


def test_scan_error_restores_combo_and_status(qtbot) -> None:
    controller, calls, instance_combo, _, _, _, conn_status = _build_controller(qtbot)

    controller.scan_instances()
    calls[0]["on_error"]("timeout")

    assert instance_combo.isEnabled() is True
    assert instance_combo.currentText() == "Ошибка сканирования"
    assert conn_status.text() == "Сканирование: timeout"
