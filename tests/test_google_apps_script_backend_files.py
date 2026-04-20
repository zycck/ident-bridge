from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "google script back end"
SRC_DIR = BACKEND_DIR / "src"
LIBRARY_SCRIPT_ID = "1gCHuAaNHvQmelAnG2bLBlCoiuj1EPx0uu8D0e3leBp1XQ6X6sukBm5iu"
LIBRARY_SYMBOL = "iDBBackend"
TECH_COLUMN = "__\u0414\u0430\u0442\u0430\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0438"
TECH_COLUMN_JS = "__\\u0414\\u0430\\u0442\\u0430\\u0412\\u044b\\u0433\\u0440\\u0443\\u0437\\u043a\\u0438"


def _v2_checksum(
    protocol_version: str,
    job_name: str,
    run_id: str,
    chunk_index: int,
    total_chunks: int,
    total_rows: int,
    chunk_rows: int,
    sheet_name: str,
    export_date: str,
    columns: list[object],
    records: list[object],
) -> str:
    payload = json.dumps(
        {
            "protocol_version": protocol_version,
            "job_name": job_name,
            "run_id": run_id,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "total_rows": total_rows,
            "chunk_rows": chunk_rows,
            "sheet_name": sheet_name,
            "export_date": export_date,
            "columns": columns,
            "records": records,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_google_apps_script_backend_is_split_into_v2_modules() -> None:
    source_files = sorted(path.name for path in SRC_DIR.iterdir() if path.is_file())

    assert "backend.js" in source_files
    assert any(name.startswith("backend_") for name in source_files)
    assert len(source_files) >= 4
    assert "Подключение.gs" not in source_files

    combined_source = "\n".join(
        (SRC_DIR / name).read_text(encoding="utf-8") for name in source_files
    )
    for legacy_token in [
        "_dedupe_index_v1",
        "_dedupe_index_v2",
        "_idem_ledger_v1",
        "recovery",
        "ledgerSheetName",
        "indexPrepareChunk_",
    ]:
        assert legacy_token not in combined_source


def test_library_project_keeps_connection_template_outside_src() -> None:
    library_template = SRC_DIR / "Подключение.gs"
    shim_template = ROOT / "resources" / "gas-shim" / "shim.gs"

    assert not library_template.exists()
    assert shim_template.exists()

    shim_text = shim_template.read_text(encoding="utf-8")
    assert "function doGet(e) {" in shim_text
    assert "function doPost(e) {" in shim_text
    assert LIBRARY_SCRIPT_ID in shim_text


def test_do_get_supports_only_ping_and_sheets() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [['id', 'name', '__TECH_COLUMN__']]
        });
        __registerSheet('__stage__Reports__run-1', {
          sheetId: 11,
          hidden: true,
          values: [['__chunk_index', '__row_index', 'id', 'name', '__TECH_COLUMN__']]
        });

        const ping = JSON.parse(__callGet({ action: 'ping' }));
        const sheets = JSON.parse(__callGet({ action: 'sheets' }));
        const invalid = JSON.parse(__callGet({ action: 'headers' }));

        console.log(JSON.stringify({ ping, sheets, invalid }));
        """
    )

    assert result["ping"]["ok"] is True
    assert result["ping"]["status"] == "ready"
    assert result["ping"]["message"] == "pong"
    assert result["sheets"]["sheet_names"] == ["Reports"]
    assert result["sheets"]["sheets"] == ["Reports"]
    assert result["invalid"]["ok"] is False
    assert result["invalid"]["error_code"] == "INVALID_ACTION"


def test_do_post_stages_chunks_and_promotes_on_completion() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__'],
            [99, 'Old', '2026-04-20'],
            [50, 'Keep', '2026-04-19']
          ]
        });

        const basePayload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-2026-04-20-001',
          total_chunks: 2,
          total_rows: 3,
          chunk_rows: 2,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          columns: ['id', 'name']
        };

        const chunk1Records = [
          { id: 1, name: 'Ana' },
          { id: 2, name: 'Boris' }
        ];
        const chunk2Records = [
          { id: 3, name: 'Vera' }
        ];

        const first = JSON.parse(__callPost({
          ...basePayload,
          chunk_index: 1,
          records: chunk1Records,
          checksum: __checksum__({ ...basePayload, chunk_index: 1, records: chunk1Records })
        }));

        const second = JSON.parse(__callPost({
          ...basePayload,
          chunk_index: 2,
          chunk_rows: 1,
          total_rows: 3,
          records: chunk2Records,
          checksum: __checksum__({ ...basePayload, chunk_index: 2, chunk_rows: 1, total_rows: 3, records: chunk2Records })
        }));

        const mainSheet = __spreadsheet.getSheetByName('Reports');
        const stagingSheet = __spreadsheet.getSheetByName('__stage__Reports__run-2026-04-20-001');

        console.log(JSON.stringify({
          first,
          second,
          mainValues: mainSheet.getDataRange().getValues(),
          hiddenColumns: mainSheet.getHiddenColumns ? mainSheet.getHiddenColumns() : [],
          stagingValues: stagingSheet.getDataRange().getValues(),
          state: JSON.parse(__propertyStore.get('gasv2:run:run-2026-04-20-001'))
        }));
        """
    )

    assert result["first"]["ok"] is True
    assert result["first"]["status"] == "staged"
    assert result["first"]["rows_written"] == 2
    assert result["second"]["ok"] is True
    assert result["second"]["status"] == "promoted"
    assert result["second"]["rows_written"] == 1
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN],
        [50, "Keep", "2026-04-19"],
        [1, "Ana", "2026-04-20"],
        [2, "Boris", "2026-04-20"],
        [3, "Vera", "2026-04-20"],
    ]
    assert result["hiddenColumns"] == [3]
    assert result["stagingValues"] == []
    assert result["state"]["promoted"] is True
    assert result["state"]["sheet_name"] == "Reports"


