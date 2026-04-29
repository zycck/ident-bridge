from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from app.core.constants import EXPORT_SOURCE_ID


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "google script back end"
SRC_DIR = BACKEND_DIR / "src"
LIBRARY_SCRIPT_ID = "1gCHuAaNHvQmelAnG2bLBlCoiuj1EPx0uu8D0e3leBp1XQ6X6sukBm5iu"
LIBRARY_SYMBOL = "iDBBackend"
TECH_COLUMN = "__\u0414\u0430\u0442\u0430\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0438"
TECH_COLUMN_JS = "__\u0414\u0430\u0442\u0430\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0438"
SOURCE_COLUMN = "__idb_source"
SOURCE_ID = EXPORT_SOURCE_ID
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
    assert "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435.gs" not in source_files

    combined_source = "\n".join((SRC_DIR / name).read_text(encoding="utf-8") for name in source_files)
    assert "var " not in combined_source
    for legacy_token in [
        "__stage__",
        "promotedRows",
        "runStatePrefix",
        "cleanupGateKey",
        "backendLoadRunState_",
        "backendSaveRunState_",
        "backendDeleteRunState_",
        "backendCreateRunState_",
        "backendCollectStaleRuns_",
        "backendEnsureStagingSheet_",
        "backendBuildStagingRows_",
        "backendReadPromotedRows_",
        "backendDeleteStagingSheet_",
    ]:
        assert legacy_token not in combined_source


def test_library_project_keeps_connection_template_outside_src() -> None:
    library_template = SRC_DIR / "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435.gs"
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
    assert "function doGet(" not in backend_source
    assert "function doPost(" not in backend_source
    assert "var iDBBackend =" not in backend_source


def test_do_get_supports_only_ping_and_sheets_without_maintenance_calls() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [['id', 'name', '__TECH_COLUMN__']]
        });

        const ping = JSON.parse(__callGet({ action: 'ping' }));
        const sheets = JSON.parse(__callGet({ action: 'sheets' }));
        const invalid = JSON.parse(__callGet({ action: 'headers' }));

        console.log(JSON.stringify({ ping, sheets, invalid, calls: __calls__ }));
        """
    )

    assert result["ping"]["ok"] is True
    assert result["ping"]["status"] == "ready"
    assert result["ping"]["message"] == "pong"
    assert result["sheets"]["sheets"] == ["Reports"]
    assert "sheet_names" not in result["sheets"]
    assert result["invalid"]["ok"] is False
    assert result["invalid"]["error_code"] == "INVALID_ACTION"
    assert result["calls"]["batchGet"] == []
    assert result["calls"]["batchUpdate"] == []


def test_do_post_single_chunk_replace_by_date_source_writes_directly_without_staging() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [91, 'Old app row', '2026-04-20', '__SOURCE_ID__'],
            [77, 'Manual row', '2026-04-20', ''],
            [50, 'Keep', '2026-04-19', '__SOURCE_ID__']
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
          propertyCount: Object.keys(__propertyStore.getProperties()).length,
          calls: __calls__
        }));
        """
    )

    assert result["ack"]["ok"] is True
    assert result["ack"]["status"] == "accepted"
    assert result["ack"]["rows_written"] == 2
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
        [77, "Manual row", "2026-04-20", ""],
        [50, "Keep", "2026-04-19", SOURCE_ID],
    ]
    assert result["hiddenColumns"] == [3, 4]
    assert result["propertyCount"] == 0
    assert len(result["calls"]["batchGet"]) == 1


def test_do_post_replace_by_date_source_keeps_numeric_foreign_sources_untouched() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [90, 'Legacy zero', '2026-04-20', '0'],
            [91, 'Legacy one', '2026-04-20', '1'],
            [77, 'External row', '2026-04-20', 'external'],
            [50, 'Keep', '2026-04-19', '1']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-numeric-foreign',
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
          mainValues: mainSheet.getDataRange().getValues()
        }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [90, "Legacy zero", "2026-04-20", "0"],
        [91, "Legacy one", "2026-04-20", "1"],
        [77, "External row", "2026-04-20", "external"],
        [50, "Keep", "2026-04-19", "1"],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
    ]


