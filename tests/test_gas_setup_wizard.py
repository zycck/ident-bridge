from __future__ import annotations

from app.ui.gas_setup_wizard import GasSetupWizard
from app.ui.theme import Theme


def test_gas_setup_wizard_generates_token_and_returns_library_config(qtbot) -> None:
    dialog = GasSetupWizard()
    qtbot.addWidget(dialog)

    dialog._webhook_url_edit.setText("https://script.google.com/macros/s/library/exec")
    dialog._generate_token()

    selected = dialog.selected_config()

    assert dialog.windowTitle() == "Подключение Google Таблиц"
    assert dialog._generate_btn.text() == "Создать"
    assert dialog._copy_btn.text() == "Копировать"
    assert dialog._apply_btn.text() == "Сохранить"
    assert dialog._cancel_btn.text() == "Отмена"
    assert Theme.surface in dialog.styleSheet()
    assert selected["webhook_url"] == "https://script.google.com/macros/s/library/exec"
    assert selected["auth_token"]
    assert selected["scheme_id"] == "library_v1"


def test_gas_setup_wizard_shows_shim_preview_and_initial_values(qtbot) -> None:
    dialog = GasSetupWizard(
        initial_webhook_url="https://script.google.com/macros/s/existing/exec",
        initial_auth_token="seed-token",
    )
    qtbot.addWidget(dialog)

    assert dialog._intro_label.text().startswith("1. Вставьте адрес обработки.")
    assert dialog._code_label.text() == "Код для Apps Script"
    assert dialog._auth_token_edit.placeholderText() == "Ключ доступа"
    assert dialog._webhook_url_edit.text() == "https://script.google.com/macros/s/existing/exec"
    assert dialog._auth_token_edit.text() == "seed-token"
    assert "handleRequest" in dialog._shim_preview.toPlainText()
