"""Self-update helpers — canonical path.

Split into three future submodules (github_release / download / apply)
in the Stage 5 final wave. For now the whole surface is re-exported
from :mod:`app.core.updater`.
"""

from __future__ import annotations

from app.core.updater import *  # noqa: F401,F403
from app.core import updater as _legacy

__all__ = [name for name in dir(_legacy) if not name.startswith("_")]