def test_do_post_repeating_same_chunk_keeps_staging_idempotent() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [['id', 'name', '__TECH_COLUMN__']]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-duplicate',
          chunk_index: 1,
          total_chunks: 2,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          columns: ['id', 'name'],
          records: [
            { id: 1, name: 'Ana' },
            { id: 2, name: 'Boris' }
          ]
        };
        payload.checksum = __checksum__(payload);
        const first = JSON.parse(__callPost(payload));
        const second = JSON.parse(__callPost(payload));
        const stagingSheet = __spreadsheet.getSheetByName('__stage__Reports__run-duplicate');

        console.log(JSON.stringify({
          first,
          second,
          stagingValues: stagingSheet.getDataRange().getValues()
        }));
        """
    )

    assert result["first"]["status"] == "staged"
    assert result["second"]["status"] == "duplicate"
    assert result["second"]["rows_written"] == 0
    assert result["stagingValues"] == [
        ['__chunk_index', '__row_index', 'id', 'name', TECH_COLUMN],
        [1, 1, 1, 'Ana', '2026-04-20'],
        [1, 2, 2, 'Boris', '2026-04-20'],
    ]


def test_do_post_repeating_final_chunk_after_promotion_is_safe() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [['id', 'name', '__TECH_COLUMN__']]
        });

        const chunk1 = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-final-repeat',
          chunk_index: 1,
          total_chunks: 2,
          total_rows: 3,
          chunk_rows: 2,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          columns: ['id', 'name'],
          records: [
            { id: 1, name: 'Ana' },
            { id: 2, name: 'Boris' }
          ]
        };
        chunk1.checksum = __checksum__(chunk1);
        const chunk2 = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-final-repeat',
          chunk_index: 2,
          total_chunks: 2,
          total_rows: 3,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          columns: ['id', 'name'],
          records: [
            { id: 3, name: 'Vera' }
          ]
        };
        chunk2.checksum = __checksum__(chunk2);

        const first = JSON.parse(__callPost(chunk1));
        const second = JSON.parse(__callPost(chunk2));
        const repeat = JSON.parse(__callPost(chunk2));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({
          first,
          second,
          repeat,
          mainValues: mainSheet.getDataRange().getValues()
        }));
        """
    )

    assert result["second"]["status"] == "promoted"
    assert result["repeat"]["status"] == "promoted"
    assert result["repeat"]["rows_written"] == 0
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN],
        [1, "Ana", "2026-04-20"],
        [2, "Boris", "2026-04-20"],
        [3, "Vera", "2026-04-20"],
    ]


