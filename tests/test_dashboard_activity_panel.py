"""Tests for extracted dashboard activity/history panel."""

from PySide6.QtWidgets import QMessageBox

from app.ui.dashboard_activity_panel import DashboardActivityPanel


def _save_jobs(tmp_config, jobs: list[dict]) -> None:
    cfg = tmp_config.load()
    cfg["export_jobs"] = jobs
    tmp_config.save(cfg)


def test_activity_panel_refresh_tracks_aggregated_history_count(qtbot, tmp_config) -> None:
    _save_jobs(
        tmp_config,
        [
            {
                "name": "A",
                "history": [
                    {"ts": "2026-04-16 11:00:00", "ok": True, "rows": 2},
                    {"ts": "2026-04-16 10:00:00", "ok": False, "err": "boom"},
                ],
            },
            {
                "name": "B",
                "history": [{"ts": "2026-04-16 09:00:00", "ok": True, "rows": 1}],
            },
        ],
    )
    panel = DashboardActivityPanel(tmp_config)
    qtbot.addWidget(panel)

    panel.refresh_activity()

    assert panel.activity_count_text() == "3"


def test_activity_panel_clear_all_history_noops_when_empty(qtbot, tmp_config) -> None:
    _save_jobs(tmp_config, [{"name": "A", "history": []}])
    panel = DashboardActivityPanel(tmp_config)
    qtbot.addWidget(panel)

    assert panel.clear_all_history() is False
    assert tmp_config.load()["export_jobs"][0]["history"] == []


def test_activity_panel_clear_all_history_cancel_keeps_entries(
    monkeypatch,
    qtbot,
    tmp_config,
) -> None:
    _save_jobs(
        tmp_config,
        [{"name": "A", "history": [{"ts": "2026-04-16 11:00:00", "ok": True, "rows": 2}]}],
    )
    panel = DashboardActivityPanel(tmp_config)
    qtbot.addWidget(panel)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    assert panel.clear_all_history() is False
    assert len(tmp_config.load()["export_jobs"][0]["history"]) == 1


def test_activity_panel_clear_all_history_confirm_clears_entries(
    monkeypatch,
    qtbot,
    tmp_config,
) -> None:
    _save_jobs(
        tmp_config,
        [{"name": "A", "history": [{"ts": "2026-04-16 11:00:00", "ok": True, "rows": 2}]}],
    )
    panel = DashboardActivityPanel(tmp_config)
    qtbot.addWidget(panel)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    panel.refresh_activity()
    assert panel.activity_count_text() == "1"

    assert panel.clear_all_history() is True
    assert panel.activity_count_text() == "0"
    assert tmp_config.load()["export_jobs"][0]["history"] == []