def test_do_post_multi_chunk_replace_all_clears_on_first_chunk_then_appends() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Directory', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [91, 'Old app row', '2026-04-20', '__SOURCE_ID__'],
            [77, 'Manual row', '2026-04-20', 'manual']
          ]
        });

        const chunk1 = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'directory_export',
          run_id: 'run-replace-all',
          chunk_index: 1,
          total_chunks: 2,
          total_rows: 3,
          chunk_rows: 2,
          sheet_name: 'Directory',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_all',
          columns: ['id', 'name'],
          records: [
            { id: 1, name: 'Ana' },
            { id: 2, name: 'Boris' }
          ]
        };
        chunk1.checksum = __checksum__(chunk1);

        const chunk2 = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'directory_export',
          run_id: 'run-replace-all',
          chunk_index: 2,
          total_chunks: 2,
          total_rows: 3,
          chunk_rows: 1,
          sheet_name: 'Directory',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_all',
          columns: ['id', 'name'],
          records: [
            { id: 3, name: 'Vera' }
          ]
        };
        chunk2.checksum = __checksum__(chunk2);

        const first = JSON.parse(__callPost(chunk1));
        const second = JSON.parse(__callPost(chunk2));
        const mainSheet = __spreadsheet.getSheetByName('Directory');

        console.log(JSON.stringify({
          first,
          second,
          mainValues: mainSheet.getDataRange().getValues(),
          propertyCount: Object.keys(__propertyStore.getProperties()).length
        }));
        """
    )

    assert result["first"]["status"] == "accepted"
    assert result["second"]["status"] == "accepted"
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
        [3, "Vera", "2026-04-20", SOURCE_ID],
    ]
    assert result["propertyCount"] == 0


def test_do_post_replace_all_repeated_large_export_grows_grid_after_delete() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Directory', {
          sheetId: 10
        });

        function buildPayload(runId, prefix) {
          const records = Array.from({ length: 1500 }, (_, index) => ({
            probe: `${prefix}-${index}`
          }));
          const payload = {
            protocol_version: 'gas-sheet.v2',
            job_name: 'directory_export',
            run_id: runId,
            chunk_index: 1,
            total_chunks: 1,
            total_rows: records.length,
            chunk_rows: records.length,
            sheet_name: 'Directory',
            export_date: '2026-04-20',
            source_id: '__SOURCE_ID__',
            write_mode: 'replace_all',
            columns: ['probe'],
            records
          };
          payload.checksum = __checksum__(payload);
          return payload;
        }

        const first = JSON.parse(__callPost(buildPayload('run-replace-all-big-1', 'first')));
        const second = JSON.parse(__callPost(buildPayload('run-replace-all-big-2', 'second')));
        const mainSheet = __spreadsheet.getSheetByName('Directory');
        const lastRow = mainSheet.getLastRow();

        console.log(JSON.stringify({
          first,
          second,
          lastRow,
          firstData: mainSheet.getRange(2, 1, 1, 1).getValues()[0][0],
          lastData: mainSheet.getRange(lastRow, 1, 1, 1).getValues()[0][0]
        }));
        """
    )

    assert result["first"]["status"] == "accepted"
    assert result["second"]["status"] == "accepted"
    assert result["lastRow"] == 1501
    assert result["firstData"] == "second-0"
    assert result["lastData"] == "second-1499"


