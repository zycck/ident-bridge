"""SQL Server section extracted from SettingsWidget."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.lucide_icons import lucide
from app.ui.theme import Theme
from app.ui.widgets import labeled_row, section, status_label, style_combo_popup


class SettingsSqlPanel(QWidget):
    scan_requested = Signal()
    refresh_databases_requested = Signal()
    test_connection_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sql_box, sql_lay = section("SQL Server")

        self._instance_combo = QComboBox()
        style_combo_popup(self._instance_combo)
        self._instance_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._instance_combo.setEditable(True)

        self._scan_btn = QPushButton("  Сканировать")
        self._scan_btn.setIcon(lucide("search", color=Theme.gray_700, size=14))
        self._scan_btn.clicked.connect(self.scan_requested)

        inst_row = QHBoxLayout()
        inst_row.setSpacing(6)
        inst_lbl = QLabel("SQL Instance")
        inst_lbl.setFixedWidth(100)
        inst_lbl.setStyleSheet("color: #9CA3AF;")
        inst_row.addWidget(inst_lbl)
        inst_row.addWidget(self._instance_combo, stretch=1)
        inst_row.addWidget(self._scan_btn)
        sql_lay.addLayout(inst_row)

        self._db_combo = QComboBox()
        style_combo_popup(self._db_combo)
        self._db_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        self._refresh_db_btn = QPushButton()
        self._refresh_db_btn.setIcon(
            lucide("refresh-cw", color=Theme.gray_700, size=14)
        )
        self._refresh_db_btn.setFixedWidth(28)
        self._refresh_db_btn.setToolTip("Обновить список баз данных")
        self._refresh_db_btn.clicked.connect(self.refresh_databases_requested)

        db_row = QHBoxLayout()
        db_row.setSpacing(6)
        db_lbl = QLabel("База данных")
        db_lbl.setFixedWidth(100)
        db_lbl.setStyleSheet("color: #9CA3AF;")
        db_row.addWidget(db_lbl)
        db_row.addWidget(self._db_combo, stretch=1)
        db_row.addWidget(self._refresh_db_btn)
        sql_lay.addLayout(db_row)

        self._login_edit = QLineEdit()
        self._login_edit.setPlaceholderText("sa")
        sql_lay.addLayout(labeled_row("Логин", self._login_edit))

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("••••••")
        sql_lay.addLayout(labeled_row("Пароль", self._password_edit))

        self._test_conn_btn = QPushButton("  Тест подключения")
        self._test_conn_btn.setObjectName("primaryBtn")
        self._test_conn_btn.setIcon(lucide("zap", color=Theme.gray_900, size=14))
        self._test_conn_btn.clicked.connect(self.test_connection_requested)
        sql_lay.addWidget(self._test_conn_btn)

        self._conn_status = status_label()
        sql_lay.addWidget(self._conn_status)

        root.addWidget(sql_box)

    def instance_combo(self) -> QComboBox:
        return self._instance_combo

    def database_combo(self) -> QComboBox:
        return self._db_combo

    def login_edit(self) -> QLineEdit:
        return self._login_edit

    def password_edit(self) -> QLineEdit:
        return self._password_edit

    def conn_status(self) -> QLabel:
        return self._conn_status

    def scan_button(self) -> QPushButton:
        return self._scan_btn

    def refresh_databases_button(self) -> QPushButton:
        return self._refresh_db_btn

    def test_connection_button(self) -> QPushButton:
        return self._test_conn_btn
