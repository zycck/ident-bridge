from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "google script back end"
SRC_DIR = BACKEND_DIR / "src"


def test_google_apps_script_backend_is_consolidated_into_four_js_modules() -> None:
    source_files = sorted(path.name for path in SRC_DIR.iterdir() if path.is_file())
    assert source_files == [
        "00_entry.js",
        "10_ingest.js",
        "20_storage.js",
        "30_shared.js",
    ]


def test_appsscript_manifest_uses_v8_and_enables_advanced_sheets_service() -> None:
    manifest = json.loads((BACKEND_DIR / "appsscript.json").read_text(encoding="utf-8"))

    assert manifest["runtimeVersion"] == "V8"
    assert manifest["oauthScopes"] == [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/script.storage",
    ]
    assert manifest["dependencies"]["enabledAdvancedServices"] == [
        {
            "userSymbol": "Sheets",
            "serviceId": "sheets",
            "version": "v4",
        }
    ]


def test_storage_module_uses_sheets_api_batch_writes_without_legacy_sheet_scans() -> None:
    storage_source = (SRC_DIR / "20_storage.js").read_text(encoding="utf-8")

    assert "class SheetsStore" in storage_source
    assert "Sheets.Spreadsheets.Values.batchGet" in storage_source
    assert "Sheets.Spreadsheets.batchUpdate" in storage_source
    assert "_recoverCompletedStateFromLedger_" in storage_source
    assert "appendRow(" not in storage_source
    assert "getDataRange(" not in storage_source


def test_backend_rejects_non_empty_chunk_when_total_rows_is_zero() -> None:
    result = _run_backend_probe(
        """
        try {
          normalizeWebhookRequest_({
            protocol_version: 'gas-sheet.v1',
            job_name: 'job',
            run_id: 'run-1',
            chunk_index: 1,
            total_chunks: 1,
            total_rows: 0,
            chunk_rows: 1,
            chunk_bytes: 128,
            schema: {
              mode: 'append_only_v1',
              columns: ['id'],
              checksum: 'abc'
            },
            records: [{ id: 1 }]
          });
          console.log(JSON.stringify({ ok: true }));
        } catch (error) {
          console.log(JSON.stringify({
            ok: false,
            errorCode: error.errorCode,
            message: error.message
          }));
        }
        """
    )

    assert result["ok"] is False
    assert result["errorCode"] == "INVALID_RECORDS_SHAPE"


def test_idempotency_key_is_stable_for_reordered_schema_columns() -> None:
    result = _run_backend_probe(
        """
        const left = buildIdempotencyKey_({
          protocolVersion: 'gas-sheet.v1',
          jobName: 'job',
          runId: 'run-1',
          chunkIndex: 1,
          totalChunks: 1,
          totalRows: 1,
          chunkRows: 1,
          chunkBytes: 128,
          schema: {
            mode: 'append_only_v1',
            columns: ['id', 'email'],
            checksum: 'abc'
          },
          records: [{ id: 1, email: 'a@example.com' }]
        });
        const right = buildIdempotencyKey_({
          protocolVersion: 'gas-sheet.v1',
          jobName: 'job',
          runId: 'run-1',
          chunkIndex: 1,
          totalChunks: 1,
          totalRows: 1,
          chunkRows: 1,
          chunkBytes: 128,
          schema: {
            mode: 'append_only_v1',
            columns: ['email', 'id'],
            checksum: 'abc'
          },
          records: [{ email: 'a@example.com', id: 1 }]
        });
        console.log(JSON.stringify({ left, right, equal: left === right }));
        """
    )

    assert result["equal"] is True


def test_backend_preserves_formula_escaping_for_string_cells() -> None:
    result = _run_backend_probe(
        """
        console.log(JSON.stringify({
          eq: escapeFormulaValue_('=1+1'),
          plus: escapeFormulaValue_('+sum(A1:A2)'),
          safe: escapeFormulaValue_('hello'),
          obj: escapeFormulaValue_(stableStringify_({ a: 1 }))
        }));
        """
    )

    assert result["eq"] == "'=1+1"
    assert result["plus"] == "'+sum(A1:A2)"
    assert result["safe"] == "hello"
    assert result["obj"] == '{"a":1}'


