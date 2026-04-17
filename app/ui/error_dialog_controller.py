"""Infrastructure helpers extracted from ErrorDialog."""

import sys
import traceback
from collections.abc import Callable
from types import TracebackType
from typing import Any

from PySide6.QtWidgets import QApplication

from app.ui.error_dialog_helpers import append_error_log


def build_exception_traceback(exc: BaseException) -> str:
    """Format a traceback for a concrete exception instance."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def build_traceback_text(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> str:
    """Format a traceback from a raw excepthook triple."""
    return "".join(traceback.format_exception(exc_type, exc, tb))


def install_global_handler(
    *,
    dialog_factory: Callable[[BaseException], Any],
    append_error_log_fn: Callable[[str], None] = append_error_log,
    app_instance_fn: Callable[[], Any] = QApplication.instance,
    sys_module: Any = sys,
) -> None:
    """Replace ``sys.excepthook`` with a dialog + log based handler."""

    def _hook(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        tb_text = build_traceback_text(exc_type, exc, tb)
        append_error_log_fn(tb_text)

        if app_instance_fn() is not None:
            dialog = dialog_factory(exc)
            dialog.exec()

    sys_module.excepthook = _hook
