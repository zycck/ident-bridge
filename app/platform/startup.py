"""Shim: ``app.platform.startup`` → :mod:`app.core.startup` (Windows autostart)."""

from __future__ import annotations

from app.core.startup import *  # noqa: F401,F403
from app.core import startup as _legacy

__all__ = [name for name in dir(_legacy) if not name.startswith("_")]
