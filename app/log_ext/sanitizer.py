"""Shim: ``app.log_ext.sanitizer`` → :mod:`app.core.log_sanitizer`."""

from __future__ import annotations

from app.core.log_sanitizer import *  # noqa: F401,F403
from app.core import log_sanitizer as _legacy

__all__ = [name for name in dir(_legacy) if not name.startswith("_")]
