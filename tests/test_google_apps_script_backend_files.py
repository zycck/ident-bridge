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
SOURCE_COLUMN = "__idb_source"
SOURCE_ID = "job-1"
LEGACY_SOURCE_MARKER = "iDentBridge:gas-sheet:v2"


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
    source_id: str,
    write_mode: str,
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
            "source_id": source_id,
            "write_mode": write_mode,
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

    assert source_files == [
        "backend.js",
        "backend_core.gs",
        "backend_sheet.gs",
    ]
    assert "Подключение.gs" not in source_files

    combined_source = "\n".join(
        (SRC_DIR / name).read_text(encoding="utf-8") for name in source_files
    )
    assert "var " not in combined_source
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


def test_library_exposes_top_level_handle_request_entrypoint() -> None:
    backend_source = (SRC_DIR / "backend.js").read_text(encoding="utf-8")

    assert "function handleRequest(event, method, context)" in backend_source
    assert "var iDBBackend =" not in backend_source


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
    assert result["sheets"]["sheets"] == ["Reports"]
    assert "sheet_names" not in result["sheets"]
    assert result["invalid"]["ok"] is False
    assert result["invalid"]["error_code"] == "INVALID_ACTION"


def test_do_get_does_not_run_cleanup_or_touch_advanced_sheets_calls() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [['id', 'name', '__TECH_COLUMN__']]
        });
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
        const sheets = JSON.parse(__callGet({ action: 'sheets' }));

        console.log(JSON.stringify({
          ping,
          sheets,
          stageExists: Boolean(__spreadsheet.getSheetByName('__stage__Reports__stale-run')),
          stateExists: Boolean(__propertyStore.get('gasv2:run:stale-run')),
          calls: __calls__
        }));
        """
    )

    assert result["ping"]["ok"] is True
    assert result["sheets"]["ok"] is True
    assert result["stageExists"] is True
    assert result["stateExists"] is True
    assert result["calls"]["batchGet"] == []
    assert result["calls"]["batchUpdate"] == []


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
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
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

        console.log(JSON.stringify({
          first,
          second,
          mainValues: mainSheet.getDataRange().getValues(),
          hiddenColumns: mainSheet.getHiddenColumns ? mainSheet.getHiddenColumns() : [],
          stageExists: Boolean(__spreadsheet.getSheetByName(JSON.parse(__propertyStore.get('gasv2:run:run-2026-04-20-001')).staging_sheet_name)),
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
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
        [3, "Vera", "2026-04-20", SOURCE_ID],
        [50, "Keep", "2026-04-19", SOURCE_ID],
    ]
    assert result["hiddenColumns"] == [3, 4]
    assert result["stageExists"] is False
    assert result["state"]["completed"] is True
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
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
          columns: ['id', 'name'],
          records: [
            { id: 1, name: 'Ana' },
            { id: 2, name: 'Boris' }
          ]
        };
        payload.checksum = __checksum__(payload);
        const first = JSON.parse(__callPost(payload));
        const second = JSON.parse(__callPost(payload));
        const state = JSON.parse(__propertyStore.get('gasv2:run:run-duplicate'));
        const stagingSheet = __spreadsheet.getSheetByName(state.staging_sheet_name);

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
        ['__chunk_index', '__row_index', 'id', 'name', TECH_COLUMN, SOURCE_COLUMN],
        [1, 1, 1, 'Ana', '2026-04-20', SOURCE_ID],
        [1, 2, 2, 'Boris', '2026-04-20', SOURCE_ID],
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
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
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
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
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
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
        [3, "Vera", "2026-04-20", SOURCE_ID],
    ]


def test_do_post_single_chunk_writes_directly_without_staging_or_run_state() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [91, 'Old app row', '2026-04-20', '__SOURCE_ID__'],
            [77, 'Manual row', '2026-04-20', '']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-single',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
          columns: ['id', 'name'],
          records: [
            { id: 1, name: 'Ana' },
            { id: 2, name: 'Boris' }
          ]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({
          ack,
          mainValues: mainSheet.getDataRange().getValues(),
          hiddenColumns: mainSheet.getHiddenColumns ? mainSheet.getHiddenColumns() : [],
          stageCount: Object.keys(__sheets).filter((name) => name.startsWith('__stage__')).length,
          stateExists: Boolean(__propertyStore.get('gasv2:run:run-single'))
        }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["ack"]["status"] == "promoted"
    assert result["ack"]["rows_written"] == 2
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
        [77, "Manual row", "2026-04-20", ""],
    ]
    assert result["hiddenColumns"] == [3, 4]
    assert result["stageCount"] == 0
    assert result["stateExists"] is False


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
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
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
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
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
        ["name", "id", TECH_COLUMN, SOURCE_COLUMN],
        ["Keep", "", "2026-04-19", SOURCE_ID],
        ["Ana", 1, "2026-04-20", SOURCE_ID],
    ]
    assert result["hiddenColumns"] == [3, 4]


def test_do_post_removes_only_rows_owned_by_identbridge_for_the_same_day() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [10, 'Old app row', '2026-04-20', '__SOURCE_ID__'],
            [11, 'Manual same day', '2026-04-20', 'manual-import'],
            [12, 'Manual blank marker', '2026-04-20', ''],
            [13, 'Old app other day', '2026-04-19', '__SOURCE_ID__']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-owned-delete',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
          columns: ['id', 'name'],
          records: [{ id: 1, name: 'Ana' }]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({
          ack,
          mainValues: mainSheet.getDataRange().getValues()
        }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [11, "Manual same day", "2026-04-20", "manual-import"],
        [12, "Manual blank marker", "2026-04-20", ""],
        [13, "Old app other day", "2026-04-19", SOURCE_ID],
    ]


def test_do_post_append_mode_always_writes_to_end() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [10, 'Old app row', '2026-04-20', '__SOURCE_ID__'],
            [11, 'Manual row', '2026-04-20', 'manual-import']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-append',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'append',
          columns: ['id', 'name'],
          records: [{ id: 99, name: 'New row' }]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({ ack, mainValues: mainSheet.getDataRange().getValues() }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [10, "Old app row", "2026-04-20", SOURCE_ID],
        [11, "Manual row", "2026-04-20", "manual-import"],
        [99, "New row", "2026-04-20", SOURCE_ID],
    ]


def test_do_post_replace_all_mode_rewrites_all_rows_below_header() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [10, 'Old app row', '2026-04-20', '__SOURCE_ID__'],
            [11, 'Manual row', '2026-04-20', 'manual-import']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'directory_export',
          run_id: 'run-replace-all',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_all',
          columns: ['id', 'name'],
          records: [
            { id: 1, name: 'Ana' },
            { id: 2, name: 'Boris' }
          ]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({ ack, mainValues: mainSheet.getDataRange().getValues() }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
    ]


def test_do_post_replace_by_date_source_deletes_disjoint_ranges_bottom_up() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [10, 'Old app first', '2026-04-20', '__SOURCE_ID__'],
            [11, 'Manual keep 1', '2026-04-20', 'manual-import'],
            [12, 'Old app second', '2026-04-20', '__SOURCE_ID__'],
            [13, 'Manual keep 2', '2026-04-19', 'manual-import']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-disjoint',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
          columns: ['id', 'name'],
          records: [
            { id: 1, name: 'Ana' },
            { id: 2, name: 'Boris' }
          ]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({ ack, mainValues: mainSheet.getDataRange().getValues() }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
        [11, "Manual keep 1", "2026-04-20", "manual-import"],
        [13, "Manual keep 2", "2026-04-19", "manual-import"],
    ]


def test_do_post_migrates_legacy_source_marker_to_current_job_id() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [10, 'Legacy app row', '2026-04-20', '__LEGACY_SOURCE_MARKER__'],
            [11, 'Manual keep', '2026-04-20', 'manual-import']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-legacy-source',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
          columns: ['id', 'name'],
          records: [{ id: 1, name: 'Ana' }]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({ ack, mainValues: mainSheet.getDataRange().getValues() }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [11, "Manual keep", "2026-04-20", "manual-import"],
    ]


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
    assert result["stageExists"] is True
    assert result["stateExists"] is True


def test_do_post_append_mode_avoids_full_sheet_read_and_batch_update() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [10, 'Old app row', '2026-04-20', '__SOURCE_ID__']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'append_export',
          run_id: 'run-append-budget',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'append',
          columns: ['id', 'name'],
          records: [{ id: 11, name: 'Ana' }]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        console.log(JSON.stringify({ ack, calls: __calls__ }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["calls"]["batchGet"] == []
    assert result["calls"]["batchUpdate"] == []
    assert result["calls"]["getDataRange"] == []


def test_do_post_replace_by_date_source_uses_one_batch_get_and_one_batch_update() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [10, 'Old app row', '2026-04-20', '__SOURCE_ID__'],
            [11, 'Manual row', '2026-04-20', 'manual-import']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-batch-budget',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
          columns: ['id', 'name'],
          records: [{ id: 1, name: 'Ana' }]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        console.log(JSON.stringify({ ack, calls: __calls__ }));
        """
    )

    assert result["ack"]["ok"] is True
    assert len(result["calls"]["batchGet"]) == 1
    assert len(result["calls"]["batchUpdate"]) == 1


