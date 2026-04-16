from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.ui.error_dialog_controller import (
    build_exception_traceback,
    install_global_handler as _install_global_handler,
)
from app.ui.theme import Theme

# Note: INotifier integration removed in Phase 1 refactor — re-introduce via
# DI (constructor injection) if a notification channel comes back.

class ErrorDialog(QDialog):
    def __init__(
        self,
        exc: BaseException,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)

        self._traceback_text: str = build_exception_traceback(exc)

        self.setWindowTitle("Ошибка приложения")
        self.setMinimumSize(600, 400)
        self.resize(660, 440)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # -- Header label --------------------------------------------------
        header = QLabel("Произошла непредвиденная ошибка:")
        header.setStyleSheet(f"color: {Theme.error}; font-weight: bold; font-size: 13px;")
        root.addWidget(header)

        # -- Traceback viewer ----------------------------------------------
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        font = QFont("Courier New", 9)
        viewer.setFont(font)
        viewer.setPlainText(self._traceback_text)
        root.addWidget(viewer, stretch=1)

        # -- Button row ----------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        copy_btn = QPushButton("Копировать")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(copy_btn)

        btn_row.addStretch()

        close_btn = QPushButton("Закрыть")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    def _copy_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._traceback_text)
def install_global_handler() -> None:
    """Replace sys.excepthook with one that shows ErrorDialog and logs to disk."""
    _install_global_handler(dialog_factory=ErrorDialog)
