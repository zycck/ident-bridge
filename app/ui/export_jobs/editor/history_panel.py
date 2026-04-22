"""History panel widget used by ExportJobEditor."""

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config import ExportHistoryEntry
from app.core.constants import HISTORY_MAX
from app.export.run_store import ExportRunInfo
from app.ui.history_row import HistoryRow
from app.ui.theme import Theme
from app.ui.widgets import hsep

_SAFE_RETRY_WRITE_MODES = {"replace_all", "replace_by_date_source"}


def _write_mode_label(write_mode: str) -> str:
    return {
        "replace_all": "заменить весь лист",
        "replace_by_date_source": "заменить срез по дате",
        "append": "дописать строки",
    }.get(write_mode, write_mode or "не указан")


def _status_title(status: str) -> tuple[str, str]:
    return {
        "planned": ("Не был запущен", Theme.info),
        "running": ("Оборвался во время отправки", Theme.warning),
        "failed": ("Завершился с ошибкой", Theme.error),
    }.get(status, ("Незавершённая выгрузка", Theme.warning))


def _status_note(run: ExportRunInfo) -> tuple[str, str]:
    messages: list[str] = []
    color = Theme.gray_500
    if run.last_error:
        messages.append(run.last_error)
        color = Theme.error
    if run.write_mode == "append" and run.total_chunks > 1:
        messages.append("Повтор этой выгрузки может создать дубли. Запускайте её вручную, если понимаете риск.")
        color = Theme.warning if color != Theme.error else color
    return "\n".join(messages), color


class _UnfinishedRunRow(QWidget):
    retry_requested = Signal(str)
    reset_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, run: ExportRunInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._run = run
        self._build_ui()

    def _build_ui(self) -> None:
        title, accent_color = _status_title(self._run.status)
        note_text, note_color = _status_note(self._run)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"_UnfinishedRunRow {{"
            f"  background-color: {Theme.surface_tinted};"
            f"  border: 1px solid {Theme.border};"
            f"  border-radius: {Theme.radius_md}px;"
            f"}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color: {accent_color};"
            f"font-size: {Theme.font_size_base}pt;"
            f"font-weight: {Theme.font_weight_semi};"
            f"background: transparent;"
        )
        top_row.addWidget(title_label)
        top_row.addStretch()

        if self._run.write_mode in _SAFE_RETRY_WRITE_MODES:
            retry_btn = self._action_button("Повторить заново")
            retry_btn.clicked.connect(lambda: self.retry_requested.emit(self._run.run_id))
            top_row.addWidget(retry_btn)

        reset_btn = self._action_button("Сбросить")
        reset_btn.clicked.connect(lambda: self.reset_requested.emit(self._run.run_id))
        top_row.addWidget(reset_btn)

        delete_btn = self._action_button("Удалить", danger=True)
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self._run.run_id))
        top_row.addWidget(delete_btn)

        root.addLayout(top_row)

        summary_label = QLabel(
            "Лист: "
            f"{self._run.sheet_name or '—'}"
            f" · режим: {_write_mode_label(self._run.write_mode)}"
            f" · чанки: {self._run.delivered_chunks}/{self._run.total_chunks}"
            f" · строки: {self._run.delivered_rows}/{self._run.total_rows}"
        )
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet(
            f"color: {Theme.gray_700};"
            f"font-size: {Theme.font_size_sm}pt;"
            f"background: transparent;"
        )
        root.addWidget(summary_label)

        if note_text:
            note_label = QLabel(note_text)
            note_label.setWordWrap(True)
            note_label.setStyleSheet(
                f"color: {note_color};"
                f"font-size: {Theme.font_size_sm}pt;"
                f"background: transparent;"
            )
            root.addWidget(note_label)

    def _action_button(self, text: str, *, danger: bool = False) -> QPushButton:
        button = QPushButton(text, self)
        hover_background = Theme.error_bg if danger else Theme.gray_50
        hover_color = Theme.error if danger else Theme.gray_900
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{"
            f"  min-height: 26px;"
            f"  padding: 4px 10px;"
            f"  border: 1px solid {Theme.border};"
            f"  border-radius: {Theme.radius}px;"
            f"  background-color: {Theme.surface};"
            f"  color: {Theme.gray_700};"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {hover_background};"
            f"  color: {hover_color};"
            f"  border-color: {Theme.border_strong};"
            f"}}"
        )
        return button


