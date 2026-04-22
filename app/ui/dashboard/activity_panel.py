"""Dashboard activity/history card with refresh and clear actions."""

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

from app.config import ConfigManager
from app.export.run_store import ExportRunStore
from app.ui.dashboard_activity import (
    clear_job_histories,
    refresh_dashboard_activity,
    refresh_dashboard_activity_entries,
)
from app.ui.export_jobs_store import load_export_jobs
from app.ui.shared.worker_threads import run_worker, shutdown_worker_threads
from app.ui.theme import Theme

_REFRESH_DEBOUNCE_MS = 120


class _ActivityLoadWorker(QObject):
    finished = Signal(int, object, object)
    error = Signal(str)

    def __init__(
        self,
        *,
        token: int,
        config: ConfigManager,
        run_store: ExportRunStore,
    ) -> None:
        super().__init__()
        self._token = token
        self._config = config
        self._run_store = run_store

    @Slot()
    def run(self) -> None:
        try:
            entries = self._run_store.list_recent_history(limit=100)
            jobs = load_export_jobs(self._config, self._run_store) if not entries else []
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.error.emit(str(exc))
            return
        self.finished.emit(self._token, entries, jobs)


class DashboardActivityPanel(QFrame):
    def __init__(
        self,
        config: ConfigManager,
        run_store: ExportRunStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._run_store = run_store or ExportRunStore()
        self._activity_worker: QObject | None = None
        self._refresh_token = 0
        self._refresh_queued = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self.refresh_activity)
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

    def schedule_refresh(self) -> None:
        if self._activity_worker is not None:
            self._refresh_queued = True
            return
        self._refresh_timer.start()

    def stop(self) -> None:
        self._refresh_timer.stop()
        self._refresh_token += 1
        self._refresh_queued = False
        shutdown_worker_threads(self)

    def refresh_activity(self) -> None:
        self._refresh_timer.stop()
        if self._activity_worker is not None:
            self._refresh_queued = True
            return
        self._refresh_token += 1
        self._refresh_queued = False
        token = self._refresh_token
        worker = _ActivityLoadWorker(
            token=token,
            config=self._config,
            run_store=self._run_store,
        )
        run_worker(
            self,
            worker,
            pin_attr="_activity_worker",
            on_finished=self._apply_loaded_activity,
            on_error=self._handle_refresh_error,
            connect_signals=lambda _worker, thread: thread.finished.connect(
                self._on_refresh_thread_finished
            ),
        )

    @Slot()
    def clear_all_history(self) -> bool:
        self._refresh_timer.stop()
        self._refresh_token += 1
        self._refresh_queued = False
        entries = self._run_store.list_recent_history(limit=10_000)
        if entries:
            total = len(entries)
        else:
            jobs = load_export_jobs(self._config, self._run_store)
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
        if entries:
            self._run_store.clear_all_history()
        else:
            cfg = self._config.load()
            cfg["export_jobs"] = cleared_jobs
            self._config.save(cfg)
        self.refresh_activity()
        return True

    @Slot(int, object, object)
    def _apply_loaded_activity(
        self,
        token: int,
        entries: object,
        jobs: object,
    ) -> None:
        if token != self._refresh_token:
            return
        history_entries = entries if isinstance(entries, list) else []
        if history_entries:
            count = refresh_dashboard_activity_entries(
                self._activity_layout,
                self,
                history_entries,
            )
        else:
            jobs_payload = jobs if isinstance(jobs, list) else []
            count = refresh_dashboard_activity(
                self._activity_layout,
                self,
                jobs_payload,
            )
        self._activity_count.setText(str(count))

    @Slot(str)
    def _handle_refresh_error(self, _message: str) -> None:
        pass

    @Slot()
    def _on_refresh_thread_finished(self) -> None:
        QTimer.singleShot(0, self._drain_queued_refresh)

    @Slot()
    def _drain_queued_refresh(self) -> None:
        if self._activity_worker is not None or not self._refresh_queued:
            return
        self._refresh_queued = False
        self.refresh_activity()
