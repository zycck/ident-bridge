"""Interaction controller extracted from SqlEditor."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


class SqlEditorInteractionController:
    """Owns expand-button positioning and tab/dedent behavior."""

    def __init__(
        self,
        *,
        editor,
        expand_button,
        tab_spaces: int,
        margin: int,
    ) -> None:
        self._editor = editor
        self._expand_button = expand_button
        self._tab_spaces = tab_spaces
        self._margin = margin

    def reposition_expand_button(self) -> None:
        vp = self._editor.viewport()
        sz = self._expand_button.size()
        x = vp.width() - sz.width() - self._margin
        y = self._margin
        self._expand_button.move(max(0, x), max(0, y))

    def handle_key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Tab and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            cursor = self._editor.textCursor()
            cursor.insertText(" " * self._tab_spaces)
            event.accept()
            return True

        if event.key() == Qt.Key.Key_Backtab:
            cursor = self._editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.StartOfLine)
            line_start = cursor.position()
            block_text = cursor.block().text()
            spaces_to_remove = 0
            for ch in block_text[: self._tab_spaces]:
                if ch == " ":
                    spaces_to_remove += 1
                else:
                    break
            if spaces_to_remove > 0:
                cursor.setPosition(line_start)
                cursor.setPosition(
                    line_start + spaces_to_remove,
                    cursor.MoveMode.KeepAnchor,
                )
                cursor.removeSelectedText()
            event.accept()
            return True

        return False
