"""Reusable dashboard cards for connection and last-sync status."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.config import SyncResult
from app.ui.formatters import format_duration_compact
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme


class DashboardStatusCards(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        title_style = (
            f"color: {Theme.gray_500}; font-size: 9pt; font-weight: 600;"
        )

        card1 = self._make_card()
        c1_layout = QVBoxLayout(card1)
        c1_layout.setSpacing(6)
        c1_title_row = QHBoxLayout()
        c1_title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c1_title_row.setSpacing(6)
        c1_db_icon = QLabel()
        c1_db_icon.setPixmap(
            lucide("database", color=Theme.gray_600, size=14).pixmap(14, 14)
        )
        c1_title = QLabel("Подключение к БД")
        c1_title.setStyleSheet(title_style)
        c1_title_row.addWidget(c1_db_icon)
        c1_title_row.addWidget(c1_title)
        indicator_row = QHBoxLayout()
        indicator_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("statusDot")
        self._status_dot.setStyleSheet(
            f"color: {Theme.gray_500}; font-size: 20px;"
        )
        self._status_text = QLabel("Проверка...")
        self._status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_text.setStyleSheet(
            f"color: {Theme.gray_400}; font-size: 9.5pt;"
        )
        indicator_row.addWidget(self._status_dot)
        indicator_row.addWidget(self._status_text)
        c1_layout.addLayout(c1_title_row)
        c1_layout.addLayout(indicator_row)

        card2 = self._make_card()
        c2_layout = QVBoxLayout(card2)
        c2_layout.setSpacing(6)
        c2_title_row = QHBoxLayout()
        c2_title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c2_title_row.setSpacing(6)
        c2_clock_icon = QLabel()
        c2_clock_icon.setPixmap(
            lucide("clock", color=Theme.gray_600, size=14).pixmap(14, 14)
        )
        c2_title = QLabel("Последняя синхронизация")
        c2_title.setStyleSheet(title_style)
        c2_title_row.addWidget(c2_clock_icon)
        c2_title_row.addWidget(c2_title)
        self._last_sync_label = QLabel("Никогда")
        self._last_sync_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._last_sync_label.setStyleSheet(
            f"color: {Theme.gray_700}; font-size: 10pt;"
        )
        c2_layout.addLayout(c2_title_row)
        c2_layout.addWidget(self._last_sync_label)

        row.addWidget(card1)
        row.addWidget(card2)

    def _make_card(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(80)
        return frame

    def set_connected(self, ok: bool | None) -> None:
        if ok is None:
            color, label = Theme.gray_400, "Не настроено"
        elif ok:
            color, label = Theme.success, "Подключено"
        else:
            color, label = Theme.error, "Нет связи"
        self._status_dot.setStyleSheet(f"color: {color}; font-size: 20px;")
        self._status_text.setText(label)
        self._status_text.setStyleSheet(f"color: {color}; font-size: 9.5pt;")

    def update_last_sync(self, result: SyncResult) -> None:
        ts = result.timestamp.strftime("%H:%M:%S  %d.%m")
        self._last_sync_label.setText(
            f"{ts}  ·  {result.rows_synced} стр.  ·  "
            f"{format_duration_compact(result.duration_us)}"
        )

    def connection_label_text(self) -> str:
        return self._status_text.text()

    def connection_label_style(self) -> str:
        return self._status_text.styleSheet()

    def last_sync_text(self) -> str:
        return self._last_sync_label.text()
