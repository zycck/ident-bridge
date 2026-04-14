import json
import os
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


GITHUB_REPO = "zycck/ident-bridge"
API_URL = "https://api.github.com/repos/{repo}/releases/latest"


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
    old_exe = os.path.join(os.path.dirname(get_exe_path()), "iDentSync_old.exe")
    try:
        if os.path.exists(old_exe):
            os.remove(old_exe)
    except Exception:
        pass


def check_latest(repo: str = GITHUB_REPO) -> tuple[str, str] | None:
    url = API_URL.format(repo=repo)
    headers = {"User-Agent": "iDentBridge/0.0.1"}
    request = urllib.request.Request(url, headers=headers)
    ssl_ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, context=ssl_ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return (data["tag_name"], data["assets"][0]["browser_download_url"])
    except Exception:
        return None


def download_and_apply(download_url: str) -> None:
    exe_path = get_exe_path()
    new_exe = os.path.join(tempfile.gettempdir(), "iDentSync_new.exe")

    ssl_ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_ctx)
    )
    with opener.open(download_url) as resp, open(new_exe, "wb") as fh:
        fh.write(resp.read())

    if os.path.getsize(new_exe) <= 1_000_000:
        raise ValueError(
            f"Downloaded file is too small ({os.path.getsize(new_exe)} bytes); "
            "aborting update to avoid replacing the app with a corrupt file."
        )

    old_exe = os.path.join(os.path.dirname(exe_path), "iDentSync_old.exe")
    # Write script next to the exe (not world-writable tempdir) to prevent TOCTOU attacks.
    script_dir = os.path.dirname(exe_path) if getattr(sys, "frozen", False) else tempfile.gettempdir()
    script_path = os.path.join(script_dir, "_ident_updater.py")
    script = (
        "import os, shutil, time\n"
        f"src = {new_exe!r}\n"
        f"dst = {exe_path!r}\n"
        f"old = {old_exe!r}\n"
        "for _ in range(10):\n"
        "    try:\n"
        "        os.rename(dst, old)\n"
        "        break\n"
        "    except Exception:\n"
        "        time.sleep(1)\n"
        "shutil.move(src, dst)\n"
        "os.startfile(dst)\n"
    )
    with open(script_path, "w", encoding="utf-8") as fh:
        fh.write(script)

    subprocess.Popen(
        [sys.executable, script_path],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    sys.exit(0)
