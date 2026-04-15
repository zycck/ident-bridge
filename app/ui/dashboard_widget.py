# -*- coding: utf-8 -*-
"""
DashboardWidget — status overview panel.

Shows three status cards (DB connection, last sync, next run), an update
banner, and a live log pane.  Polls the SQL connection every 30 seconds
via QTimer and reacts to scheduler signals.
"""
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigManager, SyncResult
from app.core.scheduler import SyncScheduler
from app.core.sql_client import SqlClient


class DashboardWidget(QWidget):
    update_requested = Signal(str)  # carries download URL

    def __init__(
        self,
        scheduler: SyncScheduler,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._update_url: str = ""

        self._build_ui()
        self._connect_signals(scheduler)
        self._start_ping_timer()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        root.addLayout(self._build_card_row())
        root.addWidget(self._build_update_banner())
        root.addWidget(self._build_log())

    def _build_card_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        # Card 1 — DB connection
        card1 = self._make_card()
        c1_layout = QVBoxLayout(card1)
        c1_layout.setSpacing(6)
        c1_title = QLabel("Подключение к БД")
        c1_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        indicator_row = QHBoxLayout()
        indicator_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("statusDot")
        self._status_dot.setStyleSheet("color: #6B7280; font-size: 18px;")
        self._status_text = QLabel("Проверка...")
        self._status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        indicator_row.addWidget(self._status_dot)
        indicator_row.addWidget(self._status_text)
        c1_layout.addWidget(c1_title)
        c1_layout.addLayout(indicator_row)

        # Card 2 — Last sync
        card2 = self._make_card()
        c2_layout = QVBoxLayout(card2)
        c2_layout.setSpacing(6)
        c2_title = QLabel("Последняя синхронизация")
        c2_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._last_sync_label = QLabel("Никогда")
        self._last_sync_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c2_layout.addWidget(c2_title)
        c2_layout.addWidget(self._last_sync_label)

        # Card 3 — Next run
        card3 = self._make_card()
        c3_layout = QVBoxLayout(card3)
        c3_layout.setSpacing(6)
        c3_title = QLabel("Следующий запуск")
        c3_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._next_run_label = QLabel("Не запланировано")
        self._next_run_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c3_layout.addWidget(c3_title)
        c3_layout.addWidget(self._next_run_label)

        row.addWidget(card1)
        row.addWidget(card2)
        row.addWidget(card3)
        return row

    def _make_card(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(80)
        return frame

    def _build_update_banner(self) -> QFrame:
        self._update_banner = QFrame()
        self._update_banner.setObjectName("updateBanner")
        self._update_banner.setVisible(False)

        banner_layout = QHBoxLayout(self._update_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)

        self._update_label = QLabel("Доступна версия — ")
        self._update_btn = QPushButton("Обновить")
        self._update_btn.setFlat(True)
        self._update_btn.clicked.connect(self._on_update_clicked)

        banner_layout.addWidget(self._update_label)
        banner_layout.addWidget(self._update_btn)
        banner_layout.addStretch()

        return self._update_banner

    def _build_log(self) -> QPlainTextEdit:
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.document().setMaximumBlockCount(20)
        self._log.setMinimumHeight(120)
        return self._log

    # ------------------------------------------------------------------
    # Signal wiring & timer
    # ------------------------------------------------------------------

    def _connect_signals(self, scheduler: SyncScheduler) -> None:
        scheduler.next_run_changed.connect(self.update_next_run)

    def _start_ping_timer(self) -> None:
        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(30_000)
        self._ping_timer.timeout.connect(self._ping_db)
        self._ping_timer.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connected(self, ok: bool) -> None:
        color = "#22C55E" if ok else "#EF4444"
        self._status_dot.setStyleSheet(f"color: {color}; font-size: 18px;")
        self._status_text.setText("Подключено" if ok else "Нет связи")

    def append_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{ts}] {msg}")
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )

    def update_next_run(self, dt: datetime | None) -> None:
        if dt is None:
            self._next_run_label.setText("Не запланировано")
        else:
            self._next_run_label.setText(dt.strftime("%H:%M  %d.%m"))

    def update_last_sync(self, result: SyncResult) -> None:
        ts = result.timestamp.strftime("%H:%M  %d.%m")
        self._last_sync_label.setText(f"{ts}  ·  {result.rows_synced} стр.")

    def show_update_banner(self, version: str, url: str) -> None:
        self._update_url = url
        self._update_label.setText(f"Доступна версия {version}  ·  ")
        self._update_banner.setVisible(True)

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _ping_db(self) -> None:
        cfg = self._config.load()
        client = SqlClient(cfg)
        try:
            client.connect()
            alive = client.is_alive()
        except Exception:  # noqa: BLE001
            alive = False
        finally:
            client.disconnect()
        self.set_connected(alive)

    def _on_update_clicked(self) -> None:
        self.update_requested.emit(self._update_url)
