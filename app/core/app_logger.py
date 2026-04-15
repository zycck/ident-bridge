"""Thread-safe logging bridge: Python logging → Qt signal → UI."""
from __future__ import annotations

import collections
import logging

from PySide6.QtCore import QObject, Signal

from app.core.constants import LOG_RING_BUFFER

_FMT  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DFMT = "%H:%M:%S"


class _Bridge(QObject):
    """QObject wrapper so we can emit signals from a plain Handler."""
    message = Signal(str)


class QtLogHandler(logging.Handler):
    """Routes Python log records to a Qt signal — safe across threads."""

    def __init__(self) -> None:
        super().__init__()
        self._bridge = _Bridge()
        self._buffer: collections.deque[str] = collections.deque(maxlen=LOG_RING_BUFFER)
        self.setFormatter(logging.Formatter(_FMT, _DFMT))

    @property
    def message(self) -> Signal:
        return self._bridge.message  # type: ignore[return-value]

    @property
    def history(self) -> list[str]:
        """Snapshot of buffered log lines, oldest first."""
        return list(self._buffer)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
            self._buffer.append(text)
            self._bridge.message.emit(text)
        except Exception:
            self.handleError(record)


# ── Singleton ────────────────────────────────────────────────────────────────

_handler: QtLogHandler | None = None


def setup() -> QtLogHandler:
    """Install handler on root logger. Call once at startup."""
    global _handler
    if _handler is None:
        _handler = QtLogHandler()
        fmt = logging.Formatter(_FMT, _DFMT)

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        root.addHandler(_handler)

        stderr_handler = logging.StreamHandler()
        stderr_handler.setFormatter(fmt)
        root.addHandler(stderr_handler)

    return _handler


def get_handler() -> QtLogHandler:
    return _handler if _handler is not None else setup()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