def test_final_chunk_success_cleans_run_related_properties() -> None:
    result = _run_backend_probe(
        """
        const store = getSheetsStore_();
        const ack = {
          rows_received: 1,
          rows_written: 1,
          schema_action: 'unchanged',
          added_columns: [],
          message: 'ok'
        };
        const request1 = {
          protocolVersion: 'gas-sheet.v1',
          jobName: 'job',
          runId: 'run-1',
          chunkIndex: 1,
          totalChunks: 2,
          totalRows: 2,
          chunkRows: 1,
          chunkBytes: 128,
          schema: { mode: 'append_only_v1', columns: ['id'], checksum: 'abc' },
          records: [{ id: 1 }]
        };
        const request2 = {
          protocolVersion: 'gas-sheet.v1',
          jobName: 'job',
          runId: 'run-1',
          chunkIndex: 2,
          totalChunks: 2,
          totalRows: 2,
          chunkRows: 1,
          chunkBytes: 128,
          schema: { mode: 'append_only_v1', columns: ['id'], checksum: 'abc' },
          records: [{ id: 2 }]
        };
        const lease1 = {
          key: buildIdempotencyKey_(request1),
          lock: { released: false, releaseLock() { this.released = true; } }
        };
        const lease2 = {
          key: buildIdempotencyKey_(request2),
          lock: { released: false, releaseLock() { this.released = true; } }
        };

        store.finalizeSuccess(request1, ack, lease1);
        const afterFirst = Object.keys(__properties__);

        store.finalizeSuccess(request2, ack, lease2);
        console.log(JSON.stringify({
          afterFirst,
          afterFinal: Object.keys(__properties__),
          lease1Released: lease1.lock.released,
          lease2Released: lease2.lock.released
        }));
        """
    )

    assert result["afterFirst"]
    assert result["afterFinal"] == []
    assert result["lease1Released"] is True
    assert result["lease2Released"] is True


def _run_backend_probe(probe: str) -> dict[str, object]:
    harness = f"""
const crypto = require('crypto');
const fs = require('fs');
global.Utilities = {{
  DigestAlgorithm: {{ SHA_256: 'SHA_256' }},
  Charset: {{ UTF_8: 'utf8' }},
  computeDigest: (_algorithm, value) => Array.from(
    crypto.createHash('sha256').update(String(value), 'utf8').digest()
  ).map((byte) => byte > 127 ? byte - 256 : byte),
}};
global.ContentService = {{
  MimeType: {{ JSON: 'application/json' }},
  createTextOutput: (text) => ({{ setMimeType: () => text }}),
}};
global.Logger = {{ log: () => {{}} }};
global.SpreadsheetApp = {{}};
global.Sheets = {{ Spreadsheets: {{ Values: {{}}, batchUpdate: () => ({{}}) }} }};
const __propertyStore = new Map();
const __cacheStore = new Map();
global.__properties__ = Object.create(null);
global.LockService = {{
  getScriptLock: () => ({{
    tryLock: () => true,
    releaseLock: () => {{}}
  }})
}};
global.CacheService = {{
  getScriptCache: () => ({{
    get: (key) => __cacheStore.has(key) ? __cacheStore.get(key) : null,
    put: (key, value) => {{
      __cacheStore.set(key, value);
    }},
    remove: (key) => {{
      __cacheStore.delete(key);
    }}
  }})
}};
global.PropertiesService = {{
  getScriptProperties: () => ({{
    getProperty: (key) => __propertyStore.has(key) ? __propertyStore.get(key) : null,
    setProperty: (key, value) => {{
      __propertyStore.set(key, value);
      __properties__[key] = value;
    }},
    deleteProperty: (key) => {{
      __propertyStore.delete(key);
      delete __properties__[key];
    }},
    getProperties: () => Object.fromEntries(__propertyStore.entries())
  }})
}};
const source = [
  fs.readFileSync('google script back end/src/30_shared.js', 'utf8'),
  fs.readFileSync('google script back end/src/10_ingest.js', 'utf8'),
  fs.readFileSync('google script back end/src/20_storage.js', 'utf8'),
].join('\\n');
eval(source);
{probe}
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout.strip())