def test_do_post_rejects_bad_checksum() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [['id', 'name', '__TECH_COLUMN__']]
        });
        const base = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-errors',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          columns: ['id', 'name'],
          records: [{ id: 1, name: 'Ana' }]
        };

        const badChecksum = JSON.parse(__callPost({
          ...base,
          checksum: 'not-a-real-checksum'
        }));

        console.log(JSON.stringify({ badChecksum }));
        """
    )

    assert result["badChecksum"]["ok"] is False
    assert result["badChecksum"]["error_code"] == "CHECKSUM_MISMATCH"


def test_do_post_maps_new_rows_by_column_name_and_keeps_existing_header_order() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['name', '__TECH_COLUMN__'],
            ['Keep', '2026-04-19']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-column-map',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          columns: ['id', 'name'],
          records: [{ id: 1, name: 'Ana' }]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({
          ack,
          mainValues: mainSheet.getDataRange().getValues(),
          hiddenColumns: mainSheet.getHiddenColumns ? mainSheet.getHiddenColumns() : []
        }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["ack"]["status"] == "promoted"
    assert result["mainValues"] == [
        ["name", "id", TECH_COLUMN],
        ["Keep", "", "2026-04-19"],
        ["Ana", 1, "2026-04-20"],
    ]
    assert result["hiddenColumns"] == [3]


def test_ping_cleans_stale_stage_sheet_and_run_state() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('__stage__Reports__stale-run', {
          sheetId: 11,
          hidden: true,
          values: [['__chunk_index', '__row_index', 'id', 'name', '__TECH_COLUMN__']]
        });
        __propertyStore.set('gasv2:run:stale-run', JSON.stringify({
          run_id: 'stale-run',
          staging_sheet_name: '__stage__Reports__stale-run',
          updated_at: '2000-01-01T00:00:00.000Z'
        }));

        const ping = JSON.parse(__callGet({ action: 'ping' }));

        console.log(JSON.stringify({
          ping,
          stageExists: Boolean(__spreadsheet.getSheetByName('__stage__Reports__stale-run')),
          stateExists: Boolean(__propertyStore.get('gasv2:run:stale-run'))
        }));
        """
    )

    assert result["ping"]["ok"] is True
    assert result["stageExists"] is False
    assert result["stateExists"] is False


