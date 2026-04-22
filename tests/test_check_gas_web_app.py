from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.core.constants import EXPORT_SOURCE_ID


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "check_gas_web_app.py"
SPEC = importlib.util.spec_from_file_location("check_gas_web_app", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class _FakeResp:
    def __init__(self, body: object, status: int = 200) -> None:
        self.status = status
        if isinstance(body, bytes):
            self._body = body
        elif isinstance(body, str):
            self._body = body.encode("utf-8")
        else:
            self._body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.headers = {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return "https://script.google.com/macros/s/test/exec"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_build_post_smoke_payload_uses_append_contract() -> None:
    payload = MODULE.build_post_smoke_payload(
        "Probe",
        job_name="probe-job",
        source_id="probe/source",
        export_date="2026-04-21",
        probe_value="hello",
    )

    assert payload["protocol_version"] == "gas-sheet.v2"
    assert payload["sheet_name"] == "Probe"
    assert payload["write_mode"] == "append"
    assert payload["columns"] == ["probe"]
    assert payload["records"] == [{"probe": "hello"}]
    assert isinstance(payload["checksum"], str)
    assert len(payload["checksum"]) == 64


def test_build_post_smoke_payload_defaults_to_app_source_id() -> None:
    payload = MODULE.build_post_smoke_payload("Probe")

    assert payload["source_id"] == EXPORT_SOURCE_ID


def test_probe_post_requires_accepted_contract(monkeypatch) -> None:
    def _urlopen(req, **kwargs):
        assert req.get_method() == "POST"
        return _FakeResp(
            {
                "ok": True,
                "status": "promoted",
                "rows_received": 1,
                "rows_written": 1,
                "retryable": False,
                "message": "Chunk promoted",
                "api_version": "2.0",
            }
        )

    monkeypatch.setattr(MODULE.urllib.request, "urlopen", _urlopen)

    result = MODULE.probe_post(
        "https://script.google.com/macros/s/test/exec",
        MODULE.build_post_smoke_payload("Probe", export_date="2026-04-21"),
    )

    assert result["backend_ok"] is True
    assert result["actual_status"] == "promoted"
    assert result["ok"] is False
