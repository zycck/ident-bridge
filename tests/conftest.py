# -*- coding: utf-8 -*-
"""
Shared pytest fixtures for the iDentBridge test suite.

All tests run under QT_QPA_PLATFORM=offscreen (set in qapp fixture) so
no GUI is shown. Use pytest-qt's `qtbot` fixture for signal-based waits.
"""
import os
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

# Ensure the project root is on sys.path so `import app...` works
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def _set_qt_platform() -> None:
    """Force offscreen platform before any QApplication import."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp_session() -> Iterator[Any]:
    """Session-wide QApplication instance.

    pytest-qt provides its own `qapp` fixture, but some tests need to
    construct QObjects before pytest-qt has a chance to spin one up.
    This guarantees there's always a QApplication available.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def tmp_config(monkeypatch, tmp_path):
    """ConfigManager pointed at a temporary directory.

    Each test gets its own empty config dir so saves don't pollute the
    user's real %APPDATA%\\iDentSync\\config.json.
    """
    monkeypatch.setattr("app.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("app.config.CONFIG_PATH", tmp_path / "config.json")
    from app.config import ConfigManager
    return ConfigManager()


@pytest.fixture
def mock_query_result():
    """Canned QueryResult for mock SQL clients to return."""
    from app.config import QueryResult
    return QueryResult(
        columns=["id", "name"],
        rows=[(1, "alice"), (2, "bob")],
        count=2,
        duration_ms=12,
    )


@pytest.fixture
def mock_sql_client(monkeypatch, mock_query_result):
    """
    Replace SqlClient inside app.workers.export_worker with a stub that
    returns canned results without touching a real database.

    Use this in tests that exercise the export pipeline.
    """
    class _MockSqlClient:
        instances: list["_MockSqlClient"] = []

        def __init__(self, cfg) -> None:
            self.cfg = cfg
            self.connected = False
            self.queries: list[str] = []
            _MockSqlClient.instances.append(self)

        def connect(self) -> None:
            self.connected = True

        def disconnect(self) -> None:
            self.connected = False

        def query(self, sql: str):
            self.queries.append(sql)
            return mock_query_result

    _MockSqlClient.instances.clear()
    monkeypatch.setattr("app.workers.export_worker.SqlClient", _MockSqlClient)
    return _MockSqlClient


@pytest.fixture
def mock_winreg(monkeypatch):
    """
    In-memory winreg replacement so app.core.startup tests run on any OS.

    Patches `app.core.startup.winreg` with a stub backed by a dict so the
    register/unregister/is_registered functions work without touching the
    real Windows registry. Returns the underlying dict so tests can assert
    its contents directly.
    """
    store: dict[str, str] = {}

    class _MockKey:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    class _MockReg:
        HKEY_CURRENT_USER = 0
        KEY_SET_VALUE = 0
        KEY_READ = 0
        REG_SZ = 1

        @staticmethod
        def OpenKey(*args, **kwargs):
            return _MockKey()

        @staticmethod
        def CreateKey(*args, **kwargs):
            return _MockKey()

        @staticmethod
        def SetValueEx(key, name, _reserved, _type, value):
            store[name] = value

        @staticmethod
        def QueryValueEx(key, name):
            if name not in store:
                raise FileNotFoundError(f"value not found: {name}")
            return (store[name], 1)

        @staticmethod
        def DeleteValue(key, name):
            store.pop(name, None)

    monkeypatch.setattr("app.core.startup.winreg", _MockReg, raising=False)
    return store


@pytest.fixture
def sample_export_job():
    """A typical ExportJob dict used by multiple tests."""
    from app.config import ExportJob
    return ExportJob(
        id="test-job-1",
        name="Test Job",
        sql_query="SELECT id, name FROM users WHERE active = 1",
        webhook_url="",
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],
    )
