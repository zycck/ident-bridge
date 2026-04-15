import winreg
import sys
import os
from pathlib import Path

from app.core.app_logger import get_logger

_log = get_logger(__name__)

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "iDentBridge"


def get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = Path(__file__).parent.parent.parent / "main.py"
    return f'"{sys.executable}" "{main_py}"'


def _read_value() -> str:
    """Read the current registry value (raises FileNotFoundError if missing)."""
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        REG_PATH,
        0,
        winreg.KEY_READ,
    ) as key:
        value, _type = winreg.QueryValueEx(key, APP_NAME)
        return value


def is_registered() -> bool:
    try:
        _read_value()
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:
        _log.warning("Autostart is_registered check failed: %s", exc)
        return False


def register() -> tuple[bool, str]:
    exe_path = get_exe_path()
    _log.info("Autostart register: writing exe path -> %s", exe_path)
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
    except Exception as exc:
        _log.error("Autostart register FAILED: %s", exc)
        return False, str(exc)

    # Verify by reading back
    try:
        readback = _read_value()
        if readback == exe_path:
            _log.info(
                "Autostart register VERIFIED: HKCU\\%s\\%s = %s",
                REG_PATH, APP_NAME, readback,
            )
            _log.info("App will start automatically on next Windows login")
            return True, ""
        else:
            _log.warning(
                "Autostart register MISMATCH: wrote %r but read back %r",
                exe_path, readback,
            )
            return False, "Verification failed: stored value differs"
    except FileNotFoundError:
        _log.error(
            "Autostart register VERIFY FAILED: registry value not found after write"
        )
        return False, "Verification failed: value not found after write"
    except Exception as exc:
        _log.error("Autostart register VERIFY FAILED: %s", exc)
        return False, str(exc)


def unregister() -> tuple[bool, str]:
    _log.info("Autostart unregister: removing entry %s", APP_NAME)
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
                _log.info("Autostart unregister: registry entry removed")
            except FileNotFoundError:
                _log.info("Autostart unregister: entry was already absent (no-op)")
    except Exception as exc:
        _log.error("Autostart unregister FAILED: %s", exc)
        return False, str(exc)

    # Verify it's actually gone
    try:
        _read_value()
        _log.error(
            "Autostart unregister VERIFY FAILED: value still present after delete"
        )
        return False, "Verification failed: value still present"
    except FileNotFoundError:
        _log.info(
            "Autostart unregister VERIFIED: HKCU\\%s\\%s removed",
            REG_PATH, APP_NAME,
        )
        return True, ""
    except Exception as exc:
        _log.warning("Autostart unregister VERIFY error: %s", exc)
        return True, ""  # benefit of the doubt


def sync_path() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            current_value, _ = winreg.QueryValueEx(key, APP_NAME)
    except Exception:
        return

    expected = get_exe_path()

    if os.path.normcase(current_value.strip('"')) != os.path.normcase(expected.strip('"')):
        register()
