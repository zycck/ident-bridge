# -*- coding: utf-8 -*-
"""
SqlEditor — QPlainTextEdit with an inline syntax-status chip.

The chip overlays the bottom-right of the editor viewport and shows
sqlglot-validated state: green "✓ SQL" when the statement parses
cleanly, red "✗ <message>" with the first error otherwise. Hidden
when the editor is empty.

The chip is a child of self.viewport() so it doesn't get clipped by
scrollbars; it has WA_TransparentForMouseEvents so clicks pass through
to the underlying text. resizeEvent re-anchors it to the corner.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QWidget

from app.ui.theme import Theme


class SyntaxChip(QLabel):
    """Floating status pill anchored to a parent viewport."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("syntaxChip")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

    def show_ok(self) -> None:
        self.setStyleSheet(
            f"#syntaxChip {{"
            f"  background-color: {Theme.success_bg};"
            f"  color: {Theme.success};"
            f"  border: 1px solid {Theme.success};"
            f"  border-radius: 10px;"
            f"  padding: 2px 10px;"
            f"  font-size: {Theme.font_size_xs}pt;"
            f"  font-weight: {Theme.font_weight_semi};"
            f"}}"
        )
        self.setText("✓ SQL")
        self.setToolTip("")
        self.adjustSize()
        self.show()
        self.raise_()

    def show_error(self, msg: str) -> None:
        self.setStyleSheet(
            f"#syntaxChip {{"
            f"  background-color: {Theme.error_bg};"
            f"  color: {Theme.error};"
            f"  border: 1px solid {Theme.error};"
            f"  border-radius: 10px;"
            f"  padding: 2px 10px;"
            f"  font-size: {Theme.font_size_xs}pt;"
            f"  font-weight: {Theme.font_weight_semi};"
            f"}}"
        )
        # Truncate display, keep full message in tooltip
        short = msg if len(msg) <= 36 else msg[:33] + "…"
        self.setText(f"✗ {short}")
        self.setToolTip(msg)
        self.adjustSize()
        self.show()
        self.raise_()

    def hide_chip(self) -> None:
        self.hide()


class SqlEditor(QPlainTextEdit):
    """QPlainTextEdit with a floating SyntaxChip in the bottom-right."""

    CHIP_MARGIN = 10

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chip = SyntaxChip(self.viewport())
        self._chip.move(0, 0)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition_chip()

    def _reposition_chip(self) -> None:
        if not self._chip.isVisible():
            return
        vp = self.viewport()
        sz: QSize = self._chip.size()
        x = vp.width()  - sz.width()  - self.CHIP_MARGIN
        y = vp.height() - sz.height() - self.CHIP_MARGIN
        self._chip.move(max(0, x), max(0, y))

    def set_syntax(self, ok: bool | None, message: str = "") -> None:
        """
        Update the syntax indicator state.

        ok=True  → green "✓ SQL"
        ok=False → red   "✗ <message>"   (with full message in tooltip)
        ok=None  → hide the chip entirely (use when the editor is empty)
        """
        if ok is None:
            self._chip.hide_chip()
            return
        if ok:
            self._chip.show_ok()
        else:
            self._chip.show_error(message)
        self._reposition_chip()