def _run_backend_probe(probe: str) -> dict[str, object]:
    probe = probe.replace("__TECH_COLUMN__", TECH_COLUMN_JS)
    source_files = sorted(
        path
        for path in SRC_DIR.iterdir()
        if path.is_file() and path.suffix in {".gs", ".js"}
    )
    source_loading = "\n".join(
        f"eval(fs.readFileSync({json.dumps(str(path))}, 'utf8'));"
        for path in source_files
    )

    harness = f"""
const crypto = require('crypto');
const fs = require('fs');

function __cloneRows__(rows) {{
  return rows.map((row) => Array.isArray(row) ? row.slice() : []);
}}

function __maxColumns__(rows) {{
  return rows.reduce((max, row) => Math.max(max, Array.isArray(row) ? row.length : 0), 0);
}}

function __makeRange__(sheet, startRow, startColumn, numRows, numColumns) {{
  return {{
    getValues: () => {{
      const values = [];
      for (let rowOffset = 0; rowOffset < numRows; rowOffset += 1) {{
        const sourceRow = sheet.__values[startRow - 1 + rowOffset] || [];
        const row = [];
        for (let columnOffset = 0; columnOffset < numColumns; columnOffset += 1) {{
          row.push(sourceRow[startColumn - 1 + columnOffset]);
        }}
        values.push(row);
      }}
      return __cloneRows__(values);
    }},
    setValues: (newValues) => {{
      for (let rowOffset = 0; rowOffset < numRows; rowOffset += 1) {{
        const sourceRow = Array.isArray(newValues[rowOffset]) ? newValues[rowOffset] : [];
        const targetIndex = startRow - 1 + rowOffset;
        while (sheet.__values.length <= targetIndex) {{
          sheet.__values.push([]);
        }}
        const targetRow = sheet.__values[targetIndex];
        while (targetRow.length < startColumn - 1 + numColumns) {{
          targetRow.push('');
        }}
        for (let columnOffset = 0; columnOffset < numColumns; columnOffset += 1) {{
          targetRow[startColumn - 1 + columnOffset] = sourceRow[columnOffset];
        }}
      }}
      return this;
    }},
    clearContent: () => {{
      for (let rowOffset = 0; rowOffset < numRows; rowOffset += 1) {{
        const targetIndex = startRow - 1 + rowOffset;
        if (!sheet.__values[targetIndex]) {{
          continue;
        }}
        for (let columnOffset = 0; columnOffset < numColumns; columnOffset += 1) {{
          sheet.__values[targetIndex][startColumn - 1 + columnOffset] = '';
        }}
      }}
      return this;
    }}
  }};
}}

function __makeSheet__(name, options = {{}}) {{
  const sheet = {{
    __values: __cloneRows__(options.values || []),
    __hiddenColumns: new Set(options.hiddenColumns || []),
    __hidden: Boolean(options.hidden),
    getName: () => name,
    getSheetId: () => options.sheetId || 1,
    getFrozenRows: () => options.frozenRows !== undefined ? options.frozenRows : 1,
    setFrozenRows: (value) => {{
      options.frozenRows = value;
    }},
    isSheetHidden: () => sheet.__hidden,
    hideSheet: () => {{
      sheet.__hidden = true;
    }},
    getLastRow: () => sheet.__values.length,
    getLastColumn: () => __maxColumns__(sheet.__values),
    getMaxColumns: () => options.maxColumns !== undefined ? options.maxColumns : 50,
    getDataRange: () => __makeRange__(sheet, 1, 1, sheet.__values.length, Math.max(sheet.getLastColumn(), 1)),
    getRange: (row, column, numRows = 1, numColumns = 1) => __makeRange__(sheet, row, column, numRows, numColumns),
    clearContents: () => {{
      sheet.__values = [];
      return sheet;
    }},
    hideColumns: (column, count) => {{
      for (let index = 0; index < count; index += 1) {{
        sheet.__hiddenColumns.add(column + index);
      }}
    }},
    getHiddenColumns: () => Array.from(sheet.__hiddenColumns).sort((left, right) => left - right),
  }};

  return sheet;
}}

const __sheets = Object.create(null);
const __spreadsheet = {{
  getId: () => 'spreadsheet-id',
  getSheetByName: (name) => __sheets[name] || null,
  insertSheet: (name) => {{
    const sheet = __makeSheet__(name, {{ sheetId: Object.keys(__sheets).length + 1 }});
    __sheets[name] = sheet;
    return sheet;
  }},
  deleteSheet: (sheet) => {{
    delete __sheets[sheet.getName()];
  }},
  getSheets: () => Object.values(__sheets)
}};

global.__spreadsheet = __spreadsheet;
global.__registerSheet = (name, options = {{}}) => {{
  const sheet = __makeSheet__(name, options);
  __sheets[name] = sheet;
  return sheet;
}};

global.Utilities = {{
  DigestAlgorithm: {{ SHA_256: 'SHA_256' }},
  Charset: {{ UTF_8: 'utf8' }},
  computeDigest: (_algorithm, value) => Array.from(
    crypto.createHash('sha256').update(String(value), 'utf8').digest()
  ).map((byte) => byte > 127 ? byte - 256 : byte),
  newBlob: (value) => ({{
    getBytes: () => Buffer.from(String(value), 'utf8')
  }})
}};

global.ContentService = {{
  MimeType: {{ JSON: 'application/json' }},
  createTextOutput: (text) => ({{
    setMimeType: () => text
  }})
}};

global.Logger = {{ log: () => {{}} }};
global.SpreadsheetApp = {{
  getActiveSpreadsheet: () => __spreadsheet,
  openById: () => __spreadsheet
}};
global.Sheets = {{
  Spreadsheets: {{
    Values: {{
      batchGet: () => ({{ valueRanges: [] }})
    }},
    batchUpdate: () => ({{}})
  }}
}};

const __propertyStore = new Map();
global.__propertyStore = {{
  get: (key) => __propertyStore.get(key),
  set: (key, value) => {{
    __propertyStore.set(key, value);
  }},
  delete: (key) => {{
    __propertyStore.delete(key);
  }}
}};
global.PropertiesService = {{
  getScriptProperties: () => ({{
    getProperty: (key) => __propertyStore.has(key) ? __propertyStore.get(key) : null,
    setProperty: (key, value) => {{
      __propertyStore.set(key, value);
    }},
    deleteProperty: (key) => {{
      __propertyStore.delete(key);
    }},
    getProperties: () => Object.fromEntries(__propertyStore.entries())
  }})
}};
global.LockService = {{
  getScriptLock: () => ({{
    tryLock: () => true,
    releaseLock: () => {{}}
  }})
}};

{source_loading}

function __stable__(value) {{
  if (value === null || value === undefined) {{
    return value;
  }}
  if (Array.isArray(value)) {{
    return value.map((item) => __stable__(item));
  }}
  if (Object.prototype.toString.call(value) === '[object Object]') {{
    const output = {{}};
    for (const key of Object.keys(value).sort()) {{
      output[key] = __stable__(value[key]);
    }}
    return output;
  }}
  return value;
}}

global.__checksum__ = (payload) => {{
  const canonical = JSON.stringify(__stable__({{
    protocol_version: payload.protocol_version,
    job_name: payload.job_name,
    run_id: payload.run_id,
    chunk_index: payload.chunk_index,
    total_chunks: payload.total_chunks,
    total_rows: payload.total_rows,
    chunk_rows: payload.chunk_rows,
    sheet_name: payload.sheet_name,
    export_date: payload.export_date,
    columns: payload.columns,
    records: payload.records
  }}));
  return crypto.createHash('sha256').update(canonical, 'utf8').digest('hex');
}};

global.__callGet = (parameter = {{}}, context = null) => (
  iDBBackend.handleRequest({{ parameter }}, 'GET', context)
);

global.__callPost = (payload, context = null) => (
  iDBBackend.handleRequest({{
    postData: {{
      contents: JSON.stringify(payload)
    }}
  }}, 'POST', context)
);

{probe}
"""
    completed = subprocess.run(
        ["node", "-"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=harness,
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "Node probe failed\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}"
        )
    return json.loads(completed.stdout.strip().splitlines()[-1])
