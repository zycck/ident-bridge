"""Process-level resource monitor (CPU / RAM / handles / threads).

Wraps :mod:`psutil` so callers don't have to know about it and so the
value object (:class:`ResourceSample`) is trivial to mock in tests.

The monitor is a :class:`QObject` with a single :class:`~PySide6.QtCore.QTimer`
running on the thread that owns it (typically the GUI thread). On every
tick it samples the current process once (``psutil.Process.oneshot()``
batches the syscalls) and emits :pyattr:`ResourceMonitor.sample` with a
frozen :class:`ResourceSample`.

If :mod:`psutil` is not importable — which we tolerate so unit tests and
non-Windows environments still work — :class:`ResourceMonitor` silently
emits nothing and ``start()`` is a no-op.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

_log = logging.getLogger(__name__)


try:  # pragma: no cover - import availability differs by platform
    import psutil as _psutil
except Exception as exc:  # pragma: no cover
    _psutil = None
    _PSUTIL_IMPORT_ERROR: Exception | None = exc
else:
    _PSUTIL_IMPORT_ERROR = None


@dataclass(slots=True, frozen=True)
class ResourceSample:
    """One-shot snapshot of the current process' resource use.

    Attributes:
        cpu_percent: Per-process CPU usage in percent across all cores
            (``psutil`` convention: ``100 %`` per saturated core).
        rss_bytes: Resident set size in bytes.
        handles: Windows handle count, or 0 on platforms that lack it.
        threads: Live thread count for the process.
    """

    cpu_percent: float
    rss_bytes: int
    handles: int
    threads: int

    @property
    def rss_mib(self) -> float:
        """RSS in MiB (convenience for UI rendering)."""
        return self.rss_bytes / (1024 * 1024)


class ResourceMonitor(QObject):
    """Emits a :class:`ResourceSample` on every timer tick.

    Call :meth:`start` to begin sampling, :meth:`stop` to pause. The
    monitor is cheap — one ``oneshot()`` batched syscall per tick — so
    defaulting to a 1 Hz cadence is fine even on low-power hardware.
    """

    sample = Signal(object)  # ResourceSample

    DEFAULT_INTERVAL_MS = 1000

    def __init__(self, interval_ms: int = DEFAULT_INTERVAL_MS, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(int(interval_ms))
        self._timer.timeout.connect(self._tick)
        self._proc: Any | None = None
        if _psutil is not None:
            try:
                self._proc = _psutil.Process(os.getpid())
                # The first cpu_percent(None) call returns 0.0 by design —
                # prime it so the first real tick returns a meaningful
                # number.
                self._proc.cpu_percent(interval=None)
            except Exception as exc:  # pragma: no cover - defensive
                _log.debug("ResourceMonitor: psutil.Process init failed: %s", exc)
                self._proc = None
        else:  # pragma: no cover - import-time branch
            _log.debug(
                "ResourceMonitor: psutil unavailable, monitor will be inert: %s",
                _PSUTIL_IMPORT_ERROR,
            )

    # ------------------------------------------------------------------

    @property
    def interval_ms(self) -> int:
        return int(self._timer.interval())

    def set_interval_ms(self, interval_ms: int) -> None:
        self._timer.setInterval(int(interval_ms))

    def is_active(self) -> bool:
        return bool(self._timer.isActive())

    def is_available(self) -> bool:
        """True if psutil is usable on this host."""
        return self._proc is not None

    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin periodic sampling. No-op if psutil is unavailable."""
        if self._proc is None:
            return
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        """Stop sampling. Safe to call repeatedly."""
        self._timer.stop()

    # ------------------------------------------------------------------

    def current(self) -> ResourceSample | None:
        """Read one sample synchronously. Returns ``None`` if unavailable."""
        return self._collect()

    def _tick(self) -> None:
        sample = self._collect()
        if sample is not None:
            self.sample.emit(sample)

    def _collect(self) -> ResourceSample | None:
        if self._proc is None or _psutil is None:
            return None
        try:
            with self._proc.oneshot():
                cpu = float(self._proc.cpu_percent(interval=None))
                mem = int(self._proc.memory_info().rss)
                threads = int(self._proc.num_threads())
                num_handles_fn = getattr(self._proc, "num_handles", None)
                if callable(num_handles_fn):
                    try:
                        handles = int(num_handles_fn())
                    except Exception:  # pragma: no cover - per-sample defensive
                        handles = 0
                else:  # non-Windows
                    handles = 0
        except _psutil.Error as exc:  # pragma: no cover - process vanished
            _log.debug("ResourceMonitor: psutil error: %s", exc)
            return None
        return ResourceSample(
            cpu_percent=cpu,
            rss_bytes=mem,
            handles=handles,
            threads=threads,
        )


__all__ = ["ResourceMonitor", "ResourceSample"]
