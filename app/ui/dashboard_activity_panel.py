"""Dashboard activity/history card with refresh and clear actions."""

from PySide6.QtCore import Qt, Slot
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

from app.config import ConfigManager
from app.ui.dashboard_activity import clear_job_histories, refresh_dashboard_activity
from app.ui.theme import Theme


class DashboardActivityPanel(QFrame):
    def __init__(
        self,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("activityCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        activity_layout = QVBoxLayout(self)
        activity_layout.setContentsMargins(12, 10, 12, 10)
        activity_layout.setSpacing(6)

        activity_hdr = QHBoxLayout()
        self._activity_title = QLabel("История запусков")
        self._activity_title.setObjectName("sectionHeader")
        self._activity_title.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"font-weight: {Theme.font_weight_semi};"
        )
        activity_hdr.addWidget(self._activity_title)
        activity_hdr.addStretch()
        self._activity_count = QLabel("0")
        self._activity_count.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt;"
        )
        activity_hdr.addWidget(self._activity_count)

        self._activity_clear_btn = QPushButton("Очистить всё")
        self._activity_clear_btn.setFlat(True)
        self._activity_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._activity_clear_btn.setStyleSheet(
            f"QPushButton {{"
            f"  border: none; background: transparent; padding: 0 0 0 12px;"
            f"  color: {Theme.gray_500};"
            f"  text-decoration: underline;"
            f"}}"
            f"QPushButton:hover {{ color: {Theme.error}; }}"
        )
        self._activity_clear_btn.clicked.connect(self.clear_all_history)
        activity_hdr.addWidget(self._activity_clear_btn)
        activity_layout.addLayout(activity_hdr)

        self._activity_container = QWidget()
        self._activity_container.setStyleSheet("background: transparent;")
        self._activity_layout = QVBoxLayout(self._activity_container)
        self._activity_layout.setContentsMargins(0, 4, 0, 0)
        self._activity_layout.setSpacing(2)

        self._activity_scroll = QScrollArea()
        self._activity_scroll.setWidget(self._activity_container)
        self._activity_scroll.setWidgetResizable(True)
        self._activity_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._activity_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._activity_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        activity_layout.addWidget(self._activity_scroll)

    def activity_count_text(self) -> str:
        return self._activity_count.text()

    def refresh_activity(self) -> None:
        count = refresh_dashboard_activity(
            self._activity_layout,
            self,
            self._config.load().get("export_jobs") or [],  # type: ignore[arg-type]
        )
        self._activity_count.setText(str(count))

    @Slot()
    def clear_all_history(self) -> bool:
        cfg = self._config.load()
        jobs = cfg.get("export_jobs") or []  # type: ignore[assignment]
        total, cleared_jobs = clear_job_histories(jobs)
        if total == 0:
            return False
        reply = QMessageBox.question(
            self,
            "Очистить историю",
            f"Удалить все записи истории ({total}) из всех выгрузок?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        cfg["export_jobs"] = cleared_jobs  # type: ignore[typeddict-unknown-key]
        self._config.save(cfg)
        self.refresh_activity()
        return True
