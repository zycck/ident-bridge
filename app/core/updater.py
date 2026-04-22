import hashlib
import json
import ssl
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from string import hexdigits

from app.core.app_logger import get_logger
from app.core.constants import (
    EXE_NAME,
    GITHUB_API_URL,
    GITHUB_REPO,
    MIN_DOWNLOAD_BYTES,
    USER_AGENT,
)

_DETACHED_FLAGS = (
    getattr(subprocess, "DETACHED_PROCESS", 0)
    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
)
_log = get_logger(__name__)


def _normalize_digest(digest: object) -> str | None:
    if not isinstance(digest, str):
        return None

    digest = digest.strip()
    if not digest.startswith("sha256:"):
        return None

    value = digest.split(":", 1)[1].strip()
    if len(value) != 64 or any(char not in hexdigits for char in value):
        return None

    return f"sha256:{value.lower()}"


def _pick_download_asset(release_data: dict) -> tuple[str, str | None] | None:
    """Choose the most appropriate packaged update asset from a release."""
    assets = release_data.get("assets", [])
    if not assets:
        return None

    expected_name = f"{EXE_NAME}.exe".lower()
    for asset in assets:
        name = str(asset.get("name") or "").lower()
        url = asset.get("browser_download_url")
        if name == expected_name and url:
            return (url, _normalize_digest(asset.get("digest")))

    for asset in assets:
        name = str(asset.get("name") or "").lower()
        url = asset.get("browser_download_url")
        if name.endswith(".exe") and url:
            return (url, _normalize_digest(asset.get("digest")))

    return None


def _parse_version(version: str) -> tuple[int, ...]:
    try:
        tag = version.lstrip("v")
        parts = tag.split(".")[:3]
        return tuple(int(p) for p in parts)
    except Exception:
        return (0, 0, 0)


def is_newer(latest_tag: str, current_version: str) -> bool:
    return _parse_version(latest_tag) > _parse_version(current_version)


def get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(__file__).parent.parent.parent / "main.py")


def cleanup_old_exe() -> None:
    """Remove leftover self-update artifacts from a previous run."""
    old_exe = Path(get_exe_path()).parent / f"{EXE_NAME}_old.exe"
    for attempt in range(5):
        try:
            if old_exe.exists():
                old_exe.unlink()
            return
        except (OSError, PermissionError):
            if attempt < 4:
                time.sleep(0.5)


def check_latest(repo: str = GITHUB_REPO) -> tuple[str, str, str | None] | None:
    url = GITHUB_API_URL.format(repo=repo)
    headers = {"User-Agent": USER_AGENT}
    request = urllib.request.Request(url, headers=headers)
    ssl_ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, context=ssl_ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        asset = _pick_download_asset(data)
        if not asset:
            return None
        download_url, digest = asset
        return (data["tag_name"], download_url, digest)
    except Exception:
        return None


def download_update(download_url: str, expected_digest: str | None = None) -> str:
    """Download the update payload to a temporary file and return its path."""
    new_exe = Path(tempfile.gettempdir()) / f"{EXE_NAME}_new.exe"

    ssl_ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_ctx)
    )
    request = urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT})
    hasher = hashlib.sha256()
    with opener.open(request, timeout=120) as resp, new_exe.open("wb") as fh:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            hasher.update(chunk)

    size = new_exe.stat().st_size
    if size <= MIN_DOWNLOAD_BYTES:
        raise ValueError(
            f"Downloaded file is too small ({size} bytes); "
            "aborting update to avoid replacing the app with a corrupt file."
        )

    actual_digest = f"sha256:{hasher.hexdigest()}"
    if expected_digest is None:
        _log.warning(
            "Release asset digest is missing for %s; skipping verification.",
            download_url,
        )
    else:
        normalized_expected = _normalize_digest(expected_digest)
        if normalized_expected is None:
            raise ValueError("expected_digest must be a sha256:<hex> value")
        if actual_digest != normalized_expected:
            raise ValueError(
                "Downloaded file digest mismatch: "
                f"expected {normalized_expected}, got {actual_digest}"
            )
    return str(new_exe)


def apply_downloaded_update(
    downloaded_path: str,
    *,
    exit_hook: Callable[[], None] | None = None,
) -> None:
    """
    Launch the updater helper for an already-downloaded payload.

    This lets callers move the expensive network download off the GUI thread
    while keeping the fast script-generation + process-launch phase on the
    main thread.
    """
    exe_path = Path(get_exe_path())
    new_exe = Path(downloaded_path)

    old_exe = exe_path.with_name(f"{EXE_NAME}_old.exe")
    # Write script next to the exe (not world-writable tempdir) to prevent TOCTOU attacks.
    script_dir = exe_path.parent if getattr(sys, "frozen", False) else Path(tempfile.gettempdir())

    if getattr(sys, "frozen", False):
        # В замороженном .exe нет интерпретатора Python — используем .bat через cmd.exe
        script_path = script_dir / "_ident_updater.bat"
        script = (
            "@echo off\n"
            ":wait\n"
            "timeout /t 1 /nobreak >nul\n"
            f'move /y "{exe_path}" "{old_exe}" 2>nul\n'
            "if errorlevel 1 goto wait\n"
            f'move /y "{new_exe}" "{exe_path}"\n'
            f'start "" "{exe_path}"\n'
            'del "%~f0"\n'
        )
        with script_path.open("w", encoding="ascii") as fh:
            fh.write(script)
        subprocess.Popen(
            ["cmd.exe", "/c", str(script_path)],
            creationflags=_DETACHED_FLAGS,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        script_path = script_dir / "_ident_updater.py"
        script = (
            "import os, shutil, time\n"
            f"src = {str(new_exe)!r}\n"
            f"dst = {str(exe_path)!r}\n"
            f"old = {str(old_exe)!r}\n"
            "for _ in range(10):\n"
            "    try:\n"
            "        os.rename(dst, old)\n"
            "        break\n"
            "    except Exception:\n"
            "        time.sleep(1)\n"
            "shutil.move(src, dst)\n"
            "os.startfile(dst)\n"
        )
        with script_path.open("w", encoding="utf-8") as fh:
            fh.write(script)
        subprocess.Popen(
            [sys.executable, str(script_path)],
            creationflags=_DETACHED_FLAGS,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if exit_hook is None:
        sys.exit(0)
    exit_hook()

