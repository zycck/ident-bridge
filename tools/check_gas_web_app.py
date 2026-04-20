#!/usr/bin/env python3
"""Minimal diagnostic probe for a deployed Google Apps Script web app."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_action_url(url: str, action: str) -> str:
    parsed = urllib.parse.urlsplit((url or "").strip())
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [(key, value) for key, value in query_items if key != "action"]
    filtered.append(("action", action))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(filtered),
            parsed.fragment,
        )
    )


def _preview(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    return " ".join(text.split())[:400]


def probe_action(url: str, action: str, *, timeout: float = 10.0) -> dict[str, object]:
    target_url = build_action_url(url, action)
    request = urllib.request.Request(
        target_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "iDentBridge GAS probe",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status_code = getattr(response, "status", 200)
            final_url = response.geturl()
            content_type = str(response.headers.get("Content-Type") or "")
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        return {
            "ok": False,
            "action": action,
            "url": target_url,
            "final_url": exc.geturl(),
            "status_code": exc.code,
            "content_type": str(exc.headers.get("Content-Type") or ""),
            "payload": None,
            "preview": _preview(raw),
        }

    preview = _preview(raw)
    payload = None
    is_json = False
    try:
        payload = json.loads(raw.decode("utf-8"))
        is_json = isinstance(payload, dict)
    except Exception:  # noqa: BLE001
        payload = None

    return {
        "ok": is_json and bool(payload.get("ok", False)),
        "action": action,
        "url": target_url,
        "final_url": final_url,
        "status_code": status_code,
        "content_type": content_type,
        "payload": payload,
        "preview": preview,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Deployed Apps Script web app URL ending in /exec")
    parser.add_argument(
        "--actions",
        nargs="+",
        default=["ping", "sheets"],
        help="One or more GET actions to probe.",
    )
    args = parser.parse_args()

    results = [probe_action(args.url, action) for action in args.actions]
    print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
