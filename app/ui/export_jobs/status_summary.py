"""Shared status summaries for export job journal state."""

from collections.abc import Iterable

from app.export.run_store import ExportRunInfo
from app.ui.export_editor_runtime import format_short_user_error, normalize_short_user_error
from app.ui.theme import Theme

_DEFAULT_UNFINISHED_ERROR = "\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0430 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0430\u0441\u044c \u0441 \u043e\u0448\u0438\u0431\u043a\u043e\u0439"


def latest_unfinished_run(runs: Iterable[object]) -> ExportRunInfo | None:
    for run in runs:
        if isinstance(run, ExportRunInfo):
            return run
    return None


def build_unfinished_run_status(
    run: ExportRunInfo,
    *,
    max_error_length: int | None = None,
) -> tuple[str, str, str]:
    progress = _chunk_progress_text(run)

    if run.status == "planned":
        return "warning", f"\u041d\u0435 \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u043e \u00b7 {progress}", Theme.warning

    if run.status == "running":
        return "warning", f"\u041e\u0431\u043e\u0440\u0432\u0430\u043d\u043e \u00b7 {progress}", Theme.warning

    error_text = (
        format_short_user_error(run.last_error or _DEFAULT_UNFINISHED_ERROR, max_length=max_error_length)
        if max_error_length is not None
        else normalize_short_user_error(run.last_error or _DEFAULT_UNFINISHED_ERROR)
    )
    suffix = f" \u00b7 {progress}" if run.total_chunks > 1 else ""
    return "error", f"\u2715 {error_text}{suffix}", Theme.error


def _chunk_progress_text(run: ExportRunInfo) -> str:
    total_chunks = max(1, int(run.total_chunks))
    delivered_chunks = min(max(0, int(run.delivered_chunks)), total_chunks)
    return f"{delivered_chunks}/{total_chunks} \u0447\u0430\u043d\u043a\u043e\u0432"
