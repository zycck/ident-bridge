# -*- coding: utf-8 -*-
"""Tests for extracted SettingsWidget action helpers."""

from app.ui.settings_actions import apply_startup_toggle


def test_apply_startup_toggle_registers_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.ui.settings_actions.StartupManager.register", lambda: (True, ""))
    monkeypatch.setattr("app.ui.settings_actions.StartupManager.unregister", lambda: (False, "should-not-run"))
    monkeypatch.setattr("app.ui.settings_actions.StartupManager.is_registered", lambda: True)

    result = apply_startup_toggle(True)

    assert result.ok is True
    assert result.error == ""
    assert result.actual_enabled is True


def test_apply_startup_toggle_reports_failure_when_disable_fails(monkeypatch) -> None:
    monkeypatch.setattr("app.ui.settings_actions.StartupManager.register", lambda: (True, "should-not-run"))
    monkeypatch.setattr("app.ui.settings_actions.StartupManager.unregister", lambda: (False, "registry error"))
    monkeypatch.setattr("app.ui.settings_actions.StartupManager.is_registered", lambda: True)

    result = apply_startup_toggle(False)

    assert result.ok is False
    assert result.error == "registry error"
    assert result.actual_enabled is True
