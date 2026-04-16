# -*- coding: utf-8 -*-
"""Tests for extracted dashboard status cards widget."""

from datetime import datetime

from app.config import SyncResult
from app.ui.dashboard_status_cards import DashboardStatusCards
from app.ui.theme import Theme


def _sync_result(rows: int = 42) -> SyncResult:
    return SyncResult(
        success=True,
        rows_synced=rows,
        error=None,
        timestamp=datetime(2026, 4, 16, 9, 30, 45),
    )


def test_status_cards_start_with_expected_defaults(qtbot) -> None:
    cards = DashboardStatusCards()
    qtbot.addWidget(cards)

    assert cards.connection_label_text() == "Проверка..."
    assert cards.last_sync_text() == "Никогда"


def test_status_cards_set_connected_updates_label_and_color(qtbot) -> None:
    cards = DashboardStatusCards()
    qtbot.addWidget(cards)

    cards.set_connected(None)
    assert cards.connection_label_text() == "Не настроено"
    assert Theme.gray_400 in cards.connection_label_style()

    cards.set_connected(True)
    assert cards.connection_label_text() == "Подключено"
    assert Theme.success in cards.connection_label_style()

    cards.set_connected(False)
    assert cards.connection_label_text() == "Нет связи"
    assert Theme.error in cards.connection_label_style()


def test_status_cards_update_last_sync_formats_timestamp_and_rows(qtbot) -> None:
    cards = DashboardStatusCards()
    qtbot.addWidget(cards)

    cards.update_last_sync(_sync_result(17))

    assert cards.last_sync_text() == "09:30:45  16.04  ·  17 стр."
