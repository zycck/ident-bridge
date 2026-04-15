# -*- coding: utf-8 -*-
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
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
from app.core.app_logger import get_logger
from app.core.scheduler import SyncScheduler
from app.core.sql_client import SqlClient

_log = get_logger(__name__)


class _PingWorker(QObject):
    result = Signal(bool)

    def __init__(self, config: ConfigManager) -> None:
        super().__init__()
        self._config = config

    @Slot()
    def run(self) -> None:
        cfg = self._config.load()
        client = SqlClient(cfg)
        try:
            client.connect()
            alive = client.is_alive()
        except Exception as exc:
            _log.debug("DB ping failed: %s", exc)
            alive = False
        finally:
            client.disconnect()
        _log.debug("DB ping: %s", "alive" if alive else "unreachable")
        self.result.emit(alive)


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
        self._ping_running = False
        self._ping_worker: _PingWorker | None = None  # strong ref to prevent GC

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

        card1 = self._make_card()
        c1_layout = QVBoxLayout(card1)
        c1_layout.setSpacing(6)
        c1_title = QLabel("Подключение к БД")
        c1_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c1_title.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: 600;")
        indicator_row = QHBoxLayout()
        indicator_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("statusDot")
        self._status_dot.setStyleSheet("color: #6B7280; font-size: 20px;")
        self._status_text = QLabel("Проверка...")
        self._status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_text.setStyleSheet("color: #9CA3AF; font-size: 9.5pt;")
        indicator_row.addWidget(self._status_dot)
        indicator_row.addWidget(self._status_text)
        c1_layout.addWidget(c1_title)
        c1_layout.addLayout(indicator_row)

        card2 = self._make_card()
        c2_layout = QVBoxLayout(card2)
        c2_layout.setSpacing(6)
        c2_title = QLabel("Последняя синхронизация")
        c2_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c2_title.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: 600;")
        self._last_sync_label = QLabel("Никогда")
        self._last_sync_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._last_sync_label.setStyleSheet("color: #D1D5DB; font-size: 10pt;")
        c2_layout.addWidget(c2_title)
        c2_layout.addWidget(self._last_sync_label)

        card3 = self._make_card()
        c3_layout = QVBoxLayout(card3)
        c3_layout.setSpacing(6)
        c3_title = QLabel("Следующий запуск")
        c3_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c3_title.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: 600;")
        self._next_run_label = QLabel("Не запланировано")
        self._next_run_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._next_run_label.setStyleSheet("color: #D1D5DB; font-size: 10pt;")
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
        self._log.document().setMaximumBlockCount(200)
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
        # Defer first ping until after event loop starts
        QTimer.singleShot(1500, self._ping_db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connected(self, ok: bool) -> None:
        color = "#34D399" if ok else "#F87171"
        label = "Подключено" if ok else "Нет связи"
        self._status_dot.setStyleSheet(f"color: {color}; font-size: 20px;")
        self._status_text.setText(label)
        self._status_text.setStyleSheet(f"color: {color}; font-size: 9.5pt;")

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
        if self._ping_running:
            return
        self._ping_running = True

        worker = _PingWorker(self._config)
        self._ping_worker = worker  # keep alive — GC would delete it otherwise
        thread = QThread(self)
        worker.moveToThread(thread)

        worker.result.connect(self._on_ping_result)
        worker.result.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda w=worker: setattr(self, '_ping_worker', None) if self._ping_worker is w else None)

        thread.start()

    @Slot(bool)
    def _on_ping_result(self, alive: bool) -> None:
        self._ping_running = False
        self.set_connected(alive)

    def _on_update_clicked(self) -> None:
        self.update_requested.emit(self._update_url)
