# Google Apps Script Webhook Backend

This folder contains a single-file Google Apps Script backend for chunked webhook ingest into Google Sheets.

## What it does

- Exposes global `doGet` and `doPost` entrypoints.
- Accepts chunked ingest payloads with `protocol_version`, `job_name`, `run_id`, `chunk_index`, `total_chunks`, `total_rows`, `chunk_rows`, `chunk_bytes`, `schema`, and `records`.
- Keeps the external HTTP contract unchanged while simplifying the internal Apps Script implementation into one file.
- Uses `PropertiesService` and `CacheService` for fast idempotency and the hidden `_idem_ledger_v1` sheet as an audit/recovery fallback.
- Stores dedupe state in the hidden narrow index sheet `_dedupe_index_v2`.
- Lazily migrates per-target dedupe state from legacy `_dedupe_index_v1` into `_dedupe_index_v2` on the first successful write for that target.
- Uses Apps Script V8 / ES6+ syntax and the Advanced Sheets service.

## File layout

- `src/backend.js` - the full backend implementation, split internally into these sections:
  - config and hidden-sheet schema
  - generic utilities and hashing
  - logging / error / JSON response helpers
  - request normalization / protocol validation / ACK builders
  - schema planning
  - idempotency state
  - dedupe index v2 with lazy migration from `_dedupe_index_v1`
  - spreadsheet bootstrap and request context loading
  - chunk preparation and batched Sheets writes
  - `doGet` / `doPost`

## Hidden sheets

- `ingest_chunks_v1` - default target data sheet
- `_idem_ledger_v1` - idempotency audit ledger
- `_dedupe_index_v2` - active dedupe index
- `_dedupe_index_v1` - legacy read-only source used only for lazy migration compatibility

### `_dedupe_index_v2` layout

Each dedupe row is narrow and bucket-scoped:

```text
target_key | bucket_id | hashes_blob | updated_at
```

- One row = one `target_key` + one hex bucket `00..ff`
- `hashes_blob` stores sorted SHA-256 hashes separated by `\n`
- Runtime reads only the first 4 columns from the v2 index sheet
- Runtime writes only touched bucket rows instead of rewriting a 260-column wide row

## Deployment

1. Open the Apps Script editor for your target spreadsheet or create a standalone Apps Script project.
2. Copy the contents of this folder into the script project.
3. Make sure the manifest includes the Advanced Sheets service (`Sheets`, `sheets`, `v4`), or enable it in **Services** for an existing project.
4. If you are using a standalone project, set `targetSpreadsheetId` in `src/backend.js`.
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

Successful responses return `status: "accepted"` when the schema is unchanged and `status: "schema_extended"` when new columns are inserted while preserving the order of existing columns. A successful response looks like:

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

## Notes

- The implementation targets one spreadsheet at a time.
- Apps Script does not provide a true transactional rollback for sheet writes.
- Schema policy stays strict and blocks ambiguous rename/remove/reorder cases.
- Logging stays conservative and avoids payload values, URLs, and tokens.
- `schema.mode` must be `append_only_v1`.
- `chunk_index` is 1-based and must be within `1..total_chunks`.
- The first bootstrap request may issue extra structural spreadsheet calls to create hidden sheets and initialize headers.
