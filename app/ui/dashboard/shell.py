"""Composite shell/layout for DashboardWidget."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.config import ConfigManager
from app.export.run_store import ExportRunStore
from app.ui.dashboard_activity_panel import DashboardActivityPanel
from app.ui.dashboard_status_cards import DashboardStatusCards
from app.ui.dashboard_update_banner import DashboardUpdateBanner


class DashboardShell(QWidget):
    """Owns dashboard layout composition while reusing extracted widgets."""

    update_requested = Signal(str)

    def __init__(
        self,
        config: ConfigManager,
        run_store: ExportRunStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._run_store = run_store or ExportRunStore()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        self._status_cards = DashboardStatusCards(self)
        root.addWidget(self._status_cards)

        self._update_banner = DashboardUpdateBanner(self)
        self._update_banner.update_requested.connect(self.update_requested)
        root.addWidget(self._update_banner)

        self._activity_panel = DashboardActivityPanel(self._config, run_store=self._run_store, parent=self)
        root.addWidget(self._activity_panel, stretch=1)

    def status_cards(self) -> DashboardStatusCards:
        return self._status_cards

    def update_banner(self) -> DashboardUpdateBanner:
        return self._update_banner

    def activity_panel(self) -> DashboardActivityPanel:
        return self._activity_panel
