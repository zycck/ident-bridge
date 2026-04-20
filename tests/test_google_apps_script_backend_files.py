from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "google script back end"
SRC_DIR = BACKEND_DIR / "src"
LIBRARY_SCRIPT_ID = "1gCHuAaNHvQmelAnG2bLBlCoiuj1EPx0uu8D0e3leBp1XQ6X6sukBm5iu"
LIBRARY_SYMBOL = "iDBBackend"


def _schema_checksum(columns: list[object], records: list[object]) -> str:
    payload = json.dumps(
        {"columns": columns, "records": records},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_google_apps_script_backend_is_consolidated_into_one_js_module() -> None:
    source_files = sorted(path.name for path in SRC_DIR.iterdir() if path.is_file())
    assert source_files == ["backend.js", "Подключение.gs"]


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


def test_backend_source_uses_batch_reads_and_writes_with_narrow_v2_index() -> None:
    backend_source = (SRC_DIR / "backend.js").read_text(encoding="utf-8")

    assert "Sheets.Spreadsheets.Values.batchGet" in backend_source
    assert "Sheets.Spreadsheets.batchUpdate" in backend_source
    assert "_dedupe_index_v2" in backend_source
    assert "_dedupe_index_v1" in backend_source
    assert "schemaDeriveWritePlan_" in backend_source
    assert "indexPrepareChunk_" in backend_source
    assert "appendRow(" not in backend_source
    assert "getDataRange(" not in backend_source


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
              checksum: __schemaChecksum__(['id'], [{ id: 1 }])
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


def test_do_get_supports_sheet_and_header_actions() -> None:
    result = _run_backend_probe(
        """
        global.SpreadsheetApp.getActiveSpreadsheet = () => ({
          getSheets: () => ([
            {
              getName: () => 'Exports',
              isSheetHidden: () => false,
              getLastColumn: () => 4,
              getRange: () => ({
                getValues: () => [['ignored']]
              })
            },
            {
              getName: () => 'Archive',
              isSheetHidden: () => false,
              getLastColumn: () => 3,
              getRange: () => ({
                getValues: () => [['id', 'email', 'created_at']]
              })
            },
            {
              getName: () => '_dedupe_index_v2',
              isSheetHidden: () => true,
              getLastColumn: () => 4,
              getRange: () => ({
                getValues: () => [['hidden']]
              })
            }
          ]),
          getSheetByName: (name) => name === 'Archive'
            ? {
                getName: () => 'Archive',
                getLastColumn: () => 3,
                getRange: () => ({
                  getValues: () => [['id', 'email', 'created_at']]
                })
              }
            : null
        });

        const sheets = JSON.parse(doGet({ parameter: { action: 'sheets' } }));
        const headers = JSON.parse(doGet({
          parameter: {
            action: 'headers',
            sheet_name: 'Archive',
            header_row: '2'
          }
        }));
        const ready = JSON.parse(doGet({ parameter: {} }));

        console.log(JSON.stringify({ sheets, headers, ready }));
        """
    )

    assert result["sheets"]["sheet_names"] == ["Exports", "Archive"]
    assert result["headers"]["headers"] == ["id", "email", "created_at"]
    assert result["headers"]["target"] == {"sheet_name": "Archive", "header_row": 2}
    assert result["ready"]["library_script_id"] == LIBRARY_SCRIPT_ID
    assert result["ready"]["library_symbol"] == LIBRARY_SYMBOL


def test_handle_request_supports_library_mode_for_get_and_post() -> None:
    result = _run_backend_probe(
        """
        const librarySpreadsheet = {
          getId: () => 'spreadsheet-id',
          getSheets: () => ([
            {
              getName: () => 'Exports',
              isSheetHidden: () => false,
              getLastColumn: () => 1,
              getRange: () => ({
                getValues: () => [['id']]
              })
            }
          ]),
          getSheetByName: (name) => __defaultSpreadsheet.getSheetByName(name),
          insertSheet: (name) => __defaultSpreadsheet.insertSheet(name)
        };
        global.SpreadsheetApp.getActiveSpreadsheet = () => librarySpreadsheet;

        const getResponse = JSON.parse(handleRequest({
          parameter: {
            action: 'sheets',
            token: 'secret-token'
          }
        }, 'GET', {
          expectedToken: 'secret-token'
        }));

        const postResponse = JSON.parse(handleRequest({
          postData: {
            contents: JSON.stringify({
              protocol_version: 'gas-sheet.v1',
              job_name: 'job',
              run_id: 'run-library',
              chunk_index: 1,
              total_chunks: 1,
              total_rows: 1,
              chunk_rows: 1,
              chunk_bytes: 128,
              auth_token: 'secret-token',
              schema: {
                mode: 'append_only_v1',
                columns: ['id'],
                checksum: __schemaChecksum__(['id'], [{ id: 1 }])
              },
              records: [{ id: 1 }]
            })
          }
        }, 'POST', {
          expectedToken: 'secret-token'
        }));

        console.log(JSON.stringify({ getResponse, postResponse }));
        """
    )

    assert result["getResponse"]["ok"] is True
    assert result["getResponse"]["sheet_names"] == ["Exports"]
    assert result["postResponse"]["ok"] is True
    assert result["postResponse"]["run_id"] == "run-library"


def test_do_post_accepts_matching_auth_token_in_json_body() -> None:
    result = _run_backend_probe(
        """
        __propertyStore.set('AUTH_TOKEN', 'secret-token');
        const response = JSON.parse(doPost({
          postData: {
            contents: JSON.stringify({
              protocol_version: 'gas-sheet.v1',
              job_name: 'job',
              run_id: 'run-auth',
              chunk_index: 1,
              total_chunks: 1,
              total_rows: 1,
              chunk_rows: 1,
              chunk_bytes: 128,
              auth_token: 'secret-token',
              schema: {
                mode: 'append_only_v1',
                columns: ['id'],
                checksum: __schemaChecksum__(['id'], [{ id: 1 }])
              },
              records: [{ id: 1 }]
            })
          }
        }));

        console.log(JSON.stringify(response));
        """
    )

    assert result["ok"] is True
    assert result["run_id"] == "run-auth"
    assert result["chunk_index"] == 1


def test_do_post_rejects_mismatched_auth_token() -> None:
    result = _run_backend_probe(
        """
        __propertyStore.set('AUTH_TOKEN', 'secret-token');
        const response = JSON.parse(doPost({
          postData: {
            contents: JSON.stringify({
              protocol_version: 'gas-sheet.v1',
              job_name: 'job',
              run_id: 'run-auth',
              chunk_index: 1,
              total_chunks: 1,
              total_rows: 1,
              chunk_rows: 1,
              chunk_bytes: 128,
              auth_token: 'wrong-token',
              schema: {
                mode: 'append_only_v1',
                columns: ['id'],
                checksum: __schemaChecksum__(['id'], [{ id: 1 }])
              },
              records: [{ id: 1 }]
            })
          }
        }));

        console.log(JSON.stringify(response));
        """
    )

    assert result["ok"] is False
    assert result["error_code"] == "UNAUTHORIZED"


def test_handle_request_rejects_mismatched_library_auth_token_from_context() -> None:
    result = _run_backend_probe(
        """
        const response = JSON.parse(handleRequest({
          postData: {
            contents: JSON.stringify({
              protocol_version: 'gas-sheet.v1',
              job_name: 'job',
              run_id: 'run-library-auth',
              chunk_index: 1,
              total_chunks: 1,
              total_rows: 1,
              chunk_rows: 1,
              chunk_bytes: 128,
              auth_token: 'wrong-token',
              schema: {
                mode: 'append_only_v1',
                columns: ['id'],
                checksum: __schemaChecksum__(['id'], [{ id: 1 }])
              },
              records: [{ id: 1 }]
            })
          }
        }, 'POST', {
          expectedToken: 'secret-token'
        }));

        console.log(JSON.stringify(response));
        """
    )

    assert result["ok"] is False
    assert result["error_code"] == "UNAUTHORIZED"
    assert result["api_version"] == "1.0"


def test_do_post_rejects_missing_auth_token() -> None:
    result = _run_backend_probe(
        """
        __propertyStore.set('AUTH_TOKEN', 'secret-token');
        const response = JSON.parse(doPost({
          postData: {
            contents: JSON.stringify({
              protocol_version: 'gas-sheet.v1',
              job_name: 'job',
              run_id: 'run-auth',
              chunk_index: 1,
              total_chunks: 1,
              total_rows: 1,
              chunk_rows: 1,
              chunk_bytes: 128,
              schema: {
                mode: 'append_only_v1',
                columns: ['id'],
                checksum: __schemaChecksum__(['id'], [{ id: 1 }])
              },
              records: [{ id: 1 }]
            })
          }
        }));

        console.log(JSON.stringify(response));
        """
    )

    assert result["ok"] is False
    assert result["error_code"] == "UNAUTHORIZED"


def test_response_helper_adds_api_version_to_ack_payloads() -> None:
    result = _run_backend_probe(
        """
        const successBody = JSON.parse(makeJsonResponse_(buildSuccessAck_({
          runId: 'run-ack',
          chunkIndex: 1,
          chunkRows: 1
        }, 1, {
          schemaAction: 'unchanged',
          addedColumns: []
        })));
        const failureBody = JSON.parse(makeJsonResponse_(buildFailureAck_(null, createWebhookError_(
          'UNAUTHORIZED',
          false,
          'Invalid auth token',
          { field: 'auth_token' }
        ))));

        console.log(JSON.stringify({ successBody, failureBody }));
        """
    )

    assert result["successBody"]["api_version"] == "1.0"
    assert result["failureBody"]["api_version"] == "1.0"


def test_gas_library_shim_resources_are_packaged() -> None:
    shim_path = ROOT / "resources" / "gas-shim" / "shim.gs"
    build_spec = (ROOT / "build.spec").read_text(encoding="utf-8")

    assert shim_path.is_file()
    assert re.search(
        r"\(\s*['\"]resources/gas-shim/shim\.gs['\"]\s*,\s*['\"]resources/gas-shim['\"]\s*\)",
        build_spec,
    )


def test_gas_library_has_plain_connection_template_with_script_id() -> None:
    template_path = SRC_DIR / "Подключение.gs"
    shim_path = ROOT / "resources" / "gas-shim" / "shim.gs"
    template_text = template_path.read_text(encoding="utf-8")
    shim_text = shim_path.read_text(encoding="utf-8")

    assert template_path.is_file()
    assert LIBRARY_SCRIPT_ID in template_text
    assert LIBRARY_SYMBOL in template_text
    assert "function doGet(e) {" in template_text
    assert "function doPost(e) {" in template_text
    assert "handleRequest(e, 'GET'" in template_text
    assert "handleRequest(e, 'POST'" in template_text
    assert "SHEET_ID" not in template_text
    assert "SHEET_ID" not in shim_text
    assert LIBRARY_SCRIPT_ID in shim_text


def test_backend_normalizes_target_and_dedupe_blocks() -> None:
    result = _run_backend_probe(
        """
        const normalized = normalizeWebhookRequest_({
          protocol_version: 'gas-sheet.v1',
          job_name: 'job',
          run_id: 'run-1',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          chunk_bytes: 128,
          schema: {
            mode: 'append_only_v1',
            columns: ['id', 'updated_at'],
            checksum: __schemaChecksum__(['id', 'updated_at'], [{ id: 1, updated_at: '2026-04-18' }])
          },
          target: {
            sheet_name: ' Exports ',
            header_row: '2'
          },
          dedupe: {
            key_columns: [' id ', 'updated_at']
          },
          records: [{ id: 1, updated_at: '2026-04-18' }]
        });
        console.log(JSON.stringify(normalized));
        """
    )

    assert result["target"] == {"sheetName": "Exports", "headerRow": 2}
    assert result["dedupe"] == {"keyColumns": ["id", "updated_at"]}


def test_backend_rejects_dedupe_columns_outside_schema() -> None:
    result = _run_backend_probe(
        """
        try {
          normalizeWebhookRequest_({
            protocol_version: 'gas-sheet.v1',
            job_name: 'job',
            run_id: 'run-1',
            chunk_index: 1,
            total_chunks: 1,
            total_rows: 1,
            chunk_rows: 1,
            chunk_bytes: 128,
            schema: {
              mode: 'append_only_v1',
              columns: ['id'],
              checksum: __schemaChecksum__(['id'], [{ id: 1 }])
            },
            dedupe: {
              key_columns: ['missing']
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


def test_backend_accepts_matching_checksum_during_normalization() -> None:
    result = _run_backend_probe(
        """
        const normalized = normalizeWebhookRequest_({
          protocol_version: 'gas-sheet.v1',
          job_name: 'job',
          run_id: 'run-checksum-ok',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 1,
          chunk_rows: 1,
          chunk_bytes: 128,
          schema: {
            mode: 'append_only_v1',
            columns: ['id', 'email'],
            checksum: __schemaChecksum__(['id', 'email'], [{ id: 1, email: 'a@example.com' }])
          },
          records: [{ id: 1, email: 'a@example.com' }]
        });
        console.log(JSON.stringify(normalized));
        """
    )

    assert result["schema"] == {
        "mode": "append_only_v1",
        "columns": ["id", "email"],
        "checksum": _schema_checksum(["id", "email"], [{"id": 1, "email": "a@example.com"}]),
    }
    assert result["records"] == [{"id": 1, "email": "a@example.com"}]


def test_do_post_rejects_checksum_mismatch_after_auth_validation() -> None:
    result = _run_backend_probe(
        """
        __propertyStore.set('AUTH_TOKEN', 'secret-token');
        const response = JSON.parse(doPost({
          postData: {
            contents: JSON.stringify({
              protocol_version: 'gas-sheet.v1',
              job_name: 'job',
              run_id: 'run-checksum-mismatch',
              chunk_index: 1,
              total_chunks: 1,
              total_rows: 1,
              chunk_rows: 1,
              chunk_bytes: 128,
              auth_token: 'secret-token',
              schema: {
                mode: 'append_only_v1',
                columns: ['id'],
                checksum: __schemaChecksum__(['id'], [{ id: 2 }])
              },
              records: [{ id: 1 }]
            })
          }
        }));

        console.log(JSON.stringify(response));
        """
    )

    assert result["ok"] is False
    assert result["error_code"] == "CHECKSUM_MISMATCH"
    assert result["retryable"] is False


def test_load_request_context_uses_same_target_key_as_index_rows() -> None:
    result = _run_backend_probe(
        """
        const makeSheet = (name, sheetId) => ({
          getName: () => name,
          getSheetId: () => sheetId,
          getFrozenRows: () => 1,
          setFrozenRows: () => {},
          isSheetHidden: () => name.startsWith('_'),
          hideSheet: () => {},
          getLastRow: () => 1,
          getLastColumn: () => 4,
          getMaxColumns: () => 26,
          getRange: () => ({
            getValues: () => [[]]
          })
        });

        const sheets = {
          'Employees': makeSheet('Employees', 10),
          'ingest_chunks_v1': makeSheet('ingest_chunks_v1', 11),
          '_idem_ledger_v1': makeSheet('_idem_ledger_v1', 12),
          '_dedupe_index_v2': makeSheet('_dedupe_index_v2', 13)
        };

        global.SpreadsheetApp.getActiveSpreadsheet = () => ({
          getId: () => 'spreadsheet-id',
          getSheetByName: (name) => sheets[name] || null,
          insertSheet: (name) => {
            sheets[name] = makeSheet(name, 99);
            return sheets[name];
          },
          getSheets: () => Object.values(sheets)
        });

        global.Sheets.Spreadsheets.Values.batchGet = () => ({
          valueRanges: [
            { values: [['id', 'email']] },
            { values: [['created_at']] },
            { values: [['target_key', 'bucket_id', 'hashes_blob', 'updated_at']] }
          ]
        });

        const request = {
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
          target: {
            sheetName: 'Employees',
            headerRow: 2
          },
          dedupe: {
            keyColumns: ['id']
          },
          records: [{ id: 1, email: 'a@example.com' }]
        };

        const store = getSheetsStore_();
        const context = store.loadRequestContext(request);
        const indexRows = buildIndexRowValues_(request, createEmptyBucketSets_());

        console.log(JSON.stringify({
          targetKey: context.targetKey,
          expectedTargetKey: buildIndexTargetKey_(request),
          indexRows
        }));
        """
    )

    assert result["targetKey"] == result["expectedTargetKey"]
    assert result["indexRows"] == []


def test_schema_derive_write_plan_returns_insertions_for_new_columns() -> None:
    result = _run_backend_probe(
        """
        const plan = schemaDeriveWritePlan_(
          ['id', 'email'],
          ['created_at', 'id', 'email', 'updated_at']
        );
        console.log(JSON.stringify(plan));
        """
    )

    assert result["allowed"] is True
    assert result["schemaAction"] == "extended"
    assert result["addedColumns"] == ["created_at", "updated_at"]
    assert result["targetHeaders"] == ["created_at", "id", "email", "updated_at"]
    assert result["columnInsertions"] == [{"index": 0, "count": 1}, {"index": 3, "count": 1}]


def test_schema_transition_blocks_reordering_existing_columns() -> None:
    result = _run_backend_probe(
        """
        const transition = schemaDeriveWritePlan_(['id', 'email'], ['email', 'id']);
        console.log(JSON.stringify(transition));
        """
    )

    assert result["allowed"] is False
    assert result["schemaAction"] == "blocked"


def test_prepare_chunk_filters_duplicates_and_emits_narrow_bucket_ops() -> None:
    result = _run_backend_probe(
        """
        const request = {
          protocolVersion: 'gas-sheet.v1',
          jobName: 'job',
          runId: 'run-2',
          chunkIndex: 1,
          totalChunks: 1,
          totalRows: 3,
          chunkRows: 3,
          chunkBytes: 128,
          schema: {
            mode: 'append_only_v1',
            columns: ['id'],
            checksum: 'abc'
          },
          target: {
            sheetName: 'Exports',
            headerRow: 2
          },
          dedupe: {
            keyColumns: ['id']
          },
          records: [{ id: 1 }, { id: 2 }, { id: 2 }]
        };
        const existingBuckets = createEmptyBucketSets_();
        const duplicateHash = buildRecordDedupeHash_(request, { id: 1 });
        existingBuckets[getBucketHeaderForHash_(duplicateHash)][duplicateHash] = true;
        const context = {
          targetKey: buildIndexTargetKey_(request),
          indexStateV2: {
            hasRows: true,
            legacySource: false,
            rowNumbers: Object.create(null),
            bucketSets: existingBuckets
          }
        };
        context.indexState = context.indexStateV2;

        const prepared = indexPrepareChunk_(context, request);
        console.log(JSON.stringify({
          rows: prepared.records,
          opCount: prepared.indexBucketOps.length,
          op: prepared.indexBucketOps[0]
        }));
        """
    )

    assert result["rows"] == [{"id": 2}]
    assert result["opCount"] == 1
    assert result["op"]["rowNumber"] == 0
    assert result["op"]["values"][1] == result["op"]["bucketId"]
    assert len(result["op"]["values"]) == 4


def test_prepare_chunk_materializes_legacy_v1_state_into_v2_bucket_rows() -> None:
    result = _run_backend_probe(
        """
        const request = {
          protocolVersion: 'gas-sheet.v1',
          jobName: 'job',
          runId: 'run-legacy',
          chunkIndex: 1,
          totalChunks: 1,
          totalRows: 2,
          chunkRows: 2,
          chunkBytes: 128,
          schema: {
            mode: 'append_only_v1',
            columns: ['id'],
            checksum: 'abc'
          },
          target: {
            sheetName: 'Exports',
            headerRow: 2
          },
          dedupe: {
            keyColumns: ['id']
          },
          records: [{ id: 1 }, { id: 2 }]
        };

        const legacyBuckets = createEmptyBucketSets_();
        const legacyHash = buildRecordDedupeHash_(request, { id: 1 });
        legacyBuckets[getBucketHeaderForHash_(legacyHash)][legacyHash] = true;
        const legacyRow = [
          buildIndexTargetKey_(request),
          'Exports',
          2,
          stableStringify_(['id'])
        ];
        const bucketHeaders = getIndexBucketHeaders_();
        for (let index = 0; index < bucketHeaders.length; index += 1) {
          const header = bucketHeaders[index];
          legacyRow.push(Object.keys(legacyBuckets[header]).sort().join('\\n'));
        }

        const makeSheet = (name, sheetId, rows) => ({
          getName: () => name,
          getSheetId: () => sheetId,
          getFrozenRows: () => 1,
          setFrozenRows: () => {},
          isSheetHidden: () => name.startsWith('_'),
          hideSheet: () => {},
          getLastRow: () => rows.length,
          getLastColumn: () => rows[0] ? rows[0].length : 0,
          getMaxColumns: () => 26,
          getRange: (_row, _column, numRows) => ({
            getValues: () => rows.slice(1, 1 + numRows)
          })
        });

        const sheets = {
          'Exports': makeSheet('Exports', 10, [[]]),
          'ingest_chunks_v1': makeSheet('ingest_chunks_v1', 11, [[]]),
          '_idem_ledger_v1': makeSheet('_idem_ledger_v1', 12, [[]]),
          '_dedupe_index_v2': makeSheet('_dedupe_index_v2', 13, [['target_key', 'bucket_id', 'hashes_blob', 'updated_at']]),
          '_dedupe_index_v1': makeSheet('_dedupe_index_v1', 14, [CONFIG.legacyIndexHeaders, legacyRow])
        };

        global.SpreadsheetApp.getActiveSpreadsheet = () => ({
          getId: () => 'spreadsheet-id',
          getSheetByName: (name) => sheets[name] || null,
          insertSheet: (name) => {
            sheets[name] = makeSheet(name, 99, [[]]);
            return sheets[name];
          },
          getSheets: () => Object.values(sheets)
        });

        global.Sheets.Spreadsheets.Values.batchGet = () => ({
          valueRanges: [
            { values: [['id']] },
            { values: [['created_at']] },
            { values: [['target_key', 'bucket_id', 'hashes_blob', 'updated_at']] }
          ]
        });

        const store = getSheetsStore_();
        const context = store.loadRequestContext(request);
        const prepared = store.prepareChunk(context, request);

        console.log(JSON.stringify({
          accepted: prepared.records,
          legacySourceInitiallyLoaded: context.indexState && context.indexState.legacySource === false,
          opCount: prepared.indexBucketOps.length,
          rowNumbers: prepared.indexBucketOps.map((op) => op.rowNumber),
          rowWidths: prepared.indexBucketOps.map((op) => op.values.length)
        }));
        """
    )

    assert result["accepted"] == [{"id": 2}]
    assert result["opCount"] >= 1
    assert all(row_number == 0 for row_number in result["rowNumbers"])
    assert all(width == 4 for width in result["rowWidths"])


def test_write_chunk_inserts_missing_columns_before_updating_headers() -> None:
    result = _run_backend_probe(
        """
        const captured = [];
        global.Sheets.Spreadsheets.batchUpdate = (payload) => {
          captured.push(...payload.requests);
          return {};
        };

        const store = getSheetsStore_();
        store.writeChunk({
          context: {
            spreadsheetId: 'spreadsheet-id',
            targetSheetId: 101,
            targetHeaderRow: 2,
            targetMaxColumns: 26,
            existingHeaders: ['id', 'email'],
            ledgerSheetId: 102,
            ledgerHeaders: ['created_at'],
            ledgerMaxColumns: 26,
            indexSheetId: 103,
            indexHeaders: ['target_key', 'bucket_id', 'hashes_blob', 'updated_at'],
            indexMaxColumns: 26,
            indexStateV2: createIndexStateV2_(),
            indexState: createIndexStateV2_()
          },
          schemaPlan: {
            targetHeaders: ['created_at', 'id', 'email', 'updated_at'],
            columnInsertions: [
              { index: 0, count: 1 },
              { index: 3, count: 1 }
            ]
          },
          records: [],
          ledgerEntry: null,
          indexBucketOps: []
        });

        console.log(JSON.stringify(captured));
        """
    )

    assert result[0]["insertDimension"]["range"]["startIndex"] == 0
    assert result[0]["insertDimension"]["range"]["endIndex"] == 1
    assert result[1]["insertDimension"]["range"]["startIndex"] == 3
    assert result[1]["insertDimension"]["range"]["endIndex"] == 4
    assert result[2]["updateCells"]["start"]["rowIndex"] == 1


def test_write_chunk_writes_narrow_index_rows_without_wide_expansion() -> None:
    result = _run_backend_probe(
        """
        const captured = [];
        global.Sheets.Spreadsheets.batchUpdate = (payload) => {
          captured.push(...payload.requests);
          return {};
        };

        const store = getSheetsStore_();
        store._spreadsheet = {
          getSheetByName: () => ({
            getLastRow: () => 1
          })
        };

        const context = {
          spreadsheetId: 'spreadsheet-id',
          targetSheetId: 101,
          targetHeaderRow: 2,
          targetMaxColumns: 26,
          existingHeaders: ['id'],
          ledgerSheetId: 102,
          ledgerHeaders: ['created_at'],
          ledgerMaxColumns: 26,
          indexSheetId: 103,
          indexHeaders: [],
          indexMaxColumns: 26,
          indexStateV2: createIndexStateV2_(),
          indexState: createIndexStateV2_()
        };

        store.writeChunk({
          context,
          schemaPlan: {
            targetHeaders: ['id'],
            columnInsertions: []
          },
          records: [],
          ledgerEntry: null,
          indexBucketOps: [{
            bucketHeader: 'bucket_00',
            bucketId: '00',
            rowNumber: 0,
            values: ['target-key', '00', 'hash-a\\nhash-b', '2026-04-18T10:00:00.000Z']
          }]
        });

        console.log(JSON.stringify({
          requests: captured,
          indexRowWidth: captured[captured.length - 1].appendCells.rows[0].values.length
        }));
        """
    )

    assert result["indexRowWidth"] == 4
    assert not [
        request
        for request in result["requests"]
        if "appendDimension" in request and request["appendDimension"]["sheetId"] == 103
    ]
    assert result["requests"][0]["updateCells"]["start"]["sheetId"] == 103
    assert result["requests"][1]["appendCells"]["sheetId"] == 103


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


def test_backend_internal_failure_ack_includes_root_cause_message() -> None:
    result = _run_backend_probe(
        """
        const ack = buildFailureAck_(null, new Error('Database unavailable'));
        console.log(JSON.stringify(ack));
        """
    )

    assert result["ok"] is False
    assert result["error_code"] == "INTERNAL_WRITE_ERROR"
    assert result["retryable"] is True
    assert result["message"] == "Unexpected server error: Database unavailable"
    assert result["details"] == {"internal_message": "Database unavailable"}


def _run_backend_probe(probe: str) -> dict[str, object]:
    harness = f"""
const crypto = require('crypto');
const fs = require('fs');
function __makeSheet(name, options = {{}}) {{
  return {{
    getName: () => name,
    getSheetId: () => options.sheetId || 1,
    getFrozenRows: () => options.frozenRows !== undefined ? options.frozenRows : 1,
    setFrozenRows: () => {{}},
    isSheetHidden: () => Boolean(options.hidden),
    hideSheet: () => {{
      options.hidden = true;
    }},
    getLastRow: () => options.lastRow !== undefined ? options.lastRow : 1,
    getLastColumn: () => options.lastColumn !== undefined ? options.lastColumn : 1,
    getMaxColumns: () => options.maxColumns !== undefined ? options.maxColumns : 26,
    getRange: () => ({{
      getValues: () => options.values || [[]]
    }})
  }};
}}
const __defaultSheets = Object.create(null);
const __defaultSpreadsheet = {{
  getId: () => 'spreadsheet-id',
  getSheetByName: (name) => __defaultSheets[name] || null,
  insertSheet: (name) => {{
    const sheet = __makeSheet(name, {{ sheetId: Object.keys(__defaultSheets).length + 1 }});
    __defaultSheets[name] = sheet;
    return sheet;
  }},
  getSheets: () => Object.values(__defaultSheets)
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
function __schemaChecksum__(columns, records) {{
  return sha256Hex_(stableStringify_({{
    columns: Array.isArray(columns) ? columns.slice() : [],
    records: Array.isArray(records) ? records.slice() : []
  }}));
}}
global.ContentService = {{
  MimeType: {{ JSON: 'application/json' }},
  createTextOutput: (text) => ({{ setMimeType: () => text }}),
}};
global.Logger = {{ log: () => {{}} }};
global.SpreadsheetApp = {{
  getActiveSpreadsheet: () => __defaultSpreadsheet,
  openById: () => __defaultSpreadsheet
}};
global.Sheets = {{
  Spreadsheets: {{
    Values: {{
      batchGet: () => ({{ valueRanges: [] }}),
      get: () => ({{ values: [] }})
    }},
    batchUpdate: () => ({{}})
  }}
}};
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
const source = fs.readFileSync('google script back end/src/backend.js', 'utf8');
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
