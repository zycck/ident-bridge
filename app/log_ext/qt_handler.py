"""Shim: ``app.log_ext.qt_handler`` → :mod:`app.core.app_logger`."""

from app.core.app_logger import *  # noqa: F401,F403
from app.core import app_logger as _legacy

__all__ = [name for name in dir(_legacy) if not name.startswith("_")]