def test_do_post_replace_all_unfreezes_existing_sheet_before_clearing_rows() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Directory', {
          sheetId: 10,
          frozenRows: 1,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [91, 'Old app row', '2026-04-20', '__SOURCE_ID__'],
            [77, 'Manual row', '2026-04-20', 'manual']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'directory_export',
          run_id: 'run-replace-all-unfreeze',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'Directory',
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
        const mainSheet = __spreadsheet.getSheetByName('Directory');

        console.log(JSON.stringify({
          ack,
          frozenRows: mainSheet.getFrozenRows ? mainSheet.getFrozenRows() : null,
          mainValues: mainSheet.getDataRange().getValues()
        }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["frozenRows"] == 0
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
    ]


def test_do_post_multi_chunk_replace_by_date_source_clears_only_first_chunk_and_keeps_manual_rows() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [90, 'Old block A', '2026-04-20', '__SOURCE_ID__'],
            [77, 'Manual middle', '2026-04-20', 'manual'],
            [91, 'Old block B', '2026-04-20', '__SOURCE_ID__'],
            [50, 'Keep', '2026-04-19', '__SOURCE_ID__']
          ]
        });

        const chunk1 = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-date-source',
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
          run_id: 'run-date-source',
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
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({
          first,
          second,
          mainValues: mainSheet.getDataRange().getValues(),
          propertyCount: Object.keys(__propertyStore.getProperties()).length,
          calls: __calls__
        }));
        """
    )

    assert result["first"]["status"] == "accepted"
    assert result["second"]["status"] == "accepted"
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
        [77, "Manual middle", "2026-04-20", "manual"],
        [50, "Keep", "2026-04-19", SOURCE_ID],
        [3, "Vera", "2026-04-20", SOURCE_ID],
    ]
    assert result["propertyCount"] == 0
    assert len(result["calls"]["batchGet"]) == 1


def test_do_post_replace_by_date_source_unfreezes_existing_sheet_before_delete_dimension() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          frozenRows: 1,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [90, 'Old block A', '2026-04-20', '__SOURCE_ID__'],
            [91, 'Old block B', '2026-04-20', '__SOURCE_ID__']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-date-source-unfreeze',
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
          frozenRows: mainSheet.getFrozenRows ? mainSheet.getFrozenRows() : null,
          mainValues: mainSheet.getDataRange().getValues()
        }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["frozenRows"] == 0
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
    ]


def test_do_post_replace_by_month_source_replaces_only_same_month_for_same_source() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [1, 'April 03', '2026-04-03', '__SOURCE_ID__'],
            [2, 'April 15', '2026-04-15', '__SOURCE_ID__'],
            [3, 'April manual', '2026-04-15', 'manual'],
            [4, 'March 30', '2026-03-30', '__SOURCE_ID__'],
            [5, 'May 01', '2026-05-01', '__SOURCE_ID__']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'monthly_export',
          run_id: 'run-month-source',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_month_source',
          columns: ['id', 'name'],
          records: [
            { id: 10, name: 'New April 18' },
            { id: 11, name: 'New April 22' }
          ]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({
          ack,
          mainValues: mainSheet.getDataRange().getValues(),
          calls: __calls__
        }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["ack"]["rows_written"] == 2
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [10, "New April 18", "2026-04-20", SOURCE_ID],
        [11, "New April 22", "2026-04-20", SOURCE_ID],
        [3, "April manual", "2026-04-15", "manual"],
        [4, "March 30", "2026-03-30", SOURCE_ID],
        [5, "May 01", "2026-05-01", SOURCE_ID],
    ]
    assert len(result["calls"]["batchGet"]) == 1


def test_do_post_replace_by_month_source_appends_when_no_rows_match_month() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [1, 'February row', '2026-02-15', '__SOURCE_ID__']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'monthly_export',
          run_id: 'run-month-empty',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_month_source',
          columns: ['id', 'name'],
          records: [
            { id: 9, name: 'First April' }
          ]
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

    assert result["ack"]["status"] == "accepted"
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "February row", "2026-02-15", SOURCE_ID],
        [9, "First April", "2026-04-20", SOURCE_ID],
    ]


def test_do_post_replace_by_date_source_skips_batch_get_when_sheet_has_only_header_row() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('HeaderOnly', {
          sheetId: 10,
          maxRows: 1,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-date-source-header-only',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'HeaderOnly',
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
        const mainSheet = __spreadsheet.getSheetByName('HeaderOnly');

        console.log(JSON.stringify({
          ack,
          mainValues: mainSheet.getDataRange().getValues(),
          batchGetCalls: __calls__.batchGet,
        }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["batchGetCalls"] == []
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Ana", "2026-04-20", SOURCE_ID],
        [2, "Boris", "2026-04-20", SOURCE_ID],
    ]


def test_do_post_append_mode_always_writes_to_tail() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Log', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [1, 'Old', '2026-04-20', '__SOURCE_ID__']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'append_export',
          run_id: 'run-append',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'Log',
          export_date: '2026-04-21',
          source_id: '__SOURCE_ID__',
          write_mode: 'append',
          columns: ['id', 'name'],
          records: [
            { id: 2, name: 'Ana' },
            { id: 3, name: 'Boris' }
          ]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Log');

        console.log(JSON.stringify({ ack, mainValues: mainSheet.getDataRange().getValues(), calls: __calls__ }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [1, "Old", "2026-04-20", SOURCE_ID],
        [2, "Ana", "2026-04-21", SOURCE_ID],
        [3, "Boris", "2026-04-21", SOURCE_ID],
    ]
    assert result["calls"]["batchUpdate"] == []


def test_do_post_localizes_sheet_and_formats_typed_columns_on_first_chunk() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Localized', {
          sheetId: 10
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'localized_export',
          run_id: 'run-localized',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          sheet_name: 'Localized',
          export_date: '2026-04-21',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_all',
          columns: ['Period', 'DateAdded', 'DateTimeAdded', 'TimeAdded', 'Sum'],
          records: [
            {
              Period: '2026-02',
              DateAdded: '2026-02-25',
              DateTimeAdded: '2026-02-25T19:54:38',
              TimeAdded: '19:54:38',
              Sum: 5000.5
            }
          ]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Localized');
        const row = mainSheet.getDataRange().getValues()[1];

        console.log(JSON.stringify({
          ack,
          locale: __spreadsheet.getSpreadsheetLocale(),
          formats: mainSheet.getColumnFormats(),
          valueTypes: row.map((value) => typeof value),
          row,
        }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["locale"] == "ru_RU"
    assert result["formats"] == {
        "1": "MM.yyyy",
        "2": "dd.MM.yyyy",
        "3": "dd.MM.yyyy hh:mm:ss",
        "4": "hh:mm:ss",
        "5": "0.###############",
    }
    assert result["valueTypes"] == [
        "number",
        "number",
        "number",
        "number",
        "number",
        "string",
        "string",
    ]
    assert result["row"][4] == 5000.5


def test_do_post_empty_replace_all_keeps_header_only_sheet_without_format_range_crash() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('EmptyLocalized', {
          sheetId: 10,
          maxRows: 1
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'empty_export',
          run_id: 'run-empty-localized',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 0,
          chunk_rows: 0,
          sheet_name: 'EmptyLocalized',
          export_date: '2026-04-21',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_all',
          columns: ['DateAdded'],
          records: []
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('EmptyLocalized');

        console.log(JSON.stringify({
          ack,
          locale: __spreadsheet.getSpreadsheetLocale(),
          mainValues: mainSheet.getDataRange().getValues(),
        }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["locale"] == "ru_RU"
    assert result["mainValues"] == [
        ["DateAdded", TECH_COLUMN, SOURCE_COLUMN],
    ]


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

  const maxRows = sheet.getMaxRows ? sheet.getMaxRows() : Math.max(sheet.getLastRow(), 1);
  const maxColumns = sheet.getMaxColumns ? sheet.getMaxColumns() : Math.max(sheet.getLastColumn(), 1);
  const endRow = parsed.endRow || maxRows;
  const endColumn = parsed.endColumn || parsed.startColumn;
  if (
    parsed.startRow < 1
    || parsed.startRow > maxRows
    || endRow > maxRows
    || parsed.startColumn < 1
    || parsed.startColumn > maxColumns
    || endColumn > maxColumns
  ) {{
    throw new Error(
      `Range (${{rangeText}}) exceeds grid limits. Max rows: ${{maxRows}}, max columns: ${{maxColumns}}`
    );
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
    }},
    setNumberFormat: (numberFormat) => {{
      for (let columnOffset = 0; columnOffset < numColumns; columnOffset += 1) {{
        sheet.__columnFormats[startColumn + columnOffset] = numberFormat;
      }}
      return this;
    }}
  }};
}}

function __makeSheet__(name, options = {{}}) {{
  const initialValues = __cloneRows__(options.values || []);
  const sheet = {{
    __values: initialValues,
    __columnFormats: {{ ...(options.columnFormats || {{}}) }},
    __hiddenColumns: new Set(options.hiddenColumns || []),
    __hidden: Boolean(options.hidden),
    __frozenRows: options.frozenRows !== undefined ? options.frozenRows : 0,
    __maxRows: options.maxRows !== undefined ? options.maxRows : Math.max(initialValues.length, 1000),
    __maxColumns: options.maxColumns !== undefined ? options.maxColumns : Math.max(__maxColumns__(initialValues), 26),
    getName: () => name,
    getSheetId: () => options.sheetId || 1,
    getFrozenRows: () => sheet.__frozenRows,
    setFrozenRows: (value) => {{
      sheet.__frozenRows = value;
    }},
    isSheetHidden: () => sheet.__hidden,
    hideSheet: () => {{
      sheet.__hidden = true;
    }},
    getLastRow: () => sheet.__values.length,
    getLastColumn: () => __maxColumns__(sheet.__values),
    getMaxRows: () => sheet.__maxRows,
    getMaxColumns: () => sheet.__maxColumns,
    getDataRange: () => {{
      __calls__.getDataRange.push({{ sheetName: name }});
      return __makeRange__(sheet, 1, 1, sheet.__values.length, Math.max(sheet.getLastColumn(), 1));
    }},
    getRange: (row, column, numRows = 1, numColumns = 1) => {{
      if (row < 1 || column < 1 || numRows < 1 || numColumns < 1) {{
        throw new Error('Координаты диапазона находятся за пределами размеров листа.');
      }}
      const endRow = row + numRows - 1;
      const endColumn = column + numColumns - 1;
      if (endRow > sheet.__maxRows || endColumn > sheet.__maxColumns) {{
        throw new Error('Координаты диапазона находятся за пределами размеров листа.');
      }}
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
      const frozenRows = sheet.getFrozenRows();
      const nonFrozenRowCount = Math.max(sheet.__values.length - frozenRows, 0);
      if (frozenRows > 0 && startRow === frozenRows + 1 && howMany >= nonFrozenRowCount && nonFrozenRowCount > 0) {{
        throw new Error('Invalid requests[0].deleteDimension: Невозможно удалить все незакрепленные строки.');
      }}
      sheet.__values.splice(Math.max(startRow - 1, 0), howMany);
      sheet.__maxRows = Math.max(1, sheet.__maxRows - howMany);
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
      sheet.__maxRows += howMany;
      return sheet;
    }},
    insertRowsAfter: (afterRow, howMany) => {{
      if (howMany <= 0) {{
        return sheet;
      }}
      const insertAt = Math.max(afterRow, 0);
      for (let index = 0; index < howMany; index += 1) {{
        sheet.__values.splice(insertAt, 0, []);
      }}
      sheet.__maxRows += howMany;
      return sheet;
    }},
    insertColumnsAfter: (afterColumn, howMany) => {{
      if (howMany <= 0) {{
        return sheet;
      }}
      sheet.__maxColumns += howMany;
      return sheet;
    }},
    hideColumns: (column, count) => {{
      for (let index = 0; index < count; index += 1) {{
        sheet.__hiddenColumns.add(column + index);
      }}
    }},
    getHiddenColumns: () => Array.from(sheet.__hiddenColumns).sort((left, right) => left - right),
    getColumnFormats: () => Object.fromEntries(
      Object.entries(sheet.__columnFormats).sort((left, right) => Number(left[0]) - Number(right[0]))
    ),
  }};

  return sheet;
}}

const __sheets = Object.create(null);
const __spreadsheet = {{
  __locale: 'en_US',
  getId: () => 'spreadsheet-id',
  getSpreadsheetLocale: () => __spreadsheet.__locale,
  setSpreadsheetLocale: (value) => {{
    __spreadsheet.__locale = value;
    return __spreadsheet;
  }},
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
__propertyStore.getProperties = () => Object.fromEntries(__propertyStore.entries());
global.__propertyStore = {{
  get: (key) => __propertyStore.get(key),
  getProperties: () => Object.fromEntries(__propertyStore.entries()),
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
