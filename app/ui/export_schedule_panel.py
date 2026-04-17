"""Schedule controls for ExportJobEditor."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.core.scheduler import SUPPORTED_SCHEDULE_MODES
from app.ui.theme import Theme
from app.ui.widgets import HeaderLabel, style_combo_popup

SCHEDULE_MODE_BY_INDEX: tuple[str, ...] = SUPPORTED_SCHEDULE_MODES
_PLACEHOLDERS: dict[int, str] = {
    0: "ЧЧ:ММ",
    1: "N часов",
    2: "N минут",
    3: "N секунд",
}


class ExportSchedulePanel(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(HeaderLabel("Расписание"))

        self._sched_check = QCheckBox("Запускать автоматически")
        self._sched_check.setToolTip("Включить автоматическую выгрузку по расписанию")
        self._sched_check.toggled.connect(self._on_changed)
        root.addWidget(self._sched_check)

        controls = QHBoxLayout()
        controls.setContentsMargins(24, 0, 0, 0)
        controls.setSpacing(8)

        self._mode_combo = QComboBox()
        style_combo_popup(self._mode_combo)
        self._mode_combo.addItems([
            "Ежедневно",
            "Каждые N часов",
            "Каждые N минут",
            "Каждые N секунд",
        ])
        self._mode_combo.currentIndexChanged.connect(self._on_changed)
        self._mode_combo.setFixedWidth(180)
        controls.addWidget(self._mode_combo, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._value_edit = QLineEdit()
        self._value_edit.setFixedWidth(100)
        self._value_edit.editingFinished.connect(self._on_changed)
        controls.addWidget(self._value_edit, alignment=Qt.AlignmentFlag.AlignVCenter)

        controls.addStretch(1)

        self._progress_lbl = QLabel()
        self._progress_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        controls.addWidget(self._progress_lbl)
        root.addLayout(controls)

        self._update_placeholder()

    def schedule_enabled(self) -> bool:
        return self._sched_check.isChecked()

    def schedule_mode(self) -> str:
        return SCHEDULE_MODE_BY_INDEX[self._mode_combo.currentIndex()]

    def schedule_value(self) -> str:
        return self._value_edit.text().strip()

    def set_schedule(self, enabled: bool, mode: str, value: str) -> None:
        widgets = (self._sched_check, self._mode_combo, self._value_edit)
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self._sched_check.setChecked(enabled)
            try:
                index = SCHEDULE_MODE_BY_INDEX.index(mode)
            except ValueError:
                index = 0
            self._mode_combo.setCurrentIndex(index)
            self._value_edit.setText(value)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._update_placeholder()

    def set_progress_text(self, text: str) -> None:
        self._progress_lbl.setText(text)

    def _update_placeholder(self) -> None:
        self._value_edit.setPlaceholderText(
            _PLACEHOLDERS.get(self._mode_combo.currentIndex(), "")
        )

    def _on_changed(self) -> None:
        self._update_placeholder()
        self.changed.emit()
