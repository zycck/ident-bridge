"""Tests for extracted MainWindow debug-window coordination."""

from PySide6.QtWidgets import QWidget

from app.ui.main_window_debug import DebugWindowCoordinator


class _DebugWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.raise_calls = 0
        self.close_calls = 0

    def raise_(self) -> None:  # type: ignore[override]
        self.raise_calls += 1
        super().raise_()

    def close(self) -> bool:  # type: ignore[override]
        self.close_calls += 1
        return super().close()


def test_toggle_creates_window_lazily_and_shows_it(qtbot) -> None:
    created: list[_DebugWidget] = []

    def factory() -> _DebugWidget:
        widget = _DebugWidget()
        qtbot.addWidget(widget)
        created.append(widget)
        return widget

    coordinator = DebugWindowCoordinator(window_factory=factory)

    coordinator.toggle()

    assert len(created) == 1
    assert created[0].isVisible() is True
    assert created[0].raise_calls == 1


def test_toggle_hides_existing_window(qtbot) -> None:
    widget = _DebugWidget()
    qtbot.addWidget(widget)
    coordinator = DebugWindowCoordinator(window_factory=lambda: widget)

    coordinator.toggle()
    coordinator.toggle()

    assert widget.isVisible() is False


def test_close_is_safe_without_window() -> None:
    coordinator = DebugWindowCoordinator(window_factory=_DebugWidget)

    coordinator.close()


def test_close_closes_existing_window(qtbot) -> None:
    widget = _DebugWidget()
    qtbot.addWidget(widget)
    coordinator = DebugWindowCoordinator(window_factory=lambda: widget)
    coordinator.toggle()

    coordinator.close()

    assert widget.close_calls >= 1
