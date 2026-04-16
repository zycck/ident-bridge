# -*- coding: utf-8 -*-
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from app.config import ConfigManager, SyncResult
from app.core.constants import PING_INTERVAL_MS
from app.ui.dashboard_activity_panel import DashboardActivityPanel
from app.ui.dashboard_ping_coordinator import DashboardPingCoordinator
from app.ui.dashboard_ping_timer import DashboardPingTimerController
from app.ui.dashboard_status_cards import DashboardStatusCards
from app.ui.dashboard_update_banner import DashboardUpdateBanner


class DashboardWidget(QWidget):
    update_requested = Signal(str)  # carries download URL

    def __init__(
        self,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._ping = DashboardPingCoordinator(self, config, self.set_connected)
        self._ping_timer = DashboardPingTimerController(
            parent=self,
            ping=self._ping.ping_db,
            interval_ms=PING_INTERVAL_MS,
        )

        self._build_ui()
        self._ping_timer.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(self._build_status_cards())
        root.addWidget(self._build_update_banner())
        root.addWidget(self._build_activity_section(), stretch=1)

        # Populate activity rows from existing jobs
        self.refresh_activity()

    def _build_activity_section(self) -> QFrame:
        panel = DashboardActivityPanel(self._config, self)
        self._activity_panel = panel
        return panel

    def _build_status_cards(self) -> DashboardStatusCards:
        cards = DashboardStatusCards(self)
        self._status_cards = cards
        return cards

    def _build_update_banner(self) -> DashboardUpdateBanner:
        banner = DashboardUpdateBanner(self)
        banner.update_requested.connect(self.update_requested)
        return banner

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Stop the periodic ping timer. Called on app shutdown."""
        self._ping_timer.stop()
        self._ping.stop()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.stop()
        super().closeEvent(event)

    def set_connected(self, ok: bool | None) -> None:
        self._status_cards.set_connected(ok)

    def update_last_sync(self, result: SyncResult) -> None:
        self._status_cards.update_last_sync(result)

    def show_update_banner(self, version: str, url: str) -> None:
        self._update_banner.show_update(version, url)

    def set_update_in_progress(self, running: bool) -> None:
        self._update_banner.set_in_progress(running)

    def refresh_activity(self) -> None:
        """Re-aggregate history from all export jobs and rebuild the list."""
        self._activity_panel.refresh_activity()
