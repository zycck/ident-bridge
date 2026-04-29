"""Tests for tray close-to-tray + Windows autostart registry."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core import startup


# ── Autostart: register / unregister / is_registered ─────────────────

def test_register_writes_value_to_registry(mock_winreg):
    """register() should put the exe path under the Run key."""
    ok, err = startup.register()
    assert ok is True
    assert "iDentBridge" in mock_winreg


def test_register_then_is_registered_returns_true(mock_winreg):
    """After register(), is_registered() must return True."""
    startup.register()
    assert startup.is_registered() is True


def test_unregister_clears_value(mock_winreg):
    """unregister() should remove the registry value."""
    startup.register()
    assert startup.is_registered() is True
    ok, err = startup.unregister()
    assert ok is True
    assert startup.is_registered() is False


def test_unregister_idempotent(mock_winreg):
    """Calling unregister twice should not crash (already returns (True,'') for missing key)."""
    startup.register()
    startup.unregister()
    # Second call on already-empty store — startup.py handles FileNotFoundError → (True, "")
    ok, err = startup.unregister()
    assert ok is True


def test_is_registered_false_when_empty(mock_winreg):
    """Fresh mock store → not registered."""
    assert startup.is_registered() is False


def test_register_uses_current_exe_path(mock_winreg):
    """The stored value should resemble a path (contains main.py or .exe or python)."""
    startup.register()
    value = mock_winreg.get("iDentBridge", "")
    assert "main.py" in value or ".exe" in value.lower() or "python" in value.lower()


def test_get_exe_path_returns_string():
    """get_exe_path should return a non-empty string in dev or frozen mode."""
    path = startup.get_exe_path()
    assert isinstance(path, str)
    assert len(path) > 0


def test_get_exe_path_contains_executable(monkeypatch):
    """In non-frozen mode the path string should include sys.executable and main.py."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    path = startup.get_exe_path()
    # Should contain the python executable name
    assert "python" in path.lower() or ".exe" in path.lower()


def test_get_exe_path_frozen_mode(monkeypatch):
    """In frozen mode get_exe_path should wrap sys.executable in quotes."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\App\iDentBridge.exe")
    path = startup.get_exe_path()
    assert "iDentBridge.exe" in path


def test_get_exe_path_includes_hidden_flag_by_default():
    """The autostart command line must carry --hidden so the app starts in tray only."""
    assert "--hidden" in startup.get_exe_path()


def test_get_exe_path_can_omit_hidden_flag():
    """Callers can opt out of the --hidden flag (e.g. for manual launch tests)."""
    assert "--hidden" not in startup.get_exe_path(hidden=False)


def test_get_exe_path_appends_hidden_flag_after_closing_quote(monkeypatch):
    """The --hidden flag goes after the quoted path so Windows parses argv correctly."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\App\iDentBridge.exe")
    path = startup.get_exe_path()
    assert path.endswith('.exe" --hidden')


def test_register_value_contains_hidden_flag(mock_winreg):
    """Newly registered autostart entries must include --hidden."""
    startup.register()
    assert "--hidden" in mock_winreg["iDentBridge"]


def test_ensure_hidden_flag_rewrites_legacy_value(mock_winreg):
    """A legacy entry without --hidden is migrated silently on next launch."""
    mock_winreg["iDentBridge"] = '"C:\\App\\iDentBridge.exe"'
    rewrote = startup.ensure_hidden_flag()
    assert rewrote is True
    assert "--hidden" in mock_winreg["iDentBridge"]


def test_ensure_hidden_flag_noop_when_already_present(mock_winreg):
    """If --hidden is already in the value, do nothing and return False."""
    startup.register()
    assert startup.ensure_hidden_flag() is False


def test_ensure_hidden_flag_noop_when_unregistered(mock_winreg):
    """If autostart isn't registered, ensure_hidden_flag is a quiet no-op."""
    assert startup.ensure_hidden_flag() is False


def test_ensure_hidden_flag_noop_when_winreg_missing(monkeypatch):
    """The migration helper stays import-safe on non-Windows platforms."""
    monkeypatch.setattr(startup, "winreg", None, raising=False)
    assert startup.ensure_hidden_flag() is False


def test_get_exe_path_hidden_dev_swaps_python_for_pythonw(tmp_path, monkeypatch):
    """Hidden autostart entries must launch via pythonw.exe to avoid console window."""
    fake_python = tmp_path / "python.exe"
    fake_pythonw = tmp_path / "pythonw.exe"
    fake_python.write_bytes(b"")
    fake_pythonw.write_bytes(b"")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_python))

    hidden_path = startup.get_exe_path(hidden=True)
    visible_path = startup.get_exe_path(hidden=False)

    assert "pythonw.exe" in hidden_path
    assert "python.exe" not in hidden_path.replace("pythonw.exe", "")
    assert "--hidden" in hidden_path
    # Manual launch must NOT swap — devs still want stdout in their terminal
    assert "pythonw.exe" not in visible_path
    assert visible_path.endswith('main.py"')


def test_get_exe_path_hidden_dev_keeps_python_when_pythonw_absent(tmp_path, monkeypatch):
    """If pythonw.exe is missing next to python.exe, fall back to python.exe gracefully."""
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_python))

    path = startup.get_exe_path(hidden=True)

    assert "pythonw.exe" not in path
    assert "python.exe" in path
    assert "--hidden" in path


