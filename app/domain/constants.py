"""Domain-level constants (timings, limits, metadata).

Re-exports the constant names still defined in :mod:`app.core.constants`
so new call-sites can import from the canonical
``app.domain.constants`` path.
"""

from __future__ import annotations

from app.core.constants import *  # noqa: F401,F403
from app.core import constants as _legacy

# Rebind module-level __all__ so `from app.domain.constants import *` works.
__all__ = [name for name in dir(_legacy) if not name.startswith("_")]
