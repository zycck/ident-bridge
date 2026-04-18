# Google Apps Script Webhook Backend

This folder contains a compact Google Apps Script reference backend for chunked webhook ingest.

## What it does

- Exposes global `doGet` and `doPost` entrypoints.
- Accepts chunked ingest payloads with `protocol_version`, `job_name`, `run_id`, `chunk_index`, `total_chunks`, `total_rows`, `chunk_rows`, `chunk_bytes`, `schema`, and `records`.
- Reads the data header once per request and writes data + audit ledger in one batched Sheets API call on the steady-state path.
- Maintains idempotency primarily with `PropertiesService` and `CacheService`; the hidden ledger sheet named `_idem_ledger_v1` is audit-first and used only as a recovery fallback if the completion marker drifts.
- Clears run-scoped property markers after the final chunk succeeds so temporary idempotency state does not accumulate across finished runs.
- Applies schema policy v1:
  - append-right additions are allowed
  - reorder-by-name is allowed
  - missing, removed, rename-like, empty, and duplicate columns are blocked
- Uses Apps Script V8 / ES6+ syntax and the Advanced Sheets service.

## Files

- `src/00_entry.js` - web entrypoints and request orchestration
- `src/10_ingest.js` - request parsing, validation, schema policy, and ack builders
- `src/20_storage.js` - `SheetsStore`, idempotency state, and batched Sheets writes
- `src/30_shared.js` - config, logging, JSON responses, and shared helpers

## Deployment

1. Open the Apps Script editor for your target spreadsheet or create a standalone Apps Script project.
2. Copy the contents of this folder into the script project.
3. In the Apps Script editor, make sure the manifest includes the Advanced Sheets service (`Sheets`, `sheets`, `v4`), or enable it in **Services** for existing projects.
4. If you are using a standalone project, set `targetSpreadsheetId` in `src/30_shared.js`.
5. Create a deployment as a Web App.
6. Set access to the intended audience and execute as the deploying user.
7. Send POST requests with JSON payloads to the deployed web app URL.

## Payload shape

The backend expects a JSON body with this shape:

```json
{
  "protocol_version": "gas-sheet.v1",
  "job_name": "nightly_export",
  "run_id": "run-2026-04-18-001",
  "chunk_index": 1,
  "total_chunks": 4,
  "total_rows": 1200,
  "chunk_rows": 300,
  "chunk_bytes": 4096,
  "schema": {
    "mode": "append_only_v1",
    "columns": ["id", "email", "status"],
    "checksum": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  },
  "records": [
    { "id": "1", "email": "a@example.com", "status": "active" }
  ]
}
```

## Acknowledgements

Successful responses return `status: "accepted"` when the schema is unchanged or reordered-by-name, and `status: "schema_extended"` when new columns are appended to the right. A successful response looks like:

```json
{
  "ok": true,
  "status": "schema_extended",
  "run_id": "run-2026-04-18-001",
  "chunk_index": 1,
  "rows_received": 300,
  "rows_written": 300,
  "retryable": false,
  "schema_action": "extended",
  "added_columns": ["status"],
  "message": "Chunk written successfully"
}
```

Duplicate replays return a success-shaped ack with `status: "duplicate"` and `rows_written: 0`.

Failures return:

```json
{
  "ok": false,
  "error_code": "SCHEMA_MISMATCH_RENAME_OR_REMOVE",
  "retryable": false,
  "run_id": "run-2026-04-18-001",
  "chunk_index": 1,
  "message": "Incoming columns removed or renamed existing columns",
  "details": {
    "missing_columns": ["email"]
  }
}
```

## Limitations

- The implementation targets one spreadsheet at a time.
- Apps Script does not provide a true transactional rollback for sheet writes.
- The schema policy is intentionally strict and blocks ambiguous column changes.
- Logging is intentionally conservative and avoids payload values, URLs, and tokens.
- `schema.mode` must be `append_only_v1`.
- `chunk_index` is 1-based and must be within `1..total_chunks`.
- The first bootstrap request may issue extra structural spreadsheet calls to create or configure sheets.
