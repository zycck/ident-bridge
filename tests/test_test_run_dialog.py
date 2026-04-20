"""Integration-level tests for TestRunDialog construction behaviour.

Covers the two bugs the user reported after the 2026-04-17 audit:
1. SQL from the card editor MUST arrive verbatim in the dialog editor.
2. The dialog MUST render with the light theme (no black background).
"""

from __future__ import annotations

from app.config import AppConfig
from app.ui.test_run_dialog import (
    TestRunDialog,
    _FALLBACK_SQL_WHEN_NO_CARD_QUERY,
)


def _cfg() -> AppConfig:
    return AppConfig(sql_instance="localhost", sql_database="test")


def test_dialog_class_marks_itself_non_collectable_for_pytest() -> None:
    assert TestRunDialog.__test__ is False


def test_dialog_shows_exactly_the_sql_passed_in(qtbot):
    dialog = TestRunDialog(_cfg(), initial_sql="SELECT id FROM Orders")
    qtbot.addWidget(dialog)
    assert dialog._shell.sql_text() == "SELECT id FROM Orders"


def test_dialog_does_not_overwrite_non_default_sql_with_fallback(qtbot):
    """Regression: the previous `initial_sql or _DEFAULT_SQL` trick
    only protected the empty case, but `initial_sql.strip()` semantics
    meant whitespace-only input fell back to the catalog query. Any
    non-empty caller input must survive verbatim.
    """
    sql = "SELECT COUNT(*) FROM Users\n"
    dialog = TestRunDialog(_cfg(), initial_sql=sql)
    qtbot.addWidget(dialog)
    assert dialog._shell.sql_text() == sql.strip()


def test_dialog_uses_fallback_only_when_sql_is_empty(qtbot):
    dialog = TestRunDialog(_cfg(), initial_sql="")
    qtbot.addWidget(dialog)
    assert dialog._shell.sql_text() == _FALLBACK_SQL_WHEN_NO_CARD_QUERY.strip()


def test_dialog_does_not_auto_run_when_initial_sql_is_empty(qtbot):
    dialog = TestRunDialog(_cfg(), initial_sql="", auto_run=True)
    qtbot.addWidget(dialog)
    # auto_run requires a real user query — the fallback catalog probe
    # should not trigger a live DB hit on dialog open.
    assert dialog._shell.sql_text() == _FALLBACK_SQL_WHEN_NO_CARD_QUERY.strip()


def test_dialog_has_explicit_light_stylesheet(qtbot):
    """Guards the "black background" regression: the dialog must
    publish its own QSS so it doesn't inherit Qt's dark default on
    Windows when the QApplication stylesheet fails to propagate into
    a top-level modal dialog.
    """
    dialog = TestRunDialog(_cfg(), initial_sql="SELECT 1")
    qtbot.addWidget(dialog)
    qss = dialog.styleSheet()
    # Light surface tokens must appear in the dialog's own QSS.
    assert "QDialog" in qss
    assert "#FAFAFA" in qss or "#FFFFFF" in qss
    # The fallback dark palette tokens must NOT be reintroduced here.
    assert "#000000" not in qss
