"""Shim: ``app.platform.dpapi`` → :mod:`app.core.dpapi`.

New call-sites should import from this path; legacy call-sites keep
working thanks to the original module still being present.
"""

from __future__ import annotations

from app.core.dpapi import *  # noqa: F401,F403
from app.core import dpapi as _legacy

__all__ = [name for name in dir(_legacy) if not name.startswith("_")]
