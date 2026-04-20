"""Compact CPU / RAM / handles / threads footer for DebugWindow.

Renders a one-line strip at the bottom of :class:`DebugWindow`, fed by
:class:`app.core.resource_monitor.ResourceMonitor` via the
:pysignal:`~app.core.resource_monitor.ResourceMonitor.sample` signal.

The bar deliberately uses plain QLabels — no QProgressBar, no sparkline
painter — to keep paint cost negligible (updates once per second) and
dependencies zero beyond Qt. A tiny 60-sample deque per metric powers a
very cheap text-based trend (``▁▂▃▄▅▆▇█``) so users can eyeball whether
CPU/RAM are trending up without installing matplotlib.
"""

from collections import deque
from collections.abc import Iterable

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from app.core.resource_monitor import ResourceMonitor, ResourceSample

_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"
_TREND_LEN = 60


def _sparkline(samples: Iterable[float], *, max_value: float | None = None) -> str:
    values = [float(v) for v in samples]
    if not values:
        return ""
    top = max_value if max_value is not None else max(values)
    if top <= 0:
        return _SPARK_BLOCKS[0] * len(values)
    out = []
    scale = len(_SPARK_BLOCKS) - 1
    for v in values:
        v = max(0.0, min(top, v))
        idx = int(round(v / top * scale))
        out.append(_SPARK_BLOCKS[idx])
    return "".join(out)


_STYLE_LABEL = (
    "QLabel { color: #9CA3AF; font-size: 9pt;"
    "         font-family: 'Cascadia Code', Consolas, monospace; }"
)
_STYLE_LABEL_VALUE = (
    "QLabel { color: #D4D4D8; font-size: 9pt; font-weight: 600;"
    "         font-family: 'Cascadia Code', Consolas, monospace; }"
)


class ResourceMonitorBar(QWidget):
    """Footer widget: ``CPU x.x % [spark] │ RAM y MB [spark] │ H n │ T m``."""

    def __init__(self, monitor: ResourceMonitor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._monitor = monitor
        self._cpu_hist: deque[float] = deque(maxlen=_TREND_LEN)
        self._ram_hist: deque[float] = deque(maxlen=_TREND_LEN)

        self._cpu_label = QLabel("CPU —")
        self._cpu_spark = QLabel("")
        self._ram_label = QLabel("RAM —")
        self._ram_spark = QLabel("")
        self._handles_label = QLabel("H —")
        self._threads_label = QLabel("T —")

        for w in (self._cpu_label, self._ram_label,
                  self._handles_label, self._threads_label):
            w.setStyleSheet(_STYLE_LABEL_VALUE)
        for w in (self._cpu_spark, self._ram_spark):
            w.setStyleSheet(_STYLE_LABEL)
            w.setMinimumWidth(60)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(10)
        sep_style = "QLabel { color: #3F3F46; }"

        row.addWidget(self._cpu_label)
        row.addWidget(self._cpu_spark)
        sep1 = QLabel("│"); sep1.setStyleSheet(sep_style); row.addWidget(sep1)
        row.addWidget(self._ram_label)
        row.addWidget(self._ram_spark)
        sep2 = QLabel("│"); sep2.setStyleSheet(sep_style); row.addWidget(sep2)
        row.addWidget(self._handles_label)
        sep3 = QLabel("│"); sep3.setStyleSheet(sep_style); row.addWidget(sep3)
        row.addWidget(self._threads_label)
        row.addStretch(1)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("ResourceMonitorBar { background: #111114; }")

        monitor.sample.connect(self._on_sample)

        if not monitor.is_available():
            self._cpu_label.setText("CPU — (psutil unavailable)")

    # ------------------------------------------------------------------

    @Slot(object)
    def _on_sample(self, sample: object) -> None:
        if not isinstance(sample, ResourceSample):
            return
        self._cpu_hist.append(sample.cpu_percent)
        self._ram_hist.append(sample.rss_mib)

        self._cpu_label.setText(f"CPU {sample.cpu_percent:5.1f} %")
        self._cpu_spark.setText(_sparkline(self._cpu_hist, max_value=100.0))
        self._ram_label.setText(f"RAM {sample.rss_mib:6.1f} MB")
        self._ram_spark.setText(_sparkline(self._ram_hist))
        self._handles_label.setText(f"H {sample.handles}")
        self._threads_label.setText(f"T {sample.threads}")


__all__ = ["ResourceMonitorBar"]
