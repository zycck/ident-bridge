var CONFIG = {
  protocolVersion: 'gas-sheet.v1',
  schemaMode: 'append_only_v1',
  dataSheetName: 'ingest_chunks_v1',
  ledgerSheetName: '_idem_ledger_v1',
  targetSpreadsheetId: '',
  idempotencyPropertyPrefix: 'idem:v1:',
  idempotencyLeaseMs: 15 * 60 * 1000,
  idempotencyCacheSeconds: 600,
  maxColumns: 200,
  maxRecordsPerChunk: 10000,
  maxChunkBytes: 5 * 1024 * 1024,
  maxLogPreviewLength: 120
};

function getTargetSpreadsheetId_() {
  return trimString_(CONFIG.targetSpreadsheetId);
}
