# -*- coding: utf-8 -*-
"""Tests for app.core.odbc_utils."""
from __future__ import annotations

import pytest

from app.core import odbc_utils


class _FakePyodbc:
    def __init__(self, drivers: list[str]) -> None:
        self._drivers = drivers

    def drivers(self) -> list[str]:
        return self._drivers


def test_best_driver_prefers_first_available_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        odbc_utils,
        "pyodbc",
        _FakePyodbc([
            "SQL Server Native Client 11.0",
            "ODBC Driver 18 for SQL Server",
        ]),
    )

    assert odbc_utils.best_driver() == "ODBC Driver 18 for SQL Server"


def test_best_driver_reports_missing_pyodbc(monkeypatch) -> None:
    monkeypatch.setattr(odbc_utils, "pyodbc", None)
    monkeypatch.setattr(
        odbc_utils,
        "_PYODBC_IMPORT_ERROR",
        ImportError("libodbc.so.2 missing"),
    )

    with pytest.raises(RuntimeError, match="pyodbc is not available"):
        odbc_utils.best_driver()


def test_best_driver_reports_empty_driver_list(monkeypatch) -> None:
    monkeypatch.setattr(odbc_utils, "pyodbc", _FakePyodbc([]))

    with pytest.raises(RuntimeError, match="Не найден подходящий ODBC-драйвер"):
        odbc_utils.best_driver()
