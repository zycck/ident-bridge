import winreg
import sys
import os
from pathlib import Path

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "iDentBridge"


def get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = Path(__file__).parent.parent.parent / "main.py"
    return f'"{sys.executable}" "{main_py}"'


def is_registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def register() -> tuple[bool, str]:
    exe_path = get_exe_path()
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        return (True, "")
    except Exception as e:
        return (False, str(e))


def unregister() -> tuple[bool, str]:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
        return (True, "")
    except FileNotFoundError:
        return (True, "")
    except Exception as e:
        return (False, str(e))


def sync_path() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            current_value, _ = winreg.QueryValueEx(key, APP_NAME)
    except Exception:
        return

    expected = get_exe_path()

    if os.path.normcase(current_value.strip('"')) != os.path.normcase(expected.strip('"')):
        register()
