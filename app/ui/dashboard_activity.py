# -*- coding: utf-8 -*-

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.ui.history_row import HistoryRow
from app.ui.theme import Theme

_EMPTY_ACTIVITY_TEXT = "Нет запусков. Запустите выгрузку на вкладке «Выгрузки»."


def refresh_dashboard_activity(
    layout: QVBoxLayout,
    parent: QWidget,
    jobs: Iterable[dict],
) -> int:
    """Rebuild the activity list from export jobs and return rendered row count."""
    all_entries: list[tuple[dict, str]] = []
    for job in jobs:
        job_name = job.get("name", "") or "(без названия)"
        for entry in (job.get("history") or []):
            all_entries.append((entry, job_name))

    # Sort by ts desc; string ordering works because the persisted timestamp
    # format is YYYY-MM-DD HH:MM[:SS].
    all_entries.sort(key=lambda x: x[0].get("ts", ""), reverse=True)
    all_entries = all_entries[:100]

    _clear_layout(layout)

    if not all_entries:
        layout.addWidget(_make_empty_state_label())
        return 0

    for i, (entry, job_name) in enumerate(all_entries):
        row = HistoryRow(entry, i, parent, job_name=job_name, show_delete=False)
        layout.addWidget(row)
    layout.addStretch()
    return len(all_entries)


def _clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item and item.widget():
            item.widget().deleteLater()


def _make_empty_state_label() -> QLabel:
    label = QLabel(_EMPTY_ACTIVITY_TEXT)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        f"color: {Theme.gray_400}; "
        f"font-size: {Theme.font_size_sm}pt; "
        f"padding: 24px 0;"
    )
    return label


def clear_job_histories(jobs: list[dict]) -> tuple[int, list[dict]]:
    """Return (cleared_total_entries, jobs-with-empty-history).

    Pure helper — no Qt, no config mutation. Used by the dashboard's
    "Очистить историю" action before persisting the cleared jobs back
    into config.
    """
    total = 0
    cleared: list[dict] = []
    for job in jobs:
        copied = dict(job)
        history = list(job.get("history") or [])
        total += len(history)
        if "history" in copied:
            copied["history"] = []
        cleared.append(copied)
    return total, cleared
