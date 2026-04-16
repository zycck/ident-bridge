# -*- coding: utf-8 -*-
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from app.config import ConfigManager, SyncResult
from app.core.constants import PING_INTERVAL_MS
from app.ui.dashboard_ping_coordinator import DashboardPingCoordinator
from app.ui.dashboard_ping_timer import DashboardPingTimerController
from app.ui.dashboard_shell import DashboardShell


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
        self._shell = DashboardShell(self._config, self)
        self._shell.update_requested.connect(self.update_requested)
        self._status_cards = self._shell.status_cards()
        self._update_banner = self._shell.update_banner()
        self._activity_panel = self._shell.activity_panel()
        from PySide6.QtWidgets import QVBoxLayout

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._shell)
        self.refresh_activity()

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