def test_ensure_hidden_flag_rewrites_console_python_entry(mock_winreg, tmp_path, monkeypatch):
    """Old entries that still launch python.exe (console) must migrate to pythonw.exe."""
    fake_python = tmp_path / "python.exe"
    fake_pythonw = tmp_path / "pythonw.exe"
    fake_python.write_bytes(b"")
    fake_pythonw.write_bytes(b"")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_python))

    main_py = Path(__file__).resolve().parents[1] / "main.py"
    legacy = f'"{fake_python}" "{main_py}" --hidden'
    mock_winreg["iDentBridge"] = legacy

    rewrote = startup.ensure_hidden_flag()

    assert rewrote is True
    assert "pythonw.exe" in mock_winreg["iDentBridge"]
    assert "--hidden" in mock_winreg["iDentBridge"]


def test_ensure_hidden_flag_noop_when_already_pythonw(mock_winreg, tmp_path, monkeypatch):
    """If the entry already uses pythonw.exe with --hidden, leave it alone."""
    fake_python = tmp_path / "python.exe"
    fake_pythonw = tmp_path / "pythonw.exe"
    fake_python.write_bytes(b"")
    fake_pythonw.write_bytes(b"")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_python))

    startup.register()
    snapshot = mock_winreg["iDentBridge"]
    assert "pythonw.exe" in snapshot

    assert startup.ensure_hidden_flag() is False
    assert mock_winreg["iDentBridge"] == snapshot


def test_register_returns_tuple(mock_winreg):
    """register() must return a (bool, str) tuple."""
    result = startup.register()
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], str)


def test_unregister_returns_tuple(mock_winreg):
    """unregister() must return a (bool, str) tuple."""
    startup.register()
    result = startup.unregister()
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)


def test_windows_autostart_is_safe_when_winreg_missing(monkeypatch):
    """The module should remain import-safe and no-op off Windows."""
    monkeypatch.setattr(startup, "winreg", None, raising=False)

    assert startup.is_registered() is False
    assert startup.register() == (False, "Windows autostart is unavailable on this platform")
    assert startup.unregister() == (False, "Windows autostart is unavailable on this platform")

# ── MainWindow tray close-to-tray ─────────────────────────────────────

@pytest.fixture
def main_window(qapp_session, tmp_config):
    """Construct a real MainWindow with a tmp config."""
    from app.ui.main_window import MainWindow
    window = MainWindow(tmp_config, "0.0.1-test")
    yield window
    # Cleanup: stop schedulers + dashboard timer
    try:
        window._cleanup()
    except Exception:
        pass


def test_main_window_constructs_with_tray(main_window):
    """The main window should have a _tray attribute that is not None."""
    assert hasattr(main_window, "_tray")
    assert main_window._tray is not None


def test_close_event_hides_window_when_tray_visible(main_window):
    """Close button → window hides instead of closing when tray is visible."""
    from PySide6.QtGui import QCloseEvent

    # Force tray visibility flag
    if hasattr(main_window._tray, "setVisible"):
        main_window._tray.setVisible(True)

    # Ensure the window is shown first so hide() has an effect
    main_window.show()

    event = QCloseEvent()
    main_window.closeEvent(event)

    # When tray is visible: event must be ignored AND window must be hidden
    assert event.isAccepted() is False
    assert main_window.isHidden()


def test_close_event_accepts_when_tray_not_visible(main_window):
    """If tray is hidden, closeEvent should accept the event (and call quit)."""
    from PySide6.QtGui import QCloseEvent
    from unittest.mock import patch as _patch

    # Force tray to hidden state
    main_window._tray.hide()
    # Verify the tray is not visible (in offscreen mode isVisible may be False anyway)
    assert main_window._tray.isVisible() is False

    quit_called = []
    with _patch("PySide6.QtWidgets.QApplication.quit", side_effect=lambda: quit_called.append(True)):
        event = QCloseEvent()
        main_window.closeEvent(event)

    # Either the event was accepted OR QApplication.quit was triggered
    assert event.isAccepted() or len(quit_called) > 0


def test_main_window_has_dashboard_with_stop(main_window):
    """Phase A added a stop() method to DashboardWidget for clean shutdown."""
    assert hasattr(main_window._dashboard, "stop")
    main_window._dashboard.stop()  # should not crash


def test_main_window_has_export_jobs_stop_all(main_window):
    """ExportJobsWidget must expose stop_all_schedulers() used by _cleanup."""
    assert hasattr(main_window._export_jobs, "stop_all_schedulers")
    main_window._export_jobs.stop_all_schedulers()  # should not crash


def test_main_window_cleanup_stops_all(main_window):
    """_cleanup() should stop schedulers + dashboard without raising."""
    # Should not raise — second call is also safe because _cleanup is idempotent
    main_window._cleanup()


# ── Hidden autostart helper in main.py ─────────────────────────────────

def test_main_is_hidden_start_detects_flag(monkeypatch):
    """main._is_hidden_start mirrors the registry --hidden flag detection."""
    import main

    monkeypatch.setattr(sys, "argv", ["main.py", "--hidden"])
    assert main._is_hidden_start() is True

    monkeypatch.setattr(sys, "argv", ["main.py"])
    assert main._is_hidden_start() is False

    monkeypatch.setattr(sys, "argv", ["main.py", "--other"])
    assert main._is_hidden_start() is False
