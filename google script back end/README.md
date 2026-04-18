# Google Apps Script Webhook Backend

This folder contains a function-first Google Apps Script reference backend for chunked webhook ingest.

## What it does

- Exposes global `doGet` and `doPost` entrypoints.
- Accepts chunked ingest payloads with `protocol_version`, `job_name`, `run_id`, `chunk_index`, `total_chunks`, `total_rows`, `chunk_rows`, `chunk_bytes`, `schema`, and `records`.
- Writes rows into a target spreadsheet sheet.
- Maintains idempotency with `PropertiesService`, `CacheService`, and a hidden ledger sheet named `_idem_ledger_v1`.
- Applies schema policy v1:
  - append-right additions are allowed
  - reorder-by-name is allowed
  - missing, removed, rename-like, empty, and duplicate columns are blocked
- Escapes formula-like cell values that start with `=`, `+`, `-`, `@`, tab, carriage return, or line feed.

## Files

- `src/00_entry.gs` - web entrypoints and request orchestration
- `src/10_config.gs` - constants and deployment knobs
- `src/20_validation.gs` - request normalization and validation
- `src/30_schema.gs` - schema policy checks and header reconciliation
- `src/40_idempotency.gs` - replay detection and lease handling
- `src/50_sheet.gs` - spreadsheet access and row writing
- `src/60_response.gs` - success/failure ack builders and JSON responses
- `src/70_logger.gs` - structured logging with redaction
- `src/80_utils.gs` - shared helpers

## Deployment

1. Open the Apps Script editor for your target spreadsheet or create a standalone Apps Script project.
2. Copy the contents of this folder into the script project.
3. If you are using a standalone project, set `TARGET_SPREADSHEET_ID` in `src/10_config.gs`.
4. Create a deployment as a Web App.
5. Set access to the intended audience and execute as the deploying user.
6. Send POST requests with JSON payloads to the deployed web app URL.

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

Successful responses return:

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

- This v1 template uses plain functions only; there are no classes.
- The implementation targets one spreadsheet at a time.
- Apps Script does not provide a true transactional rollback for sheet writes.
- The schema policy is intentionally strict and blocks ambiguous column changes.
- Logging is intentionally conservative and avoids payload values, URLs, and tokens.
- `schema.mode` must be `append_only_v1`.
- `chunk_index` is 1-based and must be within `1..total_chunks`.
