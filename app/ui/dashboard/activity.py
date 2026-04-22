from collections.abc import Iterable, Mapping
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.config import ExportHistoryEntry
from app.ui.history_row import HistoryRow
from app.ui.theme import Theme

_EMPTY_ACTIVITY_TEXT = "Нет запусков. Запустите выгрузку на вкладке «Выгрузки»."


def refresh_dashboard_activity(
    layout: QVBoxLayout,
    parent: QWidget,
    jobs: Iterable[Mapping[str, object]],
) -> int:
    """Rebuild the activity list from export jobs and return rendered row count."""

    entries: list[tuple[ExportHistoryEntry, str]] = []
    for job in jobs:
        job_name = str(job.get("name", "") or "(без названия)")
        for entry in job.get("history") or []:
            entries.append((cast(ExportHistoryEntry, entry), job_name))
    return refresh_dashboard_activity_entries(layout, parent, entries)


def refresh_dashboard_activity_entries(
    layout: QVBoxLayout,
    parent: QWidget,
    entries: Iterable[tuple[ExportHistoryEntry, str]],
) -> int:
    """Rebuild the activity list from pre-aggregated history entries."""

    all_entries = list(entries)
    all_entries.sort(key=lambda item: item[0].get("ts", ""), reverse=True)
    all_entries = all_entries[:100]

    _clear_layout(layout)

    if not all_entries:
        layout.addWidget(_make_empty_state_label())
        return 0

    for index, (entry, job_name) in enumerate(all_entries):
        row = HistoryRow(entry, index, parent, job_name=job_name, show_delete=False)
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


def clear_job_histories(jobs: list[Mapping[str, object]]) -> tuple[int, list[dict[str, object]]]:
    """Compatibility helper used by older call sites and tests."""

    total = 0
    cleared: list[dict[str, object]] = []
    for job in jobs:
        copied = dict(job)
        if "history" in copied:
            history = list(job.get("history") or [])
            total += len(history)
            copied["history"] = []
        cleared.append(copied)
    return total, cleared
