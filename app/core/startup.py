import sys
from pathlib import Path

from app.core.app_logger import get_logger
from app.core.constants import APP_NAME

_log = get_logger(__name__)

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover - exercised indirectly via import-safe tests
    winreg = None  # type: ignore[assignment]

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
HIDDEN_FLAG = "--hidden"


def _require_winreg():
    if winreg is None:
        return None
    return winreg

def get_exe_path(*, hidden: bool = True) -> str:
    # Dev mode keeps python.exe (not pythonw.exe) so logs remain visible in the
    # spawning terminal. End users always run the frozen .exe (console=False).
    if getattr(sys, "frozen", False):
        base = f'"{sys.executable}"'
    else:
        main_py = Path(__file__).parent.parent.parent / "main.py"
        base = f'"{sys.executable}" "{main_py}"'
    return f"{base} {HIDDEN_FLAG}" if hidden else base


def _read_value() -> str:
    """Read the current registry value (raises FileNotFoundError if missing)."""
    reg = _require_winreg()
    if reg is None:
        raise OSError("Windows registry autostart is unavailable on this platform")

    with reg.OpenKey(
        reg.HKEY_CURRENT_USER,
        REG_PATH,
        0,
        reg.KEY_READ,
    ) as key:
        value, _type = reg.QueryValueEx(key, APP_NAME)
        return value


def is_registered() -> bool:
    if winreg is None:
        return False

    try:
        _read_value()
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:
        _log.warning("Autostart is_registered check failed: %s", exc)
        return False


def register() -> tuple[bool, str]:
    if winreg is None:
        return False, "Windows autostart is unavailable on this platform"

    exe_path = get_exe_path()
    _log.info("Autostart register: writing exe path -> %s", exe_path)
    try:
        reg = _require_winreg()
        assert reg is not None

        with reg.OpenKey(
            reg.HKEY_CURRENT_USER,
            REG_PATH,
            0,
            reg.KEY_SET_VALUE,
        ) as key:
            reg.SetValueEx(key, APP_NAME, 0, reg.REG_SZ, exe_path)
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


def ensure_hidden_flag() -> bool:
    """Append --hidden to an existing autostart entry that lacks the flag.

    Returns True only when the registry value was actually rewritten. Used by
    main.py on every cold start so older installs migrate silently to the new
    "hidden in tray" autostart behavior.
    """
    if winreg is None:
        return False
    try:
        current = _read_value()
    except FileNotFoundError:
        return False
    except Exception as exc:
        _log.warning("ensure_hidden_flag: read failed: %s", exc)
        return False
    if HIDDEN_FLAG in current:
        return False
    _log.info("Migrating autostart entry: appending %s", HIDDEN_FLAG)
    ok, err = register()
    if not ok:
        _log.warning("ensure_hidden_flag: register() failed: %s", err)
    return ok


def unregister() -> tuple[bool, str]:
    if winreg is None:
        return False, "Windows autostart is unavailable on this platform"

    _log.info("Autostart unregister: removing entry %s", APP_NAME)
    try:
        reg = _require_winreg()
        assert reg is not None

        with reg.OpenKey(
            reg.HKEY_CURRENT_USER,
            REG_PATH,
            0,
            reg.KEY_SET_VALUE,
        ) as key:
            try:
                reg.DeleteValue(key, APP_NAME)
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
