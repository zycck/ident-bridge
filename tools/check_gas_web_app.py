#!/usr/bin/env python3
"""Minimal diagnostic probe for a deployed Google Apps Script web app."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.constants import EXPORT_SOURCE_ID


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


def _decode_json_response(raw: bytes) -> tuple[dict[str, object] | None, bool, str]:
    preview = _preview(raw)
    payload = None
    is_json = False
    try:
        payload = json.loads(raw.decode("utf-8"))
        is_json = isinstance(payload, dict)
    except Exception:  # noqa: BLE001
        payload = None
    return payload, is_json, preview


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

    payload, is_json, preview = _decode_json_response(raw)

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


def _stable_payload(payload: dict[str, object]) -> bytes:
    checksum_payload = {
        "protocol_version": payload["protocol_version"],
        "job_name": payload["job_name"],
        "run_id": payload["run_id"],
        "chunk_index": payload["chunk_index"],
        "total_chunks": payload["total_chunks"],
        "total_rows": payload["total_rows"],
        "chunk_rows": payload["chunk_rows"],
        "sheet_name": payload["sheet_name"],
        "export_date": payload["export_date"],
        "source_id": payload["source_id"],
        "write_mode": payload["write_mode"],
        "columns": payload["columns"],
        "records": payload["records"],
    }
    return json.dumps(
        checksum_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_post_smoke_payload(
    sheet_name: str,
    *,
    job_name: str = "codex_probe",
    source_id: str = EXPORT_SOURCE_ID,
    export_date: str | None = None,
    probe_value: str = "ok",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "protocol_version": "gas-sheet.v2",
        "job_name": job_name,
        "run_id": f"probe-{uuid4().hex}",
        "chunk_index": 1,
        "total_chunks": 1,
        "total_rows": 1,
        "chunk_rows": 1,
        "sheet_name": sheet_name,
        "export_date": export_date or date.today().isoformat(),
        "source_id": source_id,
        "write_mode": "append",
        "columns": ["probe"],
        "records": [{"probe": probe_value}],
    }
    payload["checksum"] = hashlib.sha256(_stable_payload(payload)).hexdigest()
    return payload


def probe_post(url: str, payload: dict[str, object], *, timeout: float = 10.0) -> dict[str, object]:
    raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url.strip(),
        data=raw_body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "iDentBridge GAS probe",
        },
        method="POST",
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
            "action": "post-smoke",
            "url": url.strip(),
            "final_url": exc.geturl(),
            "status_code": exc.code,
            "content_type": str(exc.headers.get("Content-Type") or ""),
            "payload": None,
            "preview": _preview(raw),
            "backend_ok": False,
            "expected_status": "accepted",
            "actual_status": "",
        }

    response_payload, is_json, preview = _decode_json_response(raw)
    backend_ok = is_json and bool(response_payload.get("ok", False))
    actual_status = str(response_payload.get("status", "") or "").strip() if is_json else ""

    return {
        "ok": backend_ok and actual_status == "accepted",
        "action": "post-smoke",
        "url": url.strip(),
        "final_url": final_url,
        "status_code": status_code,
        "content_type": content_type,
        "payload": response_payload,
        "preview": preview,
        "backend_ok": backend_ok,
        "expected_status": "accepted",
        "actual_status": actual_status,
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
    parser.add_argument(
        "--post-sheet",
        help="Optional sheet for append smoke POST. Writes one probe row to chosen sheet.",
    )
    parser.add_argument(
        "--post-job-name",
        default="codex_probe",
        help="job_name for optional POST smoke payload.",
    )
    parser.add_argument(
        "--post-source-id",
        default=EXPORT_SOURCE_ID,
        help="source_id for optional POST smoke payload.",
    )
    parser.add_argument(
        "--post-export-date",
        default=None,
        help="Optional export_date for POST smoke payload. Default: today.",
    )
    parser.add_argument(
        "--post-probe-value",
        default="ok",
        help="Value for single 'probe' column in optional POST smoke payload.",
    )
    args = parser.parse_args()

    results = [probe_action(args.url, action) for action in args.actions]
    if args.post_sheet:
        post_payload = build_post_smoke_payload(
            args.post_sheet,
            job_name=args.post_job_name,
            source_id=args.post_source_id,
            export_date=args.post_export_date,
            probe_value=args.post_probe_value,
        )
        results.append(probe_post(args.url, post_payload))
    print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
