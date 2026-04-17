"""Tests for extracted ErrorDialog infrastructure helpers."""

from types import SimpleNamespace

from app.ui.error_dialog_controller import (
    build_exception_traceback,
    install_global_handler,
)


class _FakeDialog:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.exec_calls = 0

    def exec(self) -> None:
        self.exec_calls += 1


def test_build_exception_traceback_includes_exception_name_and_message() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        text = build_exception_traceback(exc)

    assert "ValueError" in text
    assert "boom" in text


def test_install_global_handler_logs_and_shows_dialog_when_app_exists() -> None:
    sys_module = SimpleNamespace(excepthook=None)
    dialogs: list[_FakeDialog] = []
    logs: list[str] = []

    def factory(exc: BaseException) -> _FakeDialog:
        dialog = _FakeDialog(exc)
        dialogs.append(dialog)
        return dialog

    install_global_handler(
        dialog_factory=factory,
        append_error_log_fn=logs.append,
        app_instance_fn=lambda: object(),
        sys_module=sys_module,
    )

    try:
        raise RuntimeError("broken")
    except RuntimeError as exc:
        sys_module.excepthook(type(exc), exc, exc.__traceback__)

    assert len(logs) == 1
    assert "RuntimeError" in logs[0]
    assert len(dialogs) == 1
    assert dialogs[0].exc.args == ("broken",)
    assert dialogs[0].exec_calls == 1


def test_install_global_handler_skips_dialog_without_qt_app() -> None:
    sys_module = SimpleNamespace(excepthook=None)
    dialogs: list[_FakeDialog] = []
    logs: list[str] = []

    install_global_handler(
        dialog_factory=lambda exc: dialogs.append(_FakeDialog(exc)) or dialogs[-1],
        append_error_log_fn=logs.append,
        app_instance_fn=lambda: None,
        sys_module=sys_module,
    )

    try:
        raise LookupError("missing")
    except LookupError as exc:
        sys_module.excepthook(type(exc), exc, exc.__traceback__)

    assert len(logs) == 1
    assert "LookupError" in logs[0]
    assert dialogs == []
