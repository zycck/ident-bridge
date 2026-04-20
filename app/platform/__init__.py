"""OS-specific thin wrappers (Windows registry, DPAPI, self-update, …).

Keeps the OS-specific surface area in one place so the rest of the app
depends on ``app.platform``, not on Windows-specific modules directly.
Currently re-exports from :mod:`app.core` until the physical move in
the audit plan's Stage 5 final wave.
"""

from app.platform import dpapi, startup, updater  # noqa: F401

__all__ = ["dpapi", "startup", "updater"]
