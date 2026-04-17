"""Tests for extracted dashboard shell/composite layout."""

from app.ui.dashboard_activity_panel import DashboardActivityPanel
from app.ui.dashboard_shell import DashboardShell
from app.ui.dashboard_status_cards import DashboardStatusCards
from app.ui.dashboard_update_banner import DashboardUpdateBanner


def test_dashboard_shell_exposes_expected_sections(qtbot, tmp_config) -> None:
    shell = DashboardShell(tmp_config)
    qtbot.addWidget(shell)

    assert isinstance(shell.status_cards(), DashboardStatusCards)
    assert isinstance(shell.update_banner(), DashboardUpdateBanner)
    assert isinstance(shell.activity_panel(), DashboardActivityPanel)


def test_dashboard_shell_forwards_update_banner_signal(qtbot, tmp_config) -> None:
    shell = DashboardShell(tmp_config)
    qtbot.addWidget(shell)

    shell.update_banner().show_update("v1.2.3", "https://example.com/download")

    with qtbot.waitSignal(shell.update_requested, timeout=1000) as blocker:
        shell.update_banner().button().click()

    assert blocker.args == ["https://example.com/download"]