class ExportHistoryPanel(QWidget):
    """Owns export-job history and unfinished-run UI blocks."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[ExportHistoryEntry] = []
        self._unfinished_runs: list[ExportRunInfo] = []
        self._row_widgets: list[HistoryRow] = []
        self._unfinished_row_widgets: list[_UnfinishedRunRow] = []
        self._delete_handler = None
        self._clear_handler = None
        self._unfinished_retry_handler: Callable[[str], object] | None = None
        self._unfinished_reset_handler: Callable[[str], object] | None = None
        self._unfinished_delete_handler: Callable[[str], object] | None = None
        self._build_ui()
        self._update_chrome()

    def set_delete_handler(self, handler) -> None:
        self._delete_handler = handler

    def set_clear_handler(self, handler) -> None:
        self._clear_handler = handler

    def set_unfinished_retry_handler(self, handler) -> None:
        self._unfinished_retry_handler = handler

    def set_unfinished_reset_handler(self, handler) -> None:
        self._unfinished_reset_handler = handler

    def set_unfinished_delete_handler(self, handler) -> None:
        self._unfinished_delete_handler = handler

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._unfinished_sep = hsep()
        root.addSpacing(4)
        root.addWidget(self._unfinished_sep)
        root.addSpacing(4)

        self._unfinished_hdr_row = QWidget()
        self._unfinished_hdr_row.setStyleSheet("background: transparent;")
        unfinished_hdr_layout = QHBoxLayout(self._unfinished_hdr_row)
        unfinished_hdr_layout.setContentsMargins(0, 0, 0, 0)
        unfinished_hdr_layout.setSpacing(8)

        self._unfinished_hdr = QLabel("Незавершённые выгрузки")
        self._unfinished_hdr.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_base}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"background: transparent;"
        )
        unfinished_hdr_layout.addWidget(self._unfinished_hdr)
        unfinished_hdr_layout.addStretch()
        root.addWidget(self._unfinished_hdr_row)

        self._unfinished_container = QWidget()
        self._unfinished_container.setStyleSheet("background: transparent;")
        self._unfinished_layout = QVBoxLayout(self._unfinished_container)
        self._unfinished_layout.setContentsMargins(0, 0, 0, 0)
        self._unfinished_layout.setSpacing(6)
        root.addWidget(self._unfinished_container)

        self._hist_sep = hsep()
        root.addSpacing(8)
        root.addWidget(self._hist_sep)
        root.addSpacing(4)

        self._history_hdr_row = QWidget()
        self._history_hdr_row.setStyleSheet("background: transparent;")
        hdr_layout = QHBoxLayout(self._history_hdr_row)
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(8)

        self._history_hdr = QLabel("История")
        self._history_hdr.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_base}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"background: transparent;"
        )
        hdr_layout.addWidget(self._history_hdr)
        hdr_layout.addStretch()

        self._history_clear_btn = QPushButton("Очистить")
        self._history_clear_btn.setFlat(True)
        self._history_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_clear_btn.setStyleSheet(
            f"QPushButton {{"
            f"  border: none; background: transparent; padding: 0;"
            f"  color: {Theme.gray_500};"
            f"  text-decoration: underline;"
            f"}}"
            f"QPushButton:hover {{ color: {Theme.error}; }}"
        )
        self._history_clear_btn.clicked.connect(self._on_clear_history)
        hdr_layout.addWidget(self._history_clear_btn)

        root.addWidget(self._history_hdr_row)

        self._history_container = QWidget()
        self._history_container.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(2)

        self._history_scroll = QScrollArea()
        self._history_scroll.setWidget(self._history_container)
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._history_scroll.setMaximumHeight(280)
        self._history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._history_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        root.addWidget(self._history_scroll)

    def history(self) -> list[ExportHistoryEntry]:
        return list(self._history)

    def unfinished_runs(self) -> list[ExportRunInfo]:
        return list(self._unfinished_runs)

    def set_history(self, history: list[ExportHistoryEntry]) -> None:
        self._history = list(history)
        self._rebuild_history()

    def set_unfinished_runs(self, runs: list[ExportRunInfo]) -> None:
        self._unfinished_runs = list(runs)
        self._rebuild_unfinished()

    def prepend_entry(self, entry: ExportHistoryEntry) -> None:
        self._history.insert(0, entry)
        row = self._make_history_row(entry, 0)
        self._history_layout.insertWidget(0, row)
        self._row_widgets.insert(0, row)
        if len(self._history) > HISTORY_MAX:
            overflow = len(self._history) - HISTORY_MAX
            for _ in range(overflow):
                self._history.pop()
                old = self._row_widgets.pop()
                self._history_layout.removeWidget(old)
                old.deleteLater()
        self._reindex_rows()
        self._update_chrome()
        self.changed.emit()

    def latest_entry(self) -> ExportHistoryEntry | None:
        return self._history[0] if self._history else None

    @Slot(int)
    def _delete_history(self, index: int) -> None:
        if 0 <= index < len(self._history):
            entry = self._history.pop(index)
            row = self._row_widgets.pop(index)
            self._history_layout.removeWidget(row)
            row.deleteLater()
            run_id = str(entry.get("run_id", "") or "").strip()
            if run_id and callable(self._delete_handler):
                self._delete_handler(run_id)
            self._reindex_rows()
            self._update_chrome()
            self.changed.emit()

    @Slot()
    def _on_clear_history(self) -> None:
        if not self._history:
            return
        reply = QMessageBox.question(
            self,
            "Очистить историю",
            f"Удалить все записи истории ({len(self._history)})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._history.clear()
            if callable(self._clear_handler):
                self._clear_handler()
            self._rebuild_history()
            self.changed.emit()

    @Slot(str)
    def _retry_unfinished(self, run_id: str) -> None:
        if callable(self._unfinished_retry_handler):
            self._unfinished_retry_handler(run_id)

    @Slot(str)
    def _reset_unfinished(self, run_id: str) -> None:
        if callable(self._unfinished_reset_handler) and self._unfinished_reset_handler(run_id):
            self._remove_unfinished_run(run_id)
            self.changed.emit()

    @Slot(str)
    def _delete_unfinished(self, run_id: str) -> None:
        if callable(self._unfinished_delete_handler) and self._unfinished_delete_handler(run_id):
            self._remove_unfinished_run(run_id)
            self.changed.emit()

    def _make_history_row(self, entry: ExportHistoryEntry, index: int) -> HistoryRow:
        row = HistoryRow(entry, index, self)
        row.delete_requested.connect(self._delete_history)
        return row

    def _make_unfinished_row(self, run: ExportRunInfo) -> _UnfinishedRunRow:
        row = _UnfinishedRunRow(run, self)
        row.retry_requested.connect(self._retry_unfinished)
        row.reset_requested.connect(self._reset_unfinished)
        row.delete_requested.connect(self._delete_unfinished)
        return row

    def _remove_unfinished_run(self, run_id: str) -> None:
        self._unfinished_runs = [run for run in self._unfinished_runs if run.run_id != run_id]
        self._rebuild_unfinished()

    def _reindex_rows(self) -> None:
        for i, row in enumerate(self._row_widgets):
            row._index = i

    def _update_chrome(self) -> None:
        has_unfinished = bool(self._unfinished_runs)
        has_history = bool(self._history)
        self._unfinished_sep.setVisible(has_unfinished)
        self._unfinished_hdr_row.setVisible(has_unfinished)
        self._unfinished_container.setVisible(has_unfinished)
        if has_unfinished:
            self._unfinished_hdr.setText(f"Незавершённые выгрузки ({len(self._unfinished_runs)})")

        self._hist_sep.setVisible(has_history)
        self._history_hdr_row.setVisible(has_history)
        self._history_scroll.setVisible(has_history)
        if has_history:
            self._history_hdr.setText(f"История ({len(self._history)})")

    def _rebuild_history(self) -> None:
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._row_widgets = []

        for i, entry in enumerate(self._history):
            row = self._make_history_row(entry, i)
            self._history_layout.addWidget(row)
            self._row_widgets.append(row)
        self._update_chrome()

    def _rebuild_unfinished(self) -> None:
        while self._unfinished_layout.count():
            item = self._unfinished_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._unfinished_row_widgets = []

        for run in self._unfinished_runs:
            row = self._make_unfinished_row(run)
            self._unfinished_layout.addWidget(row)
            self._unfinished_row_widgets.append(row)
        self._update_chrome()
