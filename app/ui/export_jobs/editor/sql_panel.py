"""SQL editor section for ExportJobEditor."""

from PySide6.QtCore import QSignalBlocker, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.export.sql_templates import export_job_sql_templates, get_export_job_sql_template
from app.ui.export_sql import format_sql_for_tsql_editor, validate_sql
from app.ui.sql_editor import SqlEditor
from app.ui.theme import Theme
from app.ui.widgets import HeaderLabel, style_menu_popup


class ExportSqlPanel(QWidget):
    """Owns SQL text editing and syntax status display."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(HeaderLabel("\u0053\u0051\u004c \u0437\u0430\u043f\u0440\u043e\u0441"))
        title_row.addStretch()

        self._template_btn = QPushButton("\u0428\u0430\u0431\u043b\u043e\u043d\u044b SQL", self)
        self._template_btn.setToolTip(
            "\u0412\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u0433\u043e\u0442\u043e\u0432\u044b\u0439 SQL-\u0448\u0430\u0431\u043b\u043e\u043d"
        )
        self._template_btn.setStyleSheet(
            f"QPushButton {{"
            f"  min-height: 28px;"
            f"  padding: 0 12px;"
            f"  border: 1px solid {Theme.border_strong};"
            f"  border-radius: {Theme.radius}px;"
            f"  background-color: {Theme.surface};"
            f"  color: {Theme.gray_700};"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {Theme.gray_50};"
            f"  border-color: {Theme.border_focus};"
            f"  color: {Theme.primary_800};"
            f"}}"
        )
        self._template_btn.clicked.connect(self._show_template_menu)
        title_row.addWidget(self._template_btn)
        root.addLayout(title_row)

        self._template_menu = QMenu(self)
        style_menu_popup(self._template_menu)
        self._template_actions = {}
        for template in export_job_sql_templates():
            action = self._template_menu.addAction(template.label)
            action.triggered.connect(
                lambda _checked=False, key=template.key: self._apply_template(key)
            )
            self._template_actions[template.key] = action

        self._query_edit = SqlEditor()
        self._query_edit.setPlaceholderText("SELECT ... FROM ...")
        self._query_edit.setMinimumHeight(200)
        self._query_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._query_edit.textChanged.connect(self.changed)
        self._query_edit.expand_requested.connect(self._open_in_window)
        root.addWidget(self._query_edit, stretch=1)

        syntax_row = QHBoxLayout()
        syntax_row.setSpacing(8)

        self._syntax_lbl = QLabel("")
        self._syntax_lbl.setObjectName("syntaxStatus")
        self._syntax_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent; "
            f"padding-top: 2px;"
        )
        syntax_row.addWidget(self._syntax_lbl)
        syntax_row.addStretch()

        root.addLayout(syntax_row)

    def sql_text(self) -> str:
        return self._query_edit.toPlainText().strip()

    def set_sql_text(self, sql: str) -> None:
        with QSignalBlocker(self._query_edit):
            self._query_edit.setPlainText(sql)

    def refresh_syntax(self) -> None:
        sql = self.sql_text()
        if not sql:
            self._syntax_lbl.setText("")
            self._syntax_lbl.setToolTip("")
            return
        ok, msg = validate_sql(sql)
        if ok:
            self._syntax_lbl.setStyleSheet(
                f"color: {Theme.success}; "
                f"font-size: {Theme.font_size_xs}pt; "
                f"background: transparent;"
            )
            self._syntax_lbl.setText("\u2713 SQL")
            self._syntax_lbl.setToolTip("")
            return
        self._syntax_lbl.setStyleSheet(
            f"color: {Theme.error}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        short = msg if len(msg) <= 36 else msg[:33] + "..."
        self._syntax_lbl.setText(f"\u2717 {short}")
        self._syntax_lbl.setToolTip(msg)

    @Slot()
    def _open_in_window(self) -> None:
        from app.ui.sql_editor import SqlEditorDialog

        dialog = SqlEditorDialog(
            self._query_edit.toPlainText(),
            parent=self,
            on_format=format_sql_for_tsql_editor,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._query_edit.setPlainText(dialog.text())

    @Slot()
    def _show_template_menu(self) -> None:
        self._template_menu.exec(
            self._template_btn.mapToGlobal(self._template_btn.rect().bottomLeft())
        )

    def _apply_template(self, key: str) -> None:
        template = get_export_job_sql_template(key)
        self._query_edit.setPlainText(template.sql)
        self.refresh_syntax()
