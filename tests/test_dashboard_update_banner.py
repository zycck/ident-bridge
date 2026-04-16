# -*- coding: utf-8 -*-
"""Tests for extracted dashboard update banner widget."""

from PySide6.QtCore import Qt

from app.ui.dashboard_update_banner import DashboardUpdateBanner


def test_show_update_makes_banner_visible_and_updates_text(qtbot) -> None:
    banner = DashboardUpdateBanner()
    qtbot.addWidget(banner)

    banner.show_update("v1.2.3", "https://example.com/download")

    assert banner.isVisible() is True
    assert "v1.2.3" in banner.label_text()
    assert banner.update_url == "https://example.com/download"


def test_clicking_update_emits_requested_url(qtbot) -> None:
    banner = DashboardUpdateBanner()
    qtbot.addWidget(banner)
    banner.show_update("v1.2.3", "https://example.com/download")

    with qtbot.waitSignal(banner.update_requested, timeout=1000) as blocker:
        qtbot.mouseClick(banner.button(), Qt.MouseButton.LeftButton)

    assert blocker.args == ["https://example.com/download"]


def test_set_in_progress_only_updates_button_state(qtbot) -> None:
    banner = DashboardUpdateBanner()
    qtbot.addWidget(banner)
    banner.show_update("v1.2.3", "https://example.com/download")

    banner.set_in_progress(True)
    assert banner.button().isEnabled() is False
    assert banner.button().text() == "Загрузка…"
    assert banner.update_url == "https://example.com/download"

    banner.set_in_progress(False)
    assert banner.button().isEnabled() is True
    assert banner.button().text() == "Обновить"


def test_show_update_overwrites_previous_url_and_text(qtbot) -> None:
    banner = DashboardUpdateBanner()
    qtbot.addWidget(banner)
    banner.show_update("v1.0.0", "https://example.com/one")

    banner.show_update("v2.0.0", "https://example.com/two")

    assert "v2.0.0" in banner.label_text()
    assert banner.update_url == "https://example.com/two"