def _run_backend_probe(probe: str) -> dict[str, object]:
    probe = probe.replace("__TECH_COLUMN__", TECH_COLUMN_JS)
    probe = probe.replace("__SOURCE_COLUMN__", SOURCE_COLUMN)
    probe = probe.replace("__SOURCE_ID__", SOURCE_ID)
    probe = probe.replace("__LEGACY_SOURCE_MARKER__", LEGACY_SOURCE_MARKER)
    source_files = sorted(
        path
        for path in SRC_DIR.iterdir()
        if path.is_file() and path.suffix in {".gs", ".js"}
    )
    source_loading = "eval([\n" + ",\n".join(
        f"fs.readFileSync({json.dumps(str(path))}, 'utf8')"
        for path in source_files
    ) + "\n].join('\\n'));"

    harness = f"""
const crypto = require('crypto');
const fs = require('fs');

const __calls__ = {{
  batchGet: [],
  batchUpdate: [],
  getDataRange: [],
  getRange: [],
  getSheetByName: [],
  insertSheet: [],
  getSheets: [],
  getActiveSpreadsheet: [],
  openById: []
}};

function __columnIndexToLetters__(index) {{
  let value = Number(index);
  let output = '';
  while (value > 0) {{
    const offset = (value - 1) % 26;
    output = String.fromCharCode(65 + offset) + output;
    value = Math.floor((value - 1) / 26);
  }}
  return output || 'A';
}}

function __columnLettersToIndex__(letters) {{
  let value = 0;
  for (const ch of String(letters || '').toUpperCase()) {{
    value = (value * 26) + (ch.charCodeAt(0) - 64);
  }}
  return value;
}}

function __parseA1Range__(rawRange) {{
  const text = String(rawRange || '');
  const [sheetPart, rangePartRaw] = text.split('!');
  const sheetName = sheetPart.replace(/^'/, '').replace(/'$/, '');
  const rangePart = String(rangePartRaw || '');

  if (/^\\d+:\\d+$/.test(rangePart)) {{
    const [startRowText, endRowText] = rangePart.split(':');
    return {{
      sheetName,
      startRow: Number(startRowText),
      endRow: Number(endRowText),
      startColumn: 1,
      endColumn: null,
      rowOnly: true,
      columnOnly: false,
    }};
  }}

  const match = rangePart.match(/^([A-Z]+)(\\d+):([A-Z]+)?(\\d+)?$/);
  if (!match) {{
    throw new Error(`Unsupported A1 range in test harness: ${{text}}`);
  }}

  const startColumn = __columnLettersToIndex__(match[1]);
  const startRow = Number(match[2]);
  const endColumn = __columnLettersToIndex__(match[3] || match[1]);
  const endRow = match[4] ? Number(match[4]) : null;

  return {{
    sheetName,
    startRow,
    endRow,
    startColumn,
    endColumn,
    rowOnly: false,
    columnOnly: true,
  }};
}}

function __readA1Values__(rangeText) {{
  const parsed = __parseA1Range__(rangeText);
  const sheet = __sheets[parsed.sheetName];
  if (!sheet) {{
    return [];
  }}

  if (parsed.rowOnly) {{
    const rowIndex = parsed.startRow - 1;
    const row = sheet.__values[rowIndex] || [];
    const width = Math.max(sheet.getLastColumn(), row.length, 1);
    return [Array.from({{ length: width }}, (_, idx) => row[idx] ?? '')];
  }}

  const maxRow = parsed.endRow || Math.max(sheet.getLastRow(), parsed.startRow);
  const values = [];
  for (let rowIndex = parsed.startRow - 1; rowIndex < maxRow; rowIndex += 1) {{
    const sourceRow = sheet.__values[rowIndex] || [];
    const row = [];
    for (let columnIndex = parsed.startColumn - 1; columnIndex < parsed.endColumn; columnIndex += 1) {{
      row.push(sourceRow[columnIndex] ?? '');
    }}
    values.push(row);
  }}
  return values;
}}

function __applyBatchUpdateRequests__(requests) {{
  for (const request of requests || []) {{
    if (request.deleteDimension) {{
      const dim = request.deleteDimension.range;
      const sheet = Object.values(__sheets).find((item) => item.getSheetId() === dim.sheetId);
      if (!sheet || dim.dimension !== 'ROWS') {{
        continue;
      }}
      const startRow = dim.startIndex + 1;
      const count = dim.endIndex - dim.startIndex;
      if (count > 0) {{
        sheet.deleteRows(startRow, count);
      }}
      continue;
    }}

    if (request.insertDimension) {{
      const dim = request.insertDimension.range;
      const sheet = Object.values(__sheets).find((item) => item.getSheetId() === dim.sheetId);
      if (!sheet || dim.dimension !== 'ROWS') {{
        continue;
      }}
      const startRow = dim.startIndex + 1;
      const count = dim.endIndex - dim.startIndex;
      if (count > 0) {{
        sheet.insertRowsBefore(startRow, count);
      }}
    }}
  }}
}}

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
    getDataRange: () => {{
      __calls__.getDataRange.push({{ sheetName: name }});
      return __makeRange__(sheet, 1, 1, sheet.__values.length, Math.max(sheet.getLastColumn(), 1));
    }},
    getRange: (row, column, numRows = 1, numColumns = 1) => {{
      __calls__.getRange.push({{ sheetName: name, row, column, numRows, numColumns }});
      return __makeRange__(sheet, row, column, numRows, numColumns);
    }},
    clearContents: () => {{
      sheet.__values = [];
      return sheet;
    }},
    deleteRows: (startRow, howMany) => {{
      if (howMany <= 0) {{
        return sheet;
      }}
      sheet.__values.splice(Math.max(startRow - 1, 0), howMany);
      return sheet;
    }},
    insertRowsBefore: (beforeRow, howMany) => {{
      if (howMany <= 0) {{
        return sheet;
      }}
      const insertAt = Math.max(beforeRow - 1, 0);
      for (let index = 0; index < howMany; index += 1) {{
        sheet.__values.splice(insertAt, 0, []);
      }}
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
  getSheetByName: (name) => {{
    __calls__.getSheetByName.push(name);
    return __sheets[name] || null;
  }},
  insertSheet: (name) => {{
    __calls__.insertSheet.push(name);
    const sheet = __makeSheet__(name, {{ sheetId: Object.keys(__sheets).length + 1 }});
    __sheets[name] = sheet;
    return sheet;
  }},
  deleteSheet: (sheet) => {{
    delete __sheets[sheet.getName()];
  }},
  getSheets: () => {{
    __calls__.getSheets.push(true);
    return Object.values(__sheets);
  }}
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
  getActiveSpreadsheet: () => {{
    __calls__.getActiveSpreadsheet.push(true);
    return __spreadsheet;
  }},
  openById: () => {{
    __calls__.openById.push(true);
    return __spreadsheet;
  }}
}};
global.Sheets = {{
  Spreadsheets: {{
    Values: {{
      batchGet: (spreadsheetId, params) => {{
        __calls__.batchGet.push({{ spreadsheetId, params }});
        return {{
          valueRanges: (params.ranges || []).map((range) => ({{
            range,
            values: __readA1Values__(range)
          }}))
        }};
      }}
    }},
    batchUpdate: (payload, spreadsheetId) => {{
      __calls__.batchUpdate.push({{ spreadsheetId, payload }});
      __applyBatchUpdateRequests__(payload.requests || []);
      return {{}};
    }}
  }}
}};
global.__calls__ = __calls__;

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
    source_id: payload.source_id,
    write_mode: payload.write_mode,
    columns: payload.columns,
    records: payload.records
  }}));
  return crypto.createHash('sha256').update(canonical, 'utf8').digest('hex');
}};

global.__entrypoint__ = (...args) => {{
  if (typeof handleRequest === 'function') {{
    return handleRequest(...args);
  }}
  if (typeof iDBBackend !== 'undefined' && iDBBackend && typeof iDBBackend.handleRequest === 'function') {{
    return iDBBackend.handleRequest(...args);
  }}
  throw new Error('No public handleRequest entrypoint found');
}};

global.__callGet = (parameter = {{}}, context = null) => (
  __entrypoint__({{ parameter }}, 'GET', context)
);

global.__callPost = (payload, context = null) => (
  __entrypoint__({{
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
