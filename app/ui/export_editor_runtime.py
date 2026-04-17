"""Runtime state helpers for ExportJobEditor."""

from dataclasses import dataclass
from datetime import datetime

from app.config import ExportHistoryEntry, SyncResult, TriggerType


@dataclass(frozen=True)
class ExportEditorRuntimeUpdate:
    """UI-facing outcome for a completed export editor state transition."""

    status_kind: str
    status_text: str
    entry: ExportHistoryEntry
    alert_count: int | None = None


class ExportEditorRuntimeState:
    """Owns trigger/failure/history bookkeeping for ExportJobEditor."""

    def __init__(self) -> None:
        self._last_trigger = TriggerType.MANUAL
        self._current_trigger = TriggerType.MANUAL
        self.consecutive_failures = 0

    def mark_manual_trigger(self) -> None:
        self._last_trigger = TriggerType.MANUAL

    def mark_scheduled_trigger(self) -> None:
        self._last_trigger = TriggerType.SCHEDULED

    def begin_run(self) -> tuple[str, str]:
        self._current_trigger = self._last_trigger
        return "running", "Запуск…"

    def on_success(self, result: SyncResult) -> tuple[str, str, ExportHistoryEntry]:
        self.consecutive_failures = 0
        clock = result.timestamp.strftime("%H:%M:%S")
        entry = self._history_entry(
            trigger=self._current_trigger,
            ok=True,
            ts=result.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            rows=result.rows_synced,
        )
        return "ok", f"✓ {result.rows_synced} строк · {clock}", entry

    def on_error(
        self,
        msg: str,
        *,
        now: datetime,
        alert_threshold: int,
    ) -> ExportEditorRuntimeUpdate:
        self.consecutive_failures += 1
        alert_count = None
        if self.consecutive_failures >= alert_threshold:
            alert_count = self.consecutive_failures
        return ExportEditorRuntimeUpdate(
            status_kind="error",
            status_text=f"✗ {msg[:70]}",
            entry=self._history_entry(
                trigger=self._current_trigger,
                ok=False,
                ts=now.strftime("%Y-%m-%d %H:%M:%S"),
                err=msg,
            ),
            alert_count=alert_count,
        )

    def build_test_entry(
        self,
        *,
        ok: bool,
        rows: int,
        err: str,
        now: datetime,
    ) -> ExportHistoryEntry:
        return self._history_entry(
            trigger=TriggerType.TEST,
            ok=ok,
            ts=now.strftime("%Y-%m-%d %H:%M"),
            rows=rows,
            err=err,
        )

    @staticmethod
    def status_from_latest_entry(
        latest: ExportHistoryEntry,
    ) -> tuple[str, str]:
        if latest.get("ok"):
            ts_text = latest.get("ts", "")
            if len(ts_text) >= 19:
                ts_short = ts_text[11:19]
            elif len(ts_text) >= 16:
                ts_short = ts_text[11:16]
            else:
                ts_short = ts_text
            return "ok", f"✓ {latest.get('rows', 0)} строк · {ts_short}"
        return "error", f"✗ {latest.get('err', 'Ошибка')[:70]}"

    @staticmethod
    def _history_entry(
        *,
        trigger: TriggerType,
        ok: bool,
        ts: str,
        rows: int = 0,
        err: str = "",
    ) -> ExportHistoryEntry:
        return {
            "ts": ts,
            "trigger": trigger.value,
            "ok": ok,
            "rows": rows,
            "err": err,
        }
