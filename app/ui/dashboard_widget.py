# -*- coding: utf-8 -*-
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
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

from app.config import ConfigManager, SyncResult
from app.core.app_logger import get_logger
from app.core.constants import PING_INTERVAL_MS
from app.core.sql_client import SqlClient
from app.ui.history_row import HistoryRow
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme
from app.ui.threading import run_worker

_log = get_logger(__name__)


class _PingWorker(QObject):
    result = Signal(object)  # bool | None; None = instance not configured
    finished = Signal()

    def __init__(self, instance: str, database: str, user: str, password: str, trust_cert: bool) -> None:
        super().__init__()
        self._instance = instance
        self._database = database
        self._user = user
        self._password = password
        self._trust_cert = trust_cert

    @Slot()
    def run(self) -> None:
        from app.config import AppConfig
        try:
            if not self._instance:
                _log.debug("DB ping skipped: instance not configured")
                self.result.emit(None)
                return

            cfg = AppConfig(
                sql_instance=self._instance,
                sql_database=self._database,
                sql_user=self._user,
                sql_password=self._password,
                sql_trust_cert=self._trust_cert,
            )
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
        finally:
            self.finished.emit()


class DashboardWidget(QWidget):
    update_requested = Signal(str)  # carries download URL

    def __init__(
        self,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._update_url: str = ""
        self._ping_running = False
        self._ping_worker: _PingWorker | None = None  # strong ref to prevent GC

        self._build_ui()
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
        root.addWidget(self._build_activity_section(), stretch=1)

        # Populate activity rows from existing jobs
        self.refresh_activity()

    def _build_activity_section(self) -> QFrame:
        # ── Activity / run history ─────────────────────────────────────
        activity_box = QFrame()
        activity_box.setObjectName("activityCard")
        activity_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        activity_layout = QVBoxLayout(activity_box)
        activity_layout.setContentsMargins(12, 10, 12, 10)
        activity_layout.setSpacing(6)

        # Header row: title + count
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
        self._activity_clear_btn.clicked.connect(self._on_clear_all_history)
        activity_hdr.addWidget(self._activity_clear_btn)

        activity_layout.addLayout(activity_hdr)

        # Scrollable list of history rows
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

        # Empty state placeholder (replaced in refresh_activity)
        self._activity_empty = QLabel(
            "Нет запусков. Запустите выгрузку на вкладке «Выгрузки»."
        )
        self._activity_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._activity_empty.setStyleSheet(
            f"color: {Theme.gray_400}; "
            f"font-size: {Theme.font_size_sm}pt; "
            f"padding: 24px 0;"
        )
        self._activity_layout.addWidget(self._activity_empty)

        return activity_box

    def _build_card_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
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

    # ------------------------------------------------------------------
    # Timer
    # ------------------------------------------------------------------

    def _start_ping_timer(self) -> None:
        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(PING_INTERVAL_MS)
        self._ping_timer.timeout.connect(self._ping_db)
        self._ping_timer.start()
        # Defer first ping until after event loop starts
        QTimer.singleShot(1500, self._ping_db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Stop the periodic ping timer. Called on app shutdown."""
        if hasattr(self, "_ping_timer") and self._ping_timer is not None:
            self._ping_timer.stop()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.stop()
        super().closeEvent(event)

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
        self._last_sync_label.setText(f"{ts}  ·  {result.rows_synced} стр.")

    def show_update_banner(self, version: str, url: str) -> None:
        self._update_url = url
        self._update_label.setText(f"Доступна версия {version}  ·  ")
        self._update_banner.setVisible(True)

    def set_update_in_progress(self, running: bool) -> None:
        self._update_btn.setEnabled(not running)
        self._update_btn.setText("Загрузка…" if running else "Обновить")

    def refresh_activity(self) -> None:
        """Re-aggregate history from all export jobs and rebuild the list."""
        cfg = self._config.load()
        jobs: list = cfg.get("export_jobs") or []  # type: ignore[assignment]

        # Flatten: list of (entry, job_name) tuples
        all_entries: list[tuple[dict, str]] = []
        for job in jobs:
            job_name = job.get("name", "") or "(без названия)"
            for entry in (job.get("history") or []):
                all_entries.append((entry, job_name))

        # Sort by ts desc (string sort works because ts format is YYYY-MM-DD HH:MM)
        all_entries.sort(key=lambda x: x[0].get("ts", ""), reverse=True)

        # Cap to most recent 100
        all_entries = all_entries[:100]

        # Clear existing rows
        while self._activity_layout.count():
            item = self._activity_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Populate
        if not all_entries:
            self._activity_empty = QLabel(
                "Нет запусков. Запустите выгрузку на вкладке «Выгрузки»."
            )
            self._activity_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._activity_empty.setStyleSheet(
                f"color: {Theme.gray_400}; "
                f"font-size: {Theme.font_size_sm}pt; "
                f"padding: 24px 0;"
            )
            self._activity_layout.addWidget(self._activity_empty)
        else:
            for i, (entry, job_name) in enumerate(all_entries):
                row = HistoryRow(
                    entry, i, self, job_name=job_name, show_delete=False
                )
                self._activity_layout.addWidget(row)
            self._activity_layout.addStretch()

        self._activity_count.setText(str(len(all_entries)))

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _ping_db(self) -> None:
        if self._ping_running:
            return
        # Capture config snapshot on the main thread before spawning the worker
        cfg = self._config.load()
        self._ping_running = True

        worker = _PingWorker(
            instance=cfg.get("sql_instance") or "",
            database=cfg.get("sql_database") or "master",
            user=cfg.get("sql_user") or "",
            password=cfg.get("sql_password") or "",
            trust_cert=cfg.get("sql_trust_cert") if cfg.get("sql_trust_cert") is not None else True,
        )
        thread = run_worker(
            self,
            worker,
            pin_attr="_ping_worker",
            on_finished=self._on_ping_finished,
        )
        worker.result.connect(self._on_ping_result)
        worker.result.connect(thread.quit)

    @Slot(object)
    def _on_ping_result(self, alive) -> None:
        self._ping_running = False
        self.set_connected(alive)

    @Slot()
    def _on_ping_finished(self) -> None:
        # Defensive reset in case a fast worker finished before a result handler
        # had a chance to run or exited early with no connectivity update.
        self._ping_running = False

    def _on_update_clicked(self) -> None:
        self.update_requested.emit(self._update_url)

    @Slot()
    def _on_clear_all_history(self) -> None:
        """Clear history entries from EVERY export job after confirmation."""
        cfg = self._config.load()
        jobs = cfg.get("export_jobs") or []  # type: ignore[assignment]
        total = sum(len(job.get("history") or []) for job in jobs)
        if total == 0:
            return
        reply = QMessageBox.question(
            self,
            "Очистить историю",
            f"Удалить все записи истории ({total}) из всех выгрузок?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for job in jobs:
            if "history" in job:
                job["history"] = []
        cfg["export_jobs"] = jobs  # type: ignore[typeddict-unknown-key]
        self._config.save(cfg)
        self.refresh_activity()
