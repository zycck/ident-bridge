# -*- coding: utf-8 -*-
"""ExportJobsWidget — list-detail export job manager (tiles + editor pages)."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

# third-party
import sqlglot
from sqlglot.errors import ParseError, TokenError
from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    AppConfig,
    ConfigManager,
    ExportHistoryEntry,
    ExportJob,
    SyncResult,
    TriggerType,
)
from app.core.app_logger import get_logger
from app.core.constants import (
    DEBOUNCE_SAVE_MS,
    DEBOUNCE_SYNTAX_MS,
    HISTORY_MAX,
    SCHED_VALUE_INPUT_W,
)
from app.core.scheduler import SyncScheduler
from app.ui.history_row import HistoryRow
from app.ui.lucide_icons import lucide
from app.ui.sql_editor import SqlEditor
from app.ui.test_run_dialog import TestRunDialog
from app.ui.theme import Theme
from app.ui.threading import run_worker
from app.ui.widgets import HeaderLabel, hsep
from app.workers.export_worker import ExportWorker

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# SQL Syntax Validator (sqlglot-backed, T-SQL dialect)
# ---------------------------------------------------------------------------

def _validate_sql(sql: str) -> tuple[bool, str]:
    """
    Full T-SQL syntax check via sqlglot. Parses the entire query
    (statements separated by ;) using the T-SQL dialect grammar.
    Returns (ok, short_message_in_russian).
    """
    sql = sql.strip()
    if not sql:
        return False, "Запрос пуст"

    try:
        statements = sqlglot.parse(
            sql,
            dialect="tsql",
            error_level=sqlglot.ErrorLevel.IMMEDIATE,
        )
    except (ParseError, TokenError) as exc:
        return False, _format_sqlglot_error(exc)
    except Exception as exc:  # pragma: no cover — defensive
        return False, f"Ошибка парсера: {exc}"

    # sqlglot returns [None] for trailing/empty statements; require at least one real one
    if not any(stmt is not None for stmt in statements):
        return False, "Пустое выражение"

    return True, "SQL корректен"


def _format_sqlglot_error(exc: Exception) -> str:
    """Take the first sqlglot error and make it short + Russian-friendly."""
    errors = getattr(exc, "errors", None)
    if errors:
        first = errors[0]
        desc = first.get("description") or ""
        line = first.get("line")
        col  = first.get("col")
        # Translate a few common sqlglot phrases to Russian
        ru = (desc
              .replace("Expecting", "Ожидается")
              .replace("Expected", "Ожидается")
              .replace("Invalid expression", "Недопустимое выражение")
              .replace("Unexpected token", "неожиданный токен")
              .replace("but got", "—"))
        # Strip noisy <Token …> blob if present
        ru = re.sub(r"<Token[^>]*text:\s*([^,]+),[^>]*>", r"«\1»", ru)
        ru = re.sub(r"\s+", " ", ru).strip()
        if line and col:
            return f"стр {line}:{col} · {ru[:80]}"
        return ru[:100] or "Синтаксическая ошибка"
    return str(exc)[:100] or "Синтаксическая ошибка"


# ---------------------------------------------------------------------------
# ExportJobTile
# ---------------------------------------------------------------------------

class ExportJobTile(QFrame):
    """Compact tile representing one export job in the list view.

    The whole tile surface is clickable: click → opens the detail editor
    via open_requested signal. The [▶] run button triggers the export
    immediately without opening the editor. The [···] menu offers
    Открыть / Удалить.
    """

    open_requested   = Signal(str)   # job_id
    run_requested    = Signal(str)   # job_id
    delete_requested = Signal(str)   # job_id

    TILE_W = 280
    TILE_H = 130

    def __init__(self, job: ExportJob, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("jobTile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(self.TILE_W, self.TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._job_id: str = job.get("id", "") or str(uuid.uuid4())
        self._job: ExportJob = job
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Tile background + hover via inline stylesheet
        self.setStyleSheet(
            f"#jobTile {{"
            f"  background: {Theme.surface};"
            f"  border: 1px solid {Theme.border};"
            f"  border-radius: {Theme.radius_md}px;"
            f"}}"
            f"#jobTile:hover {{"
            f"  border-color: {Theme.primary_400};"
            f"  background: {Theme.primary_50};"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 12, 12)
        layout.setSpacing(6)

        # ── Top row: name + run button ──────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        name = self._job.get("name") or "Без названия"
        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet(
            f"color: {Theme.gray_900}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"background: transparent;"
        )
        # Truncate if too long
        self._name_lbl.setMaximumWidth(self.TILE_W - 60)
        top.addWidget(self._name_lbl, stretch=1)

        self._run_btn = QPushButton()
        self._run_btn.setIcon(lucide("play", color=Theme.gray_900, size=12))
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setFixedSize(28, 28)
        self._run_btn.setToolTip("Запустить сейчас")
        self._run_btn.clicked.connect(self._on_run_clicked)
        top.addWidget(self._run_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(top)

        # ── Status line: last run summary ────────────────────────────
        status_text, status_color = self._compute_status()
        self._status_lbl = QLabel(status_text)
        self._status_lbl.setStyleSheet(
            f"color: {status_color}; "
            f"font-size: {Theme.font_size_sm}pt; "
            f"background: transparent;"
        )
        layout.addWidget(self._status_lbl)

        layout.addStretch()

        # ── Bottom row: schedule info + more menu ────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        sched_text = self._compute_schedule_text()
        self._sched_lbl = QLabel(sched_text)
        self._sched_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        bottom.addWidget(self._sched_lbl, stretch=1)

        self._more_btn = QPushButton()
        self._more_btn.setIcon(lucide("ellipsis", color=Theme.gray_500, size=14))
        self._more_btn.setFixedSize(24, 24)
        self._more_btn.setStyleSheet(
            "QPushButton {"
            "  border: 1px solid transparent;"
            "  background: transparent;"
            "  border-radius: 5px;"
            "}"
            f"QPushButton:hover {{"
            f"  background-color: {Theme.gray_100};"
            f"  border-color: {Theme.border};"
            f"}}"
        )
        self._more_btn.setToolTip("Действия")
        self._more_btn.clicked.connect(self._show_menu)
        bottom.addWidget(self._more_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    def job_id(self) -> str:
        return self._job_id

    def update_from_job(self, job: ExportJob) -> None:
        """Refresh the tile's labels from a (possibly updated) job dict."""
        self._job = job
        self._name_lbl.setText(job.get("name") or "Без названия")
        status_text, status_color = self._compute_status()
        self._status_lbl.setText(status_text)
        self._status_lbl.setStyleSheet(
            f"color: {status_color}; "
            f"font-size: {Theme.font_size_sm}pt; "
            f"background: transparent;"
        )
        self._sched_lbl.setText(self._compute_schedule_text())

    def _compute_status(self) -> tuple[str, str]:
        """Return (text, color) for the status line based on history[0]."""
        history = self._job.get("history") or []
        if not history:
            return "Ещё не запускалось", Theme.gray_500
        latest = history[0]
        ts_short = self._format_short_ts(latest.get("ts", ""))
        if latest.get("ok"):
            return f"✓ {latest.get('rows', 0)} строк · {ts_short}", Theme.success
        else:
            err = latest.get("err", "Ошибка")
            return f"✗ {err[:40]}", Theme.error

    def _compute_schedule_text(self) -> str:
        if not self._job.get("schedule_enabled"):
            return "Ручной запуск"
        mode = self._job.get("schedule_mode", "daily")
        value = self._job.get("schedule_value", "")
        if not value:
            return "Расписание не настроено"
        if mode == "daily":
            return f"Ежедневно в {value}"
        else:
            return f"Каждые {value} часов"

    @staticmethod
    def _format_short_ts(ts: str) -> str:
        if not ts or len(ts) < 16:
            return ts
        try:
            dt = datetime.strptime(ts[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            return ts
        today = datetime.now().date()
        if dt.date() == today:
            return f"сегодня {dt.strftime('%H:%M')}"
        if dt.date() == today - timedelta(days=1):
            return f"вчера {dt.strftime('%H:%M')}"
        return dt.strftime("%d.%m %H:%M")

    # ------------------------------------------------------------------
    def _on_run_clicked(self) -> None:
        self.run_requested.emit(self._job_id)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        open_act = menu.addAction("Открыть")
        del_act = menu.addAction("Удалить")
        chosen = menu.exec(self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()))
        if chosen is open_act:
            self.open_requested.emit(self._job_id)
        elif chosen is del_act:
            self.delete_requested.emit(self._job_id)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Open the editor when the tile background is clicked, but not
        # when one of the inner buttons is clicked (Qt routes button
        # presses to the button, not here, so this is mostly redundant).
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if not isinstance(child, QPushButton):
                self.open_requested.emit(self._job_id)
                return
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# ExportJobEditor  (renamed from ExportJobCard)
# ---------------------------------------------------------------------------

class ExportJobEditor(QWidget):
    """Single export-job editor with its own scheduler and worker thread.

    Previously named ExportJobCard. Now used as a full-page editor inside
    a QScrollArea. The objectName is kept as "exportCard" so the existing
    QSS rule in theme.qss continues to apply without changes.
    """

    changed          = Signal(object)  # ExportJob — emitted on any field edit
    sync_completed   = Signal(object)  # SyncResult — emitted on successful run
    history_changed  = Signal()        # emitted whenever an entry is added or deleted
    failure_alert    = Signal(str, int)  # (job_name, consecutive_failures) — tray notification

    def __init__(
        self,
        job: ExportJob,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._config = config
        self._job_id: str = job.get("id") or str(uuid.uuid4())
        self._running = False
        self._worker: ExportWorker | None = None
        self._consecutive_failures: int = 0  # reset on success; triggers tray alert at threshold
        self._last_trigger: TriggerType = TriggerType.MANUAL    # set just before export starts
        self._current_trigger: TriggerType = TriggerType.MANUAL  # captured at export start for history
        self._history: list[ExportHistoryEntry] = []

        self._scheduler = SyncScheduler(self)
        self._scheduler.trigger.connect(self._auto_trigger)

        # debounce — save after user stops typing in SQL/name/webhook
        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(DEBOUNCE_SAVE_MS)
        self._query_timer.timeout.connect(self._emit_changed)

        # debounce — syntax check
        self._syntax_timer = QTimer(self)
        self._syntax_timer.setSingleShot(True)
        self._syntax_timer.setInterval(DEBOUNCE_SYNTAX_MS)
        self._syntax_timer.timeout.connect(self._check_syntax)

        self._build_ui()
        self._load_job(job)
        self._apply_schedule()

    # ------------------------------------------------------------------ UI

    @staticmethod
    def _section_break(root: "QVBoxLayout") -> None:
        """Add a horizontal separator with breathing room above and below."""
        root.addSpacing(8)
        root.addWidget(hsep())
        root.addSpacing(8)

    def _build_ui(self) -> None:
        """Compose the editor UI from sub-section builders."""
        self.setObjectName("exportCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        self._build_header(root)
        self._section_break(root)
        self._build_sql_section(root)
        self._section_break(root)
        self._build_webhook_section(root)
        self._section_break(root)
        self._build_schedule_section(root)
        self._build_history_section(root)

    def _build_header(self, root: QVBoxLayout) -> None:
        """Header row: title + status summary + Тест/Запустить buttons."""
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        # Left column: name (title-style) + status summary
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setContentsMargins(0, 0, 0, 0)

        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("cardTitle")
        self._name_edit.setPlaceholderText("Без названия")
        self._name_edit.setStyleSheet(
            f"QLineEdit#cardTitle {{"
            f"  background: transparent;"
            f"  border: 1px solid transparent;"
            f"  padding: 2px 4px;"
            f"  font-size: {Theme.font_size_md}pt;"
            f"  font-weight: {Theme.font_weight_semi};"
            f"  color: {Theme.gray_900};"
            f"  min-height: 22px;"
            f"}}"
            f"QLineEdit#cardTitle:hover {{"
            f"  background: {Theme.gray_50};"
            f"  border-radius: 4px;"
            f"}}"
            f"QLineEdit#cardTitle:focus {{"
            f"  background: {Theme.surface};"
            f"  border: 1px solid {Theme.border_strong};"
            f"  border-radius: 4px;"
            f"}}"
        )
        self._name_edit.editingFinished.connect(self._emit_changed)
        title_col.addWidget(self._name_edit)

        self._status_summary = QLabel("Ещё не запускалось")
        self._status_summary.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"background: transparent; "
            f"padding-left: 4px;"
        )
        title_col.addWidget(self._status_summary)

        hdr.addLayout(title_col, stretch=1)

        # Right column: action buttons (Test + Run only; delete moved to toolbar)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._test_btn = QPushButton("  Тест")
        self._test_btn.setIcon(lucide("terminal", color=Theme.gray_700, size=12))
        self._test_btn.setFixedHeight(28)
        self._test_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._test_btn.setToolTip("Выполнить SQL запрос в тестовом окне")
        self._test_btn.clicked.connect(self._open_test_dialog)
        btn_row.addWidget(self._test_btn)

        self._run_btn = QPushButton("  Запустить")
        self._run_btn.setIcon(lucide("play", color=Theme.gray_900, size=12))
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setFixedHeight(28)
        self._run_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._run_btn.setToolTip("Запустить выгрузку вручную")
        self._run_btn.clicked.connect(self.start_export)
        btn_row.addWidget(self._run_btn)

        hdr.addLayout(btn_row)
        root.addLayout(hdr)

    def _build_sql_section(self, root: QVBoxLayout) -> None:
        """SQL editor + syntax indicator."""
        root.addWidget(HeaderLabel("SQL запрос"))

        self._query_edit = SqlEditor()
        self._query_edit.setPlaceholderText("SELECT … FROM …")
        self._query_edit.setMinimumHeight(200)
        # NO maximumHeight — let it expand to fill available space
        self._query_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._query_edit.textChanged.connect(self._on_query_changed)
        self._query_edit.expand_requested.connect(self._open_sql_in_window)
        root.addWidget(self._query_edit, stretch=1)   # stretch=1 so it takes available space

        # Syntax indicator row (label only — Format/Expand buttons removed)
        syntax_row = QHBoxLayout()
        syntax_row.setSpacing(8)

        self._syntax_lbl = QLabel("")
        self._syntax_lbl.setObjectName("syntaxStatus")
        self._syntax_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent; "
            f"padding-top: 2px;"
        )
        syntax_row.addWidget(self._syntax_lbl)
        syntax_row.addStretch()

        root.addLayout(syntax_row)

    def _build_webhook_section(self, root: QVBoxLayout) -> None:
        """Webhook URL label + input."""
        root.addWidget(HeaderLabel("Webhook URL"))

        self._webhook_edit = QLineEdit()
        self._webhook_edit.setPlaceholderText("https://… (необязательно)")
        self._webhook_edit.editingFinished.connect(self._emit_changed)
        root.addWidget(self._webhook_edit)

    def _build_schedule_section(self, root: QVBoxLayout) -> None:
        """Schedule label + auto checkbox + indented mode/value controls."""
        root.addWidget(HeaderLabel("Расписание"))

        self._sched_check = QCheckBox("Запускать автоматически")
        self._sched_check.setToolTip("Включить автоматическую выгрузку по расписанию")
        self._sched_check.toggled.connect(self._on_sched_changed)
        root.addWidget(self._sched_check)

        sched_controls = QHBoxLayout()
        sched_controls.setContentsMargins(24, 0, 0, 0)   # indent under checkbox
        sched_controls.setSpacing(8)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Ежедневно", "Каждые N часов"])
        self._mode_combo.currentIndexChanged.connect(self._on_sched_changed)
        self._mode_combo.setFixedWidth(180)
        sched_controls.addWidget(self._mode_combo, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._sched_value_edit = QLineEdit()
        self._sched_value_edit.setFixedWidth(100)
        self._sched_value_edit.setPlaceholderText("ЧЧ:ММ")
        self._sched_value_edit.editingFinished.connect(self._on_sched_changed)
        sched_controls.addWidget(self._sched_value_edit, alignment=Qt.AlignmentFlag.AlignVCenter)

        sched_controls.addStretch(1)

        # progress label (shown while export is running, hidden otherwise)
        self._progress_lbl = QLabel()
        self._progress_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        sched_controls.addWidget(self._progress_lbl)

        root.addLayout(sched_controls)

    def _build_history_section(self, root: QVBoxLayout) -> None:
        """Hidden-by-default history group: separator + header row + scroll."""
        self._hist_sep = hsep()
        self._hist_sep.setVisible(False)
        root.addSpacing(4)
        root.addWidget(self._hist_sep)
        root.addSpacing(4)

        self._history_hdr_row = QWidget()
        self._history_hdr_row.setStyleSheet("background: transparent;")
        hdr_layout = QHBoxLayout(self._history_hdr_row)
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(8)

        self._history_hdr = QLabel("История")
        self._history_hdr.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_base}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"background: transparent;"
        )
        hdr_layout.addWidget(self._history_hdr)
        hdr_layout.addStretch()

        self._history_clear_btn = QPushButton("Очистить")
        self._history_clear_btn.setFlat(True)
        self._history_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_clear_btn.setStyleSheet(
            f"QPushButton {{"
            f"  border: none; background: transparent; padding: 0;"
            f"  color: {Theme.gray_500};"
            f"  text-decoration: underline;"
            f"}}"
            f"QPushButton:hover {{ color: {Theme.error}; }}"
        )
        self._history_clear_btn.clicked.connect(self._on_clear_history)
        hdr_layout.addWidget(self._history_clear_btn)

        self._history_hdr_row.setVisible(False)
        root.addWidget(self._history_hdr_row)

        # Inner container with transparent background
        self._history_container = QWidget()
        self._history_container.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(2)

        self._history_scroll = QScrollArea()
        self._history_scroll.setWidget(self._history_container)
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._history_scroll.setMaximumHeight(280)
        self._history_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._history_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._history_scroll.setVisible(False)
        root.addWidget(self._history_scroll)

    # ------------------------------------------------------------------ Load / save

    def job_id(self) -> str:
        return self._job_id

    def to_job(self) -> ExportJob:
        return ExportJob(
            id=self._job_id,
            name=self._name_edit.text().strip(),
            sql_query=self._query_edit.toPlainText().strip(),
            webhook_url=self._webhook_edit.text().strip(),
            schedule_enabled=self._sched_check.isChecked(),
            schedule_mode="hourly" if self._mode_combo.currentIndex() == 1 else "daily",
            schedule_value=self._sched_value_edit.text().strip(),
            history=list(self._history),
        )

    def _load_job(self, job: ExportJob) -> None:
        # Block all signals during programmatic load to avoid spurious saves
        for w in (
            self._query_edit, self._name_edit, self._webhook_edit,
            self._sched_check, self._mode_combo, self._sched_value_edit,
        ):
            w.blockSignals(True)

        self._name_edit.setText(job.get("name", ""))
        self._query_edit.setPlainText(job.get("sql_query", ""))
        self._webhook_edit.setText(job.get("webhook_url", ""))
        self._sched_check.setChecked(bool(job.get("schedule_enabled", False)))
        mode = job.get("schedule_mode", "daily")
        self._mode_combo.setCurrentIndex(1 if mode == "hourly" else 0)
        self._sched_value_edit.setText(job.get("schedule_value", ""))
        self._history = list(job.get("history") or [])

        for w in (
            self._query_edit, self._name_edit, self._webhook_edit,
            self._sched_check, self._mode_combo, self._sched_value_edit,
        ):
            w.blockSignals(False)

        self._update_placeholder()
        self._rebuild_history_ui()
        # Restore status summary from most recent history entry (if any)
        if self._history:
            latest = self._history[0]
            if latest.get("ok"):
                ts_short = (
                    latest.get("ts", "")[11:16]
                    if len(latest.get("ts", "")) >= 16
                    else latest.get("ts", "")
                )
                self._update_status_summary(
                    "ok", f"✓ {latest.get('rows', 0)} строк · {ts_short}"
                )
            else:
                self._update_status_summary(
                    "error", f"✗ {latest.get('err', 'Ошибка')[:70]}"
                )
        # Trigger syntax check after layout settles
        QTimer.singleShot(0, self._check_syntax)

    # ------------------------------------------------------------------ Status summary

    def _update_status_summary(self, kind: str, text: str) -> None:
        """Update the header status line beneath the editor title.
        kind ∈ {'idle', 'ok', 'error', 'running'}
        """
        color_map = {
            "idle":    Theme.gray_500,
            "ok":      Theme.success,
            "error":   Theme.error,
            "running": Theme.info,
        }
        color = color_map.get(kind, Theme.gray_500)
        self._status_summary.setStyleSheet(
            f"color: {color}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"background: transparent; "
            f"padding-left: 4px;"
        )
        self._status_summary.setText(text)

    # ------------------------------------------------------------------ Schedule

    def _on_sched_changed(self) -> None:
        self._update_placeholder()
        self._apply_schedule()
        self._emit_changed()

    def _update_placeholder(self) -> None:
        self._sched_value_edit.setPlaceholderText(
            "N часов" if self._mode_combo.currentIndex() == 1 else "ЧЧ:ММ"
        )

    def _apply_schedule(self) -> None:
        """Start or stop this editor's scheduler based on current UI settings."""
        self._scheduler.stop()
        if not self._sched_check.isChecked():
            return
        mode = "hourly" if self._mode_combo.currentIndex() == 1 else "daily"
        value = self._sched_value_edit.text().strip()
        if not value:
            return
        if mode == "daily":
            if not re.fullmatch(r"\d{1,2}:\d{2}", value):
                return
        else:
            if not value.isdigit() or int(value) < 1:
                return
        self._scheduler.configure(mode, value)  # type: ignore[arg-type]
        self._scheduler.start()
        _log.debug(
            "Job '%s': scheduler started (%s %s)",
            self._name_edit.text().strip() or self._job_id, mode, value,
        )

    def stop_scheduler(self) -> None:
        self._scheduler.stop()

    def stop_timers(self) -> None:
        """Stop the debounce timers — call before deleteLater()."""
        if hasattr(self, "_query_timer") and self._query_timer is not None:
            self._query_timer.stop()
        if hasattr(self, "_syntax_timer") and self._syntax_timer is not None:
            self._syntax_timer.stop()

    # ------------------------------------------------------------------ SQL validation

    def _on_query_changed(self) -> None:
        self._query_timer.start()
        self._syntax_timer.start()

    def _check_syntax(self) -> None:
        sql = self._query_edit.toPlainText().strip()
        if not sql:
            self._syntax_lbl.setText("")
            return
        ok, msg = _validate_sql(sql)
        if ok:
            self._syntax_lbl.setStyleSheet(
                f"color: {Theme.success}; "
                f"font-size: {Theme.font_size_xs}pt; "
                f"background: transparent;"
            )
            self._syntax_lbl.setText("✓ SQL")
            self._syntax_lbl.setToolTip("")
        else:
            self._syntax_lbl.setStyleSheet(
                f"color: {Theme.error}; "
                f"font-size: {Theme.font_size_xs}pt; "
                f"background: transparent;"
            )
            short = msg if len(msg) <= 36 else msg[:33] + "…"
            self._syntax_lbl.setText(f"✗ {short}")
            self._syntax_lbl.setToolTip(msg)

    @Slot()
    def _open_sql_in_window(self) -> None:
        """Open the SQL editor in a large standalone dialog."""
        from app.ui.sql_editor import SqlEditorDialog

        def _format(sql: str) -> str:
            try:
                statements = sqlglot.transpile(sql, read="tsql", write="tsql", pretty=True)
                if statements:
                    return ";\n\n".join(statements).rstrip(";\n") + ";"
            except Exception:
                pass
            return sql

        dialog = SqlEditorDialog(
            self._query_edit.toPlainText(),
            parent=self,
            on_format=_format,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._query_edit.setPlainText(dialog.text())

    # ------------------------------------------------------------------ Export

    @Slot()
    def _auto_trigger(self) -> None:
        """Called by scheduler — marks trigger as scheduled then fires export."""
        self._last_trigger = TriggerType.SCHEDULED
        if not self._running:
            self._start_export()

    def start_export(self) -> None:
        """Public API — manual trigger; idempotent."""
        if not self._running:
            self._last_trigger = TriggerType.MANUAL
            self._start_export()

    def _start_export(self) -> None:
        if self._running:
            return
        self._running = True
        self._current_trigger = self._last_trigger  # capture for history entry
        self._run_btn.setEnabled(False)
        self._progress_lbl.setText("Запуск…")
        self._update_status_summary("running", "Запуск…")

        job = self.to_job()
        base_cfg = self._config.load()

        worker = ExportWorker(base_cfg, job)
        run_worker(
            self,
            worker,
            pin_attr="_worker",
            on_finished=self._on_finished,
            on_error=self._on_error,
        )
        # `progress` is a streaming signal — wired manually (run_worker only
        # handles the terminal finished/error signals).
        worker.progress.connect(self._on_progress)

    # ------------------------------------------------------------------ Worker slots

    @Slot(int, str)
    def _on_progress(self, _step: int, description: str) -> None:
        self._progress_lbl.setText(description)
        self._update_status_summary("running", description)

    @Slot(object)
    def _on_finished(self, result: SyncResult) -> None:
        self._running = False
        self._run_btn.setEnabled(True)
        self._progress_lbl.setText("")
        if result.success:
            self._consecutive_failures = 0
            ts_clock = result.timestamp.strftime("%H:%M:%S")
            ts_full  = result.timestamp.strftime("%Y-%m-%d %H:%M")
            self._update_status_summary(
                "ok", f"✓ {result.rows_synced} строк · {ts_clock}"
            )
            self._add_history_entry(ok=True, rows=result.rows_synced, ts=ts_full)
            self.sync_completed.emit(result)
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self.failure_alert.emit(
                    self.to_job().get("name") or "Без названия",
                    self._consecutive_failures,
                )

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._running = False
        self._run_btn.setEnabled(True)
        self._progress_lbl.setText("")
        self._update_status_summary("error", f"✗ {msg[:70]}")
        ts_full = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._add_history_entry(ok=False, err=msg, ts=ts_full)
        self._consecutive_failures += 1
        if self._consecutive_failures >= 3:
            self.failure_alert.emit(
                self.to_job().get("name") or "Без названия",
                self._consecutive_failures,
            )

    # ------------------------------------------------------------------ History data

    def _add_history_entry(
        self, *, ok: bool, ts: str, rows: int = 0, err: str = ""
    ) -> None:
        entry: ExportHistoryEntry = {
            "ts":      ts,
            "trigger": self._current_trigger.value,
            "ok":      ok,
            "rows":    rows,
            "err":     err,
        }
        self._history.insert(0, entry)          # newest first
        if len(self._history) > HISTORY_MAX:
            self._history = self._history[:HISTORY_MAX]
        self._rebuild_history_ui()
        self._emit_changed()
        self.history_changed.emit()

    def _delete_history(self, index: int) -> None:
        if 0 <= index < len(self._history):
            self._history.pop(index)
            self._rebuild_history_ui()
            self._emit_changed()
            self.history_changed.emit()

    @Slot()
    def _on_clear_history(self) -> None:
        """Clear all history entries for this editor after confirmation."""
        if not self._history:
            return
        reply = QMessageBox.question(
            self,
            "Очистить историю",
            f"Удалить все записи истории ({len(self._history)})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._history.clear()
            self._rebuild_history_ui()
            self._emit_changed()
            self.history_changed.emit()

    # ------------------------------------------------------------------ History UI

    def _rebuild_history_ui(self) -> None:
        """Clear and repopulate history rows; show/hide section accordingly."""
        # Remove all existing row widgets
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        has = bool(self._history)
        self._hist_sep.setVisible(has)
        self._history_hdr_row.setVisible(has)
        self._history_scroll.setVisible(has)
        if has:
            self._history_hdr.setText(f"История ({len(self._history)})")
            for i, entry in enumerate(self._history):
                row = HistoryRow(entry, i, self)
                row.delete_requested.connect(self._delete_history)
                self._history_layout.addWidget(row)

    # ------------------------------------------------------------------ Test dialog

    def _open_test_dialog(self) -> None:
        sql = self._query_edit.toPlainText().strip()
        cfg = self._config.load()
        dialog = TestRunDialog(
            cfg,
            initial_sql=sql,
            auto_run=bool(sql),   # execute immediately if SQL is present
            parent=self,
        )
        dialog.test_completed.connect(self._on_test_completed)
        dialog.exec()

    @Slot(bool, int, str)
    def _on_test_completed(self, ok: bool, rows: int, err: str) -> None:
        """Record a TestRunDialog run as a TEST-trigger history entry."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        saved = self._current_trigger
        self._current_trigger = TriggerType.TEST
        try:
            self._add_history_entry(ok=ok, ts=ts, rows=rows, err=err)
        finally:
            self._current_trigger = saved

    # ------------------------------------------------------------------ Signals

    def _emit_changed(self) -> None:
        self.changed.emit(self.to_job())


# ---------------------------------------------------------------------------
# ExportJobsWidget
# ---------------------------------------------------------------------------

class ExportJobsWidget(QWidget):
    """Container for export jobs: list of tiles + detail editor pages."""

    sync_completed  = Signal(object)  # SyncResult — bubbled up from any editor
    history_changed = Signal()         # bubbled up from any editor
    failure_alert   = Signal(str, int)  # (job_name, consecutive_count) — wire to tray in MainWindow

    def __init__(self, config: ConfigManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._tiles: list[ExportJobTile] = []
        self._editors: dict[str, ExportJobEditor] = {}
        self._current_editor_id: str | None = None
        self._build_ui()
        self._load_jobs()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._tiles_page = self._build_tiles_page()
        self._editor_page = self._build_editor_page()
        self._stack.addWidget(self._tiles_page)   # index 0
        self._stack.addWidget(self._editor_page)  # index 1

    def _build_tiles_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setObjectName("exportToolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 12, 16, 12)
        tb.setSpacing(8)

        title = QLabel("Выгрузки")
        title.setStyleSheet(
            f"font-size: {Theme.font_size_lg}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"color: {Theme.gray_900};"
        )
        tb.addWidget(title)
        tb.addStretch()

        add_btn = QPushButton("  Добавить")
        add_btn.setObjectName("primaryBtn")
        add_btn.setIcon(lucide("plus", color=Theme.gray_900, size=14))
        add_btn.setFixedHeight(28)
        add_btn.clicked.connect(self._add_new_job)
        tb.addWidget(add_btn)

        layout.addWidget(toolbar)
        layout.addWidget(hsep())

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll, stretch=1)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        scroll.setWidget(self._grid_container)

        # Use QGridLayout; reflow handled in eventFilter
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(16, 16, 16, 16)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # Empty state placed in row 0, col 0
        self._empty_lbl = QLabel(
            "Нет настроенных выгрузок.\nНажмите «Добавить» чтобы создать первую."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {Theme.gray_400}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"padding: 48px 0;"
        )
        self._grid_layout.addWidget(self._empty_lbl, 0, 0)

        # Reflow on resize
        scroll.viewport().installEventFilter(self)
        self._grid_scroll = scroll

        return page

    def _build_editor_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Editor toolbar with back button
        toolbar = QWidget()
        toolbar.setObjectName("exportToolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(8, 8, 16, 8)
        tb.setSpacing(8)

        back_btn = QPushButton("  Назад к списку")
        back_btn.setIcon(lucide("arrow-left", color=Theme.gray_700, size=14))
        back_btn.setFixedHeight(28)
        back_btn.setStyleSheet(
            "QPushButton {"
            f"  border: 1px solid transparent;"
            f"  background: transparent;"
            f"  color: {Theme.gray_700};"
            f"  padding: 0 10px;"
            f"  border-radius: 5px;"
            "}"
            f"QPushButton:hover {{"
            f"  background-color: {Theme.gray_100};"
            f"}}"
        )
        back_btn.clicked.connect(self._show_tiles)
        tb.addWidget(back_btn)
        tb.addStretch()

        # Delete button on the right of the editor toolbar
        del_btn = QPushButton("  Удалить выгрузку")
        del_btn.setIcon(lucide("trash-2", color=Theme.error, size=14))
        del_btn.setFixedHeight(28)
        del_btn.setStyleSheet(
            "QPushButton {"
            f"  border: 1px solid transparent;"
            f"  background: transparent;"
            f"  color: {Theme.error};"
            f"  padding: 0 10px;"
            f"  border-radius: 5px;"
            "}"
            f"QPushButton:hover {{"
            f"  background-color: {Theme.error_bg};"
            f"  border-color: {Theme.error};"
            f"}}"
        )
        del_btn.clicked.connect(self._delete_current_editor)
        tb.addWidget(del_btn)

        layout.addWidget(toolbar)
        layout.addWidget(hsep())

        # Internal QStackedWidget — one page per editor (no re-parenting)
        self._editor_stack = QStackedWidget()
        self._editor_scrolls: dict[str, QScrollArea] = {}
        layout.addWidget(self._editor_stack, stretch=1)

        return page

    # ------------------------------------------------------------------ Reflow

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._grid_scroll.viewport() and event.type() == event.Type.Resize:
            self._reflow_tiles()
        return super().eventFilter(obj, event)

    def _reflow_tiles(self) -> None:
        """Re-position tiles in a grid based on container width."""
        if not self._tiles:
            return
        viewport_w = self._grid_scroll.viewport().width()
        # Minus container margins (16 left + 16 right)
        avail = viewport_w - 32
        cols = max(1, (avail + self._grid_layout.spacing()) // (ExportJobTile.TILE_W + self._grid_layout.spacing()))
        # Remove all tiles from grid (leave empty label in place)
        for tile in self._tiles:
            self._grid_layout.removeWidget(tile)
        # Re-add at proper grid positions
        for idx, tile in enumerate(self._tiles):
            r, c = divmod(idx, int(cols))
            self._grid_layout.addWidget(tile, r, c)

    # ------------------------------------------------------------------ Jobs CRUD

    def _load_jobs(self) -> None:
        cfg = self._config.load()
        raw_jobs: list[dict] = cfg.get("export_jobs") or []  # type: ignore[assignment]
        for raw in raw_jobs:
            job = ExportJob(
                id=raw.get("id", str(uuid.uuid4())),
                name=raw.get("name", ""),
                sql_query=raw.get("sql_query", ""),
                webhook_url=raw.get("webhook_url", ""),
                schedule_enabled=bool(raw.get("schedule_enabled", False)),
                schedule_mode=raw.get("schedule_mode", "daily"),
                schedule_value=raw.get("schedule_value", ""),
                history=list(raw.get("history") or []),  # type: ignore[typeddict-item]
            )
            self._add_tile(job)
            # Pre-create the editor so the scheduler runs even when not in
            # the editor view — same as the old ExportJobCard which lived
            # in the layout permanently.
            self._editors[job["id"]] = self._create_editor(job)
        self._refresh_empty()
        self._reflow_tiles()

    def _save_jobs(self) -> None:
        cfg = self._config.load()
        # Save the live state from each editor (which is the source of truth)
        cfg["export_jobs"] = [ed.to_job() for ed in self._editors.values()]  # type: ignore[typeddict-unknown-key]
        self._config.save(cfg)
        # Refresh the corresponding tile labels
        for ed in self._editors.values():
            job = ed.to_job()
            for tile in self._tiles:
                if tile.job_id() == job.get("id"):
                    tile.update_from_job(job)
                    break

    def _add_new_job(self) -> None:
        job = ExportJob(
            id=str(uuid.uuid4()),
            name="",
            sql_query="",
            webhook_url="",
            schedule_enabled=False,
            schedule_mode="daily",
            schedule_value="",
            history=[],  # type: ignore[typeddict-unknown-key]
        )
        self._add_tile(job)
        self._editors[job["id"]] = self._create_editor(job)
        self._save_jobs()
        self._refresh_empty()
        self._reflow_tiles()
        # Open the editor immediately so the user can fill in the name/SQL
        self._show_editor(job["id"])

    def _add_tile(self, job: ExportJob) -> None:
        tile = ExportJobTile(job, self)
        tile.open_requested.connect(self._show_editor)
        tile.run_requested.connect(self._run_job)
        tile.delete_requested.connect(self._on_tile_delete)
        self._tiles.append(tile)
        # Initial position; _reflow_tiles will fix placement
        self._grid_layout.addWidget(tile, len(self._tiles) - 1, 0)

    def _create_editor(self, job: ExportJob) -> ExportJobEditor:
        editor = ExportJobEditor(job, self._config, self)
        editor.changed.connect(lambda _j: self._save_jobs())
        editor.history_changed.connect(self.history_changed)
        editor.history_changed.connect(self._save_jobs)
        editor.sync_completed.connect(self.sync_completed)
        editor.failure_alert.connect(self.failure_alert)

        # Wrap in a container with padding, then in a QScrollArea page
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(0)
        cl.addWidget(editor, stretch=1)   # editor takes ALL extra space — no addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(container)

        self._editor_stack.addWidget(scroll)
        self._editor_scrolls[job.get("id", "")] = scroll

        return editor

    @Slot(str)
    def _show_editor(self, job_id: str) -> None:
        editor = self._editors.get(job_id)
        if editor is None:
            return
        scroll = self._editor_scrolls.get(job_id)
        if scroll is None:
            return
        self._editor_stack.setCurrentWidget(scroll)
        self._current_editor_id = job_id
        self._stack.setCurrentIndex(1)

    @Slot()
    def _show_tiles(self) -> None:
        self._current_editor_id = None
        self._stack.setCurrentIndex(0)
        # Refresh tile labels to reflect any edits made in the editor
        for ed in self._editors.values():
            job = ed.to_job()
            for tile in self._tiles:
                if tile.job_id() == job.get("id"):
                    tile.update_from_job(job)
                    break

    @Slot()
    def _delete_current_editor(self) -> None:
        if self._current_editor_id is None:
            return
        self._on_tile_delete(self._current_editor_id)

    @Slot(str)
    def _run_job(self, job_id: str) -> None:
        editor = self._editors.get(job_id)
        if editor is not None:
            editor.start_export()

    @Slot(str)
    def _on_tile_delete(self, job_id: str) -> None:
        editor = self._editors.get(job_id)
        if editor is not None and getattr(editor, "_running", False):
            QMessageBox.warning(
                self,
                "Выгрузка выполняется",
                "Дождитесь завершения выгрузки перед удалением.",
            )
            return
        name = "без названия"
        if editor is not None:
            name = editor.to_job().get("name") or "без названия"
        reply = QMessageBox.question(
            self,
            "Удалить выгрузку",
            f"Удалить выгрузку «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # Stop scheduler, remove editor + scroll page from internal stack
        if editor is not None:
            editor.stop_scheduler()
            editor.stop_timers()         # stop debounce timers before deleteLater()
            scroll = self._editor_scrolls.pop(job_id, None)
            if scroll is not None:
                self._editor_stack.removeWidget(scroll)
                scroll.deleteLater()
            editor.deleteLater()
            del self._editors[job_id]
        for tile in list(self._tiles):
            if tile.job_id() == job_id:
                self._tiles.remove(tile)
                self._grid_layout.removeWidget(tile)
                tile.deleteLater()
                break
        # If the deleted job was the one currently shown in the editor,
        # navigate back to the tiles list
        if self._current_editor_id == job_id:
            self._show_tiles()
        self._save_jobs()
        self._refresh_empty()
        self._reflow_tiles()
        self.history_changed.emit()

    def _refresh_empty(self) -> None:
        self._empty_lbl.setVisible(len(self._tiles) == 0)

    # ------------------------------------------------------------------ Public

    def stop_all_schedulers(self) -> None:
        """Stop all per-job schedulers — call on app shutdown."""
        for editor in self._editors.values():
            editor.stop_scheduler()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Safety net: stop schedulers + timers if the widget is closed
        independently of the app's normal aboutToQuit cleanup hook."""
        self.stop_all_schedulers()
        for editor in self._editors.values():
            editor.stop_timers()
        super().closeEvent(event)
