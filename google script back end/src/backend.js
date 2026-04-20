/* ==================== 1. CONFIG ==================== */

var CONFIG = Object.freeze({
  protocolVersion: 'gas-sheet.v1',
  schemaMode: 'append_only_v1',
  dataSheetName: 'ingest_chunks_v1',
  ledgerSheetName: '_idem_ledger_v1',
  indexSheetName: '_dedupe_index_v2',
  legacyIndexSheetName: '_dedupe_index_v1',
  targetSpreadsheetId: '',
  idempotencyPropertyPrefix: 'idem:v1:',
  idempotencyLeaseMs: 15 * 60 * 1000,
  idempotencyCacheSeconds: 600,
  maxColumns: 200,
  maxRecordsPerChunk: 10000,
  maxChunkBytes: 5 * 1024 * 1024,
  maxLogPreviewLength: 120,
  indexBucketCount: 256,
  indexHeaders: [
    'target_key',
    'bucket_id',
    'hashes_blob',
    'updated_at',
  ],
  legacyIndexHeaderPrefixColumns: [
    'target_key',
    'sheet_name',
    'header_row',
    'dedupe_columns_json',
  ],
  legacyIndexHeaders: buildLegacyIndexHeaders_(),
  ledgerHeaders: [
    'created_at',
    'idempotency_key',
    'state',
    'run_id',
    'chunk_index',
    'job_name',
    'status',
    'error_code',
    'retryable',
    'rows_received',
    'rows_written',
    'schema_action',
    'added_columns_json',
    'message',
    'details_json',
  ],
});

function buildLegacyIndexHeaders_() {
  const headers = [
    'target_key',
    'sheet_name',
    'header_row',
    'dedupe_columns_json',
  ];

  for (let bucketIndex = 0; bucketIndex < 256; bucketIndex += 1) {
    headers.push(getBucketHeaderForIndex_(bucketIndex));
  }

  return headers;
}

/* ==================== 2. GENERIC UTILS ==================== */

function getTargetSpreadsheetId_() {
  return trimString_(CONFIG.targetSpreadsheetId);
}

function getTargetSpreadsheet_() {
  const spreadsheetId = getTargetSpreadsheetId_();
  const spreadsheet = spreadsheetId
    ? SpreadsheetApp.openById(spreadsheetId)
    : SpreadsheetApp.getActiveSpreadsheet();

  if (!spreadsheet) {
    throw createWebhookError_(
      'NO_SPREADSHEET',
      true,
      'No active spreadsheet is available for writing',
      {}
    );
  }

  return spreadsheet;
}

function getDefaultTarget_() {
  return {
    sheetName: CONFIG.dataSheetName,
    headerRow: 1,
  };
}

function getBucketHeaderForIndex_(bucketIndex) {
  let hex = Number(bucketIndex).toString(16);
  if (hex.length === 1) {
    hex = `0${hex}`;
  }
  return `bucket_${hex}`;
}

function getBucketIdForIndex_(bucketIndex) {
  let hex = Number(bucketIndex).toString(16);
  if (hex.length === 1) {
    hex = `0${hex}`;
  }
  return hex;
}

function getBucketHeaderForBucketId_(bucketId) {
  const normalized = normalizeBucketId_(bucketId);
  return `bucket_${normalized}`;
}

function getBucketIdForHash_(hash) {
  const text = String(hash || '').toLowerCase();
  const prefix = text.substring(0, 2);
  return /^([0-9a-f]{2})$/.test(prefix) ? prefix : '00';
}

function normalizeBucketId_(bucketId) {
  const text = trimString_(bucketId).toLowerCase();
  return /^([0-9a-f]{2})$/.test(text) ? text : '00';
}

function getBucketHeaderForHash_(hash) {
  return getBucketHeaderForBucketId_(getBucketIdForHash_(hash));
}

function getIndexBucketHeaders_() {
  const headers = [];
  for (let bucketIndex = 0; bucketIndex < CONFIG.indexBucketCount; bucketIndex += 1) {
    headers.push(getBucketHeaderForIndex_(bucketIndex));
  }
  return headers;
}

function buildTargetKey_(sheetName, headerRow, dedupeColumns) {
  return stableStringify_({
    sheet_name: trimString_(sheetName),
    header_row: Number(headerRow) || 1,
    dedupe_columns: Array.isArray(dedupeColumns) ? dedupeColumns.slice() : [],
  });
}

function buildIndexTargetKey_(request) {
  const target = request && request.target ? request.target : getDefaultTarget_();
  const keyColumns = request &&
    request.dedupe &&
    Array.isArray(request.dedupe.keyColumns) &&
    request.dedupe.keyColumns.length
    ? request.dedupe.keyColumns.slice()
    : request && request.schema && Array.isArray(request.schema.columns)
      ? request.schema.columns.slice()
      : [];

  return buildTargetKey_(target.sheetName, target.headerRow, keyColumns);
}

function cloneBucketSets_(bucketSets) {
  const next = Object.create(null);
  const headers = getIndexBucketHeaders_();
  for (let index = 0; index < headers.length; index += 1) {
    const header = headers[index];
    next[header] = Object.assign(
      Object.create(null),
      bucketSets && bucketSets[header] ? bucketSets[header] : {}
    );
  }
  return next;
}

function createEmptyBucketSets_() {
  const output = Object.create(null);
  const headers = getIndexBucketHeaders_();
  for (let index = 0; index < headers.length; index += 1) {
    output[headers[index]] = Object.create(null);
  }
  return output;
}

function parseIndexBucketSets_(row) {
  const output = createEmptyBucketSets_();
  const headers = getIndexBucketHeaders_();
  for (let index = 0; index < headers.length; index += 1) {
    const header = headers[index];
    const offset = index + CONFIG.legacyIndexHeaderPrefixColumns.length;
    const values = String(row && row[offset] ? row[offset] : '').split('\n');
    for (let valueIndex = 0; valueIndex < values.length; valueIndex += 1) {
      const value = trimString_(values[valueIndex]);
      if (value) {
        output[header][value] = true;
      }
    }
  }
  return output;
}

function getNonEmptyBucketHeaders_(bucketSets) {
  const headers = [];
  const knownHeaders = getIndexBucketHeaders_();
  for (let index = 0; index < knownHeaders.length; index += 1) {
    const header = knownHeaders[index];
    if (Object.keys(bucketSets && bucketSets[header] ? bucketSets[header] : {}).length) {
      headers.push(header);
    }
  }
  return headers;
}

function buildRecordDedupeHash_(request, record) {
  const target = request && request.target ? request.target : getDefaultTarget_();
  const keyColumns = request &&
    request.dedupe &&
    Array.isArray(request.dedupe.keyColumns) &&
    request.dedupe.keyColumns.length
    ? request.dedupe.keyColumns.slice()
    : request && request.schema && Array.isArray(request.schema.columns)
      ? request.schema.columns.slice()
      : [];
  const payload = {
    target: {
      sheet_name: target.sheetName,
      header_row: target.headerRow,
    },
    key_columns: keyColumns,
    values: {},
  };

  for (let index = 0; index < keyColumns.length; index += 1) {
    const column = keyColumns[index];
    payload.values[column] = record && Object.prototype.hasOwnProperty.call(record, column)
      ? record[column]
      : null;
  }

  return sha256Hex_(stableStringify_(payload));
}

function buildIndexBucketRowValues_(targetKey, bucketId, bucketSets, updatedAt) {
  const bucketHeader = getBucketHeaderForBucketId_(bucketId);
  const hashes = Object.keys(
    bucketSets && bucketSets[bucketHeader] ? bucketSets[bucketHeader] : {}
  ).sort();
  return [
    targetKey,
    normalizeBucketId_(bucketId),
    hashes.join('\n'),
    updatedAt || nowIso_(),
  ];
}

function buildIndexRowValues_(request, bucketSets, updatedAt) {
  const targetKey = buildIndexTargetKey_(request);
  const rows = [];
  const headers = getNonEmptyBucketHeaders_(bucketSets || createEmptyBucketSets_());
  for (let index = 0; index < headers.length; index += 1) {
    const bucketHeader = headers[index];
    rows.push(
      buildIndexBucketRowValues_(
        targetKey,
        bucketHeader.substring('bucket_'.length),
        bucketSets,
        updatedAt
      )
    );
  }
  return rows;
}

function createWebhookError_(errorCode, retryable, message, details) {
  const error = new Error(message);
  error.webhookError = true;
  error.errorCode = errorCode;
  error.retryable = retryable === true;
  error.details = details || {};
  return error;
}

function makeJsonResponse_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function trimString_(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeColumnName_(value) {
  if (value === null || value === undefined) {
    return '';
  }

  return String(value).trim();
}

function toIntegerOrNull_(value) {
  if (typeof value === 'number' && isFinite(value) && Math.floor(value) === value) {
    return value;
  }

  if (typeof value === 'string' && /^\s*-?\d+\s*$/.test(value)) {
    return parseInt(value, 10);
  }

  return null;
}

function sameSequence_(left, right) {
  if (left.length !== right.length) {
    return false;
  }

  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) {
      return false;
    }
  }

  return true;
}

function toLookupSet_(values) {
  const set = Object.create(null);
  for (let index = 0; index < values.length; index += 1) {
    set[values[index]] = true;
  }
  return set;
}

function difference_(values, lookupSet) {
  const output = [];
  for (let index = 0; index < values.length; index += 1) {
    if (!lookupSet[values[index]]) {
      output.push(values[index]);
    }
  }
  return output;
}

function cloneObject_(value) {
  return JSON.parse(JSON.stringify(value));
}

function cloneArray_(value) {
  return Array.isArray(value) ? value.slice(0) : [];
}

function parseJsonOrDefault_(value, defaultValue) {
  if (value === null || value === undefined || value === '') {
    return defaultValue;
  }

  try {
    return JSON.parse(value);
  } catch (_error) {
    return defaultValue;
  }
}

function trimTrailingBlankCells_(row) {
  let end = row.length;
  while (
    end > 0 &&
    (row[end - 1] === '' || row[end - 1] === null || row[end - 1] === undefined)
  ) {
    end -= 1;
  }
  return row.slice(0, end);
}

function escapeFormulaValue_(value) {
  if (typeof value !== 'string' || !value.length) {
    return value;
  }

  const first = value.charAt(0);
  if (
    first === '=' ||
    first === '+' ||
    first === '-' ||
    first === '@' ||
    first === '\t' ||
    first === '\r' ||
    first === '\n'
  ) {
    return `'${value}`;
  }

  return value;
}

function trimToLength_(value, maxLength) {
  if (typeof value !== 'string' || value.length <= maxLength) {
    return value;
  }

  return `${value.substring(0, maxLength)}...`;
}

function stableStringify_(value) {
  return JSON.stringify(normalizeForStableStringify_(value));
}

function normalizeForStableStringify_(value) {
  if (value === null || value === undefined) {
    return value;
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (Array.isArray(value)) {
    return value.map((item) => normalizeForStableStringify_(item));
  }

  if (isPlainObject_(value)) {
    const objectValue = {};
    const keys = Object.keys(value).sort();

    for (let index = 0; index < keys.length; index += 1) {
      const key = keys[index];
      objectValue[key] = normalizeForStableStringify_(value[key]);
    }

    return objectValue;
  }

  return value;
}

function sha256Hex_(value) {
  const bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    String(value),
    Utilities.Charset.UTF_8
  );

  const hex = [];
  for (let index = 0; index < bytes.length; index += 1) {
    let byteValue = bytes[index];
    if (byteValue < 0) {
      byteValue += 256;
    }

    let text = byteValue.toString(16);
    if (text.length === 1) {
      text = `0${text}`;
    }

    hex.push(text);
  }

  return hex.join('');
}

function nowIso_() {
  return new Date().toISOString();
}

function isPlainObject_(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function measureUtf8Bytes_(value) {
  if (typeof Utilities !== 'undefined' && Utilities && typeof Utilities.newBlob === 'function') {
    return Utilities.newBlob(String(value)).getBytes().length;
  }

  return unescape(encodeURIComponent(String(value))).length;
}

/* ==================== 3. LOGGING / HTTP / ERRORS ==================== */

function logRequestStart_(request) {
  logInfo_('chunk_received', {
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    total_chunks: request.totalChunks,
    chunk_rows: request.chunkRows,
    chunk_bytes: request.chunkBytes,
    schema_mode: request.schema.mode,
    column_count: request.schema.columns.length,
  });
}

function logSuccess_(ack) {
  logInfo_('chunk_success', {
    run_id: ack.run_id,
    chunk_index: ack.chunk_index,
    rows_received: ack.rows_received,
    rows_written: ack.rows_written,
    status: ack.status,
    schema_action: ack.schema_action,
  });
}

function logFailure_(ack) {
  logWarn_('chunk_failure', {
    run_id: ack.run_id,
    chunk_index: ack.chunk_index,
    error_code: ack.error_code,
    retryable: ack.retryable,
    status: ack.status || 'failed',
  });
}

function logInfo_(eventName, context) {
  writeStructuredLog_('INFO', eventName, context);
}

function logWarn_(eventName, context) {
  writeStructuredLog_('WARN', eventName, context);
}

function writeStructuredLog_(level, eventName, context) {
  Logger.log(JSON.stringify({
    level,
    event: eventName,
    time: nowIso_(),
    context: sanitizeLogContext_(context || {}),
  }));
}

function sanitizeLogContext_(context) {
  const output = {};
  const keys = Object.keys(context || {});

  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (shouldRedactLogKey_(key)) {
      continue;
    }

    output[key] = sanitizeLogValue_(context[key]);
  }

  return output;
}

function shouldRedactLogKey_(key) {
  const lowered = String(key || '').toLowerCase();
  return lowered.includes('payload') ||
    lowered.includes('records') ||
    lowered.includes('body') ||
    lowered.includes('token') ||
    lowered.includes('secret') ||
    lowered.includes('url') ||
    lowered.includes('authorization');
}

function sanitizeLogValue_(value) {
  if (value === null || value === undefined) {
    return value;
  }

  if (typeof value === 'string') {
    if (looksSensitiveString_(value)) {
      return '[redacted]';
    }

    return trimToLength_(value, CONFIG.maxLogPreviewLength);
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }

  if (Array.isArray(value)) {
    return `[array:${value.length}]`;
  }

  if (isPlainObject_(value)) {
    return `[object:${Object.keys(value).length}]`;
  }

  return '[value]';
}

function looksSensitiveString_(value) {
  const lower = String(value).toLowerCase();
  return lower.startsWith('http://') ||
    lower.startsWith('https://') ||
    lower.startsWith('bearer ') ||
    lower.includes('token') ||
    lower.includes('secret') ||
    lower.includes('password');
}

/* ==================== 4. PROTOCOL ==================== */

function protocolParseRequest_(event) {
  const raw = event && event.postData && typeof event.postData.contents === 'string'
    ? event.postData.contents
    : '';

  if (!raw) {
    throw createWebhookError_('MALFORMED_JSON', false, 'POST body must contain JSON', {
      field: 'body',
    });
  }

  if (measureUtf8Bytes_(raw) > CONFIG.maxChunkBytes) {
    throw createWebhookError_('PAYLOAD_TOO_LARGE', false, 'POST body exceeds configured payload limit', {
      max_chunk_bytes: CONFIG.maxChunkBytes,
    });
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (_error) {
    throw createWebhookError_('MALFORMED_JSON', false, 'POST body is not valid JSON', {
      field: 'body',
    });
  }

  return protocolNormalizeRequest_(payload);
}

function protocolNormalizeRequest_(payload) {
  if (!isPlainObject_(payload)) {
    throw createWebhookError_('INVALID_PAYLOAD', false, 'Request body must be a JSON object', {
      field: 'body',
    });
  }

  const protocolVersion = protocolNormalizeRequiredString_(
    payload.protocol_version,
    'protocol_version'
  );
  if (protocolVersion !== CONFIG.protocolVersion) {
    throw createWebhookError_('INVALID_PROTOCOL_VERSION', false, 'Unsupported protocol version', {
      protocol_version: protocolVersion,
    });
  }

  const jobName = protocolNormalizeRequiredString_(payload.job_name, 'job_name');
  const runId = protocolNormalizeRequiredString_(payload.run_id, 'run_id');
  const chunkIndex = protocolNormalizeRequiredInteger_(payload.chunk_index, 'chunk_index');
  const totalChunks = protocolNormalizeRequiredInteger_(payload.total_chunks, 'total_chunks');
  const totalRows = protocolNormalizeRequiredInteger_(payload.total_rows, 'total_rows');
  const chunkRows = protocolNormalizeRequiredInteger_(payload.chunk_rows, 'chunk_rows');
  const chunkBytes = protocolNormalizeRequiredInteger_(payload.chunk_bytes, 'chunk_bytes');

  if (totalChunks < 1) {
    throw createWebhookError_('INVALID_PAYLOAD', false, 'total_chunks must be at least 1', {
      field: 'total_chunks',
    });
  }

  if (chunkIndex < 1 || chunkIndex > totalChunks) {
    throw createWebhookError_(
      'INVALID_RECORDS_SHAPE',
      false,
      'chunk_index must be within total_chunks using 1-based indexing',
      { field: 'chunk_index' }
    );
  }

  if (totalRows < 0 || chunkRows < 0 || chunkBytes < 0) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'Row and byte counts must be non-negative', {
      field: 'counts',
    });
  }

  if (chunkRows > totalRows && totalRows !== 0) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'chunk_rows cannot exceed total_rows', {
      field: 'chunk_rows',
    });
  }

  if (totalRows === 0 && chunkRows !== 0) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'chunk_rows must be 0 when total_rows is 0', {
      field: 'chunk_rows',
    });
  }

  const schema = protocolNormalizeSchema_(payload.schema);
  const records = protocolNormalizeRecordList_(payload.records);
  const target = protocolNormalizeTarget_(payload.target);
  const dedupe = protocolNormalizeDedupe_(payload.dedupe, schema.columns);

  if (records.length !== chunkRows) {
    throw createWebhookError_('INVALID_PAYLOAD', false, 'chunk_rows must match records length', {
      field: 'chunk_rows',
    });
  }

  return {
    protocolVersion,
    jobName,
    runId,
    chunkIndex,
    totalChunks,
    totalRows,
    chunkRows,
    chunkBytes,
    schema,
    records,
    target,
    dedupe,
  };
}

function protocolNormalizeTarget_(target) {
  if (target === null || target === undefined) {
    return null;
  }

  if (!isPlainObject_(target)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'target must be a JSON object', {
      field: 'target',
    });
  }

  const sheetName = protocolNormalizeRequiredString_(
    target.sheet_name !== undefined ? target.sheet_name : target.sheetName,
    'target.sheet_name'
  );
  const headerRow = protocolNormalizeRequiredInteger_(
    target.header_row !== undefined ? target.header_row : target.headerRow,
    'target.header_row'
  );

  if (headerRow < 1) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'target.header_row must be at least 1', {
      field: 'target.header_row',
    });
  }

  return {
    sheetName,
    headerRow,
  };
}

function protocolNormalizeDedupe_(dedupe, schemaColumns) {
  if (dedupe === null || dedupe === undefined) {
    return null;
  }

  if (!isPlainObject_(dedupe)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'dedupe must be a JSON object', {
      field: 'dedupe',
    });
  }

  const keyColumns = protocolNormalizeColumnList_(dedupe.key_columns !== undefined
    ? dedupe.key_columns
    : dedupe.keyColumns);
  if (!keyColumns.length) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'dedupe.key_columns must not be empty', {
      field: 'dedupe.key_columns',
    });
  }

  const schemaLookup = toLookupSet_(schemaColumns);
  const missing = difference_(keyColumns, schemaLookup);
  if (missing.length) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'dedupe.key_columns must exist in schema.columns', {
      field: 'dedupe.key_columns',
      missing_columns: missing,
    });
  }

  return {
    keyColumns,
  };
}

function protocolNormalizeSchema_(schema) {
  if (!isPlainObject_(schema)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'schema must be a JSON object', {
      field: 'schema',
    });
  }

  const mode = protocolNormalizeRequiredString_(schema.mode, 'schema.mode').toLowerCase();
  if (mode !== CONFIG.schemaMode) {
    throw createWebhookError_('INVALID_PROTOCOL_VERSION', false, 'Unsupported schema mode', {
      field: 'schema.mode',
      schema_mode: mode,
    });
  }

  const columns = protocolNormalizeColumnList_(schema.columns);
  const checksum = protocolNormalizeRequiredString_(schema.checksum, 'schema.checksum');

  if (columns.length > CONFIG.maxColumns) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'Too many schema columns', {
      field: 'schema.columns',
    });
  }

  return { mode, columns, checksum };
}

function protocolNormalizeColumnList_(columns) {
  if (!Array.isArray(columns)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'schema.columns must be an array', {
      field: 'schema.columns',
    });
  }

  const normalized = [];
  const seen = Object.create(null);

  for (let index = 0; index < columns.length; index += 1) {
    const name = normalizeColumnName_(columns[index]);
    if (!name) {
      throw createWebhookError_('SCHEMA_EMPTY_COLUMN_NAME', false, 'Empty schema columns are blocked', {
        field: 'schema.columns',
      });
    }

    if (seen[name]) {
      throw createWebhookError_('SCHEMA_DUPLICATE_COLUMNS', false, 'Duplicate schema columns are blocked', {
        field: 'schema.columns',
      });
    }

    seen[name] = true;
    normalized.push(name);
  }

  return normalized;
}

function protocolNormalizeRecordList_(records) {
  if (!Array.isArray(records)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'records must be an array', {
      field: 'records',
    });
  }

  if (records.length > CONFIG.maxRecordsPerChunk) {
    throw createWebhookError_('PAYLOAD_TOO_LARGE', false, 'Too many records in a chunk', {
      field: 'records',
    });
  }

  return records.map((record) => {
    if (!isPlainObject_(record)) {
      throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'Each record must be a JSON object', {
        field: 'records',
      });
    }

    return cloneObject_(record);
  });
}

function protocolNormalizeRequiredString_(value, fieldName) {
  const text = trimString_(value);
  if (!text) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, `${fieldName} is required`, {
      field: fieldName,
    });
  }

  return text;
}

function protocolNormalizeRequiredInteger_(value, fieldName) {
  const integerValue = toIntegerOrNull_(value);
  if (integerValue === null) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, `${fieldName} must be an integer`, {
      field: fieldName,
    });
  }

  return integerValue;
}

function protocolBuildSuccessAck_(request, rowsWritten, schemaPlan) {
  return {
    ok: true,
    status: schemaPlan.schemaAction === 'extended' ? 'schema_extended' : 'accepted',
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    rows_received: request.chunkRows,
    rows_written: rowsWritten,
    retryable: false,
    schema_action: schemaPlan.schemaAction,
    added_columns: cloneArray_(schemaPlan.addedColumns),
    message: 'Chunk written successfully',
  };
}

function protocolBuildDuplicateAck_(request, storedRecord) {
  return {
    ok: true,
    status: 'duplicate',
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    rows_received: request.chunkRows,
    rows_written: 0,
    retryable: false,
    schema_action: storedRecord && storedRecord.schema_action
      ? storedRecord.schema_action
      : 'duplicate_replay',
    added_columns: storedRecord && storedRecord.added_columns
      ? cloneArray_(storedRecord.added_columns)
      : [],
    message: 'Chunk already processed; duplicate replay skipped',
  };
}

function protocolBuildFailureAck_(request, error) {
  const safeRequest = request || {};
  if (error && error.webhookError) {
    return {
      ok: false,
      error_code: error.errorCode || 'UNKNOWN_ERROR',
      retryable: error.retryable === true,
      run_id: safeRequest.runId || '',
      chunk_index: safeRequest.chunkIndex !== undefined ? safeRequest.chunkIndex : '',
      message: error.message || 'Request failed',
      details: error.details || {},
    };
  }

  const internalMessage = summarizeInternalErrorMessage_(error);
  return {
    ok: false,
    error_code: 'INTERNAL_WRITE_ERROR',
    retryable: true,
    run_id: safeRequest.runId || '',
    chunk_index: safeRequest.chunkIndex !== undefined ? safeRequest.chunkIndex : '',
    message: internalMessage
      ? `Unexpected server error: ${internalMessage}`
      : 'Unexpected server error',
    details: internalMessage
      ? { internal_message: internalMessage }
      : {},
  };
}

function summarizeInternalErrorMessage_(error) {
  if (!error) {
    return '';
  }

  const candidates = [
    trimString_(error.message),
    trimString_(error.name),
    trimString_(typeof error.toString === 'function' ? error.toString() : ''),
  ];

  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = trimString_(candidates[index]).replace(/^Error:\s*/, '');
    if (candidate && candidate !== 'Error' && candidate !== 'Unexpected server error') {
      return trimToLength_(candidate, CONFIG.maxLogPreviewLength);
    }
  }

  return '';
}

function buildLedgerEntry_(request, ack, state) {
  return {
    created_at: nowIso_(),
    idempotency_key: buildIdempotencyKey_(request),
    state,
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    job_name: request.jobName,
    status: ack.status || '',
    error_code: ack.error_code || '',
    retryable: ack.retryable === true ? 'TRUE' : 'FALSE',
    rows_received: ack.rows_received !== undefined ? ack.rows_received : '',
    rows_written: ack.rows_written !== undefined ? ack.rows_written : '',
    schema_action: ack.schema_action || '',
    added_columns_json: stableStringify_(ack.added_columns || []),
    message: ack.message || '',
    details_json: stableStringify_(ack.details || {}),
  };
}

function parseWebhookRequest_(event) {
  return protocolParseRequest_(event);
}

function normalizeWebhookRequest_(payload) {
  return protocolNormalizeRequest_(payload);
}

function normalizeTargetBlock_(target) {
  return protocolNormalizeTarget_(target);
}

function normalizeDedupeBlock_(dedupe, schemaColumns) {
  return protocolNormalizeDedupe_(dedupe, schemaColumns);
}

function normalizeSchemaBlock_(schema) {
  return protocolNormalizeSchema_(schema);
}

function normalizeColumnList_(columns) {
  return protocolNormalizeColumnList_(columns);
}

function normalizeRecordList_(records) {
  return protocolNormalizeRecordList_(records);
}

function normalizeRequiredString_(value, fieldName) {
  return protocolNormalizeRequiredString_(value, fieldName);
}

function normalizeRequiredInteger_(value, fieldName) {
  return protocolNormalizeRequiredInteger_(value, fieldName);
}

function buildSuccessAck_(request, rowsWritten, schemaPlan) {
  return protocolBuildSuccessAck_(request, rowsWritten, schemaPlan);
}

function buildDuplicateSuccessAck_(request, storedRecord) {
  return protocolBuildDuplicateAck_(request, storedRecord);
}

function buildFailureAck_(request, error) {
  return protocolBuildFailureAck_(request, error);
}

/* ==================== 5. SCHEMA PLANNING ==================== */

function schemaNormalizeIncomingHeaders_(values) {
  if (!Array.isArray(values)) {
    return [];
  }

  return values.map((value) => normalizeColumnName_(value));
}

function schemaBlockedTransition_(message, details) {
  return {
    allowed: false,
    schemaAction: 'blocked',
    addedColumns: [],
    targetHeaders: [],
    columnInsertions: [],
    message,
    details,
  };
}

function schemaBuildColumnInsertionPlan_(existingHeaders, targetHeaders) {
  const existing = Array.isArray(existingHeaders) ? existingHeaders.slice() : [];
  const target = Array.isArray(targetHeaders) ? targetHeaders.slice() : [];

  if (!target.length || sameSequence_(existing, target)) {
    return [];
  }

  const insertions = [];
  let existingIndex = 0;
  let targetIndex = 0;
  let insertedColumns = 0;

  while (targetIndex < target.length) {
    if (
      existingIndex < existing.length &&
      target[targetIndex] === existing[existingIndex]
    ) {
      existingIndex += 1;
      targetIndex += 1;
      continue;
    }

    const startIndex = existingIndex + insertedColumns;
    let count = 0;

    while (targetIndex < target.length) {
      if (
        existingIndex < existing.length &&
        target[targetIndex] === existing[existingIndex]
      ) {
        break;
      }

      count += 1;
      targetIndex += 1;
    }

    if (count > 0) {
      insertions.push({
        index: startIndex,
        count,
      });
      insertedColumns += count;
    }
  }

  if (existingIndex !== existing.length) {
    throw new Error('Cannot build column insertion plan for headers that remove or reorder existing columns');
  }

  return insertions;
}

function schemaDeriveWritePlan_(existingHeaders, incomingColumns) {
  const existing = schemaNormalizeIncomingHeaders_(existingHeaders);
  const incoming = schemaNormalizeIncomingHeaders_(incomingColumns);

  if (!existing.length) {
    return {
      allowed: true,
      schemaAction: 'extended',
      addedColumns: incoming.slice(),
      targetHeaders: incoming.slice(),
      columnInsertions: [],
      message: 'Initial schema registered',
      details: {},
    };
  }

  const existingSet = toLookupSet_(existing);
  const addedColumns = [];
  let existingIndex = 0;

  for (let index = 0; index < incoming.length; index += 1) {
    const incomingColumn = incoming[index];
    if (existingIndex < existing.length && incomingColumn === existing[existingIndex]) {
      existingIndex += 1;
      continue;
    }

    if (existingSet[incomingColumn]) {
      return schemaBlockedTransition_('Incoming columns reorder existing columns', {
        existing_columns: existing,
        incoming_columns: incoming,
      });
    }

    addedColumns.push(incomingColumn);
  }

  if (existingIndex !== existing.length) {
    return schemaBlockedTransition_('Incoming columns removed or renamed existing columns', {
      missing_columns: existing.slice(existingIndex),
      existing_columns: existing,
      incoming_columns: incoming,
    });
  }

  if (addedColumns.length) {
    return {
      allowed: true,
      schemaAction: 'extended',
      addedColumns,
      targetHeaders: incoming.slice(),
      columnInsertions: schemaBuildColumnInsertionPlan_(existing, incoming),
      message: 'Columns inserted while preserving existing order',
      details: {},
    };
  }

  return {
    allowed: true,
    schemaAction: 'unchanged',
    addedColumns: [],
    targetHeaders: existing.slice(),
    columnInsertions: [],
    message: 'Schema unchanged',
    details: {},
  };
}

function analyzeSchemaTransition_(existingHeaders, incomingColumns) {
  return schemaDeriveWritePlan_(existingHeaders, incomingColumns);
}

function buildColumnInsertionPlan_(existingHeaders, targetHeaders) {
  return schemaBuildColumnInsertionPlan_(existingHeaders, targetHeaders);
}

/* ==================== 6. IDEMPOTENCY ==================== */

function buildIdempotencyKey_(request) {
  return `${CONFIG.idempotencyPropertyPrefix}${sha256Hex_(stableStringify_({
    protocol_version: request.protocolVersion,
    job_name: request.jobName,
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    total_chunks: request.totalChunks,
    total_rows: request.totalRows,
    chunk_rows: request.chunkRows,
    chunk_bytes: request.chunkBytes,
    schema: {
      mode: request.schema.mode,
      columns: request.schema.columns.slice().map((column) => normalizeColumnName_(column)).sort(),
      checksum: request.schema.checksum,
    },
    target: request.target || getDefaultTarget_(),
    dedupe: request.dedupe || null,
    records: request.records,
  }))}`;
}

function getIdempotencyCompletedKey_(key) {
  return `${key}:completed`;
}

function getIdempotencyLeaseKey_(key) {
  return `${key}:lease`;
}

function getIdempotencyRunKey_(runId) {
  return `${CONFIG.idempotencyPropertyPrefix}run:${runId}`;
}

function isLeaseExpired_(leaseRecord) {
  if (!leaseRecord || !leaseRecord.expiresAt) {
    return true;
  }

  const expiresAt = new Date(leaseRecord.expiresAt).getTime();
  return isNaN(expiresAt) || expiresAt <= Date.now();
}

function idemReadState_(backend, key) {
  const cache = CacheService.getScriptCache();
  const completedKey = getIdempotencyCompletedKey_(key);
  const leaseKey = getIdempotencyLeaseKey_(key);

  const cachedCompleted = cache.get(completedKey);
  if (cachedCompleted) {
    return JSON.parse(cachedCompleted);
  }

  const properties = PropertiesService.getScriptProperties();
  const storedCompleted = properties.getProperty(completedKey);
  if (storedCompleted) {
    cache.put(completedKey, storedCompleted, CONFIG.idempotencyCacheSeconds);
    return JSON.parse(storedCompleted);
  }

  const cachedLease = cache.get(leaseKey);
  if (cachedLease) {
    const parsedLease = JSON.parse(cachedLease);
    if (parsedLease && parsedLease.state === 'processing' && !isLeaseExpired_(parsedLease)) {
      return {
        state: 'processing',
        record: parsedLease,
      };
    }

    idemClearLease_(key);
  }

  const storedLease = properties.getProperty(leaseKey);
  if (storedLease) {
    const parsedLease = JSON.parse(storedLease);
    if (parsedLease && parsedLease.state === 'processing' && !isLeaseExpired_(parsedLease)) {
      cache.put(leaseKey, storedLease, CONFIG.idempotencyCacheSeconds);
      return {
        state: 'processing',
        record: parsedLease,
      };
    }

    idemClearLease_(key);
  }

  const recoveredCompleted = idemRecoverCompletedStateFromLedger_(backend, key);
  if (recoveredCompleted) {
    idemWriteCompleted_(key, recoveredCompleted);
    return recoveredCompleted;
  }

  return null;
}

function idemWriteCompleted_(key, record) {
  const payload = JSON.stringify(record);
  const completedKey = getIdempotencyCompletedKey_(key);

  PropertiesService.getScriptProperties().setProperty(completedKey, payload);
  CacheService.getScriptCache().put(completedKey, payload, CONFIG.idempotencyCacheSeconds);
}

function idemWriteLease_(key, record) {
  const payload = JSON.stringify(record);
  const leaseKey = getIdempotencyLeaseKey_(key);

  PropertiesService.getScriptProperties().setProperty(leaseKey, payload);
  CacheService.getScriptCache().put(leaseKey, payload, CONFIG.idempotencyCacheSeconds);
}

function idemClearLease_(key) {
  const leaseKey = getIdempotencyLeaseKey_(key);
  PropertiesService.getScriptProperties().deleteProperty(leaseKey);
  CacheService.getScriptCache().remove(leaseKey);
}

function idemTrackRunKey_(runId, key) {
  const properties = PropertiesService.getScriptProperties();
  const runKey = getIdempotencyRunKey_(runId);
  const current = parseJsonOrDefault_(properties.getProperty(runKey), []);

  if (current.indexOf(key) === -1) {
    const next = current.concat([key]);
    properties.setProperty(runKey, JSON.stringify(next));
  }
}

function idemClearRunState_(runId) {
  const properties = PropertiesService.getScriptProperties();
  const cache = CacheService.getScriptCache();
  const runKey = getIdempotencyRunKey_(runId);
  const trackedKeys = parseJsonOrDefault_(properties.getProperty(runKey), []);

  for (let index = 0; index < trackedKeys.length; index += 1) {
    const key = trackedKeys[index];
    const completedKey = getIdempotencyCompletedKey_(key);
    const leaseKey = getIdempotencyLeaseKey_(key);

    properties.deleteProperty(completedKey);
    properties.deleteProperty(leaseKey);
    cache.remove(completedKey);
    cache.remove(leaseKey);
  }

  properties.deleteProperty(runKey);
}

function idemRecoverCompletedStateFromLedger_(backend, key) {
  const bootstrap = sheetEnsureBootstrap_(backend);
  const ledgerSheet = sheetGetSpreadsheet_(backend).getSheetByName(CONFIG.ledgerSheetName);

  if (!ledgerSheet) {
    return null;
  }

  const lastRow = ledgerSheet.getLastRow ? ledgerSheet.getLastRow() : 0;
  if (lastRow < 2) {
    return null;
  }

  const response = Sheets.Spreadsheets.Values.get(
    bootstrap.spreadsheetId,
    `${bootstrap.ledgerSheetName}!A2:O${lastRow}`
  );
  const rows = response && Array.isArray(response.values) ? response.values : [];

  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const row = rows[index];
    if (row[1] !== key || row[2] !== 'completed') {
      continue;
    }

    return {
      state: 'completed',
      record: {
        run_id: row[3] || '',
        chunk_index: toIntegerOrNull_(row[4]) || 0,
        status: row[6] || '',
        error_code: row[7] || '',
        retryable: row[8] === 'TRUE',
        rows_received: toIntegerOrNull_(row[9]) || 0,
        rows_written: toIntegerOrNull_(row[10]) || 0,
        schema_action: row[11] || '',
        added_columns: parseJsonOrDefault_(row[12], []),
        message: row[13] || '',
        details: parseJsonOrDefault_(row[14], {}),
      },
    };
  }

  return null;
}

function idemBeginRequest_(backend, request) {
  const key = buildIdempotencyKey_(request);
  const cachedState = idemReadState_(backend, key);

  if (cachedState && cachedState.state === 'completed') {
    return {
      state: 'completed',
      key,
      record: cachedState.record,
    };
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) {
    throw createWebhookError_('IDEMPOTENCY_BUSY', true, 'Could not obtain idempotency lock', {
      run_id: request.runId,
      chunk_index: request.chunkIndex,
    });
  }

  try {
    const lockedState = idemReadState_(backend, key);

    if (lockedState && lockedState.state === 'completed') {
      lock.releaseLock();
      return {
        state: 'completed',
        key,
        record: lockedState.record,
      };
    }

    if (lockedState && lockedState.state === 'processing') {
      throw createWebhookError_('IDEMPOTENCY_BUSY', true, 'Chunk is already being processed', {
        run_id: request.runId,
        chunk_index: request.chunkIndex,
      });
    }

    const leaseRecord = {
      state: 'processing',
      key,
      startedAt: nowIso_(),
      expiresAt: new Date(Date.now() + CONFIG.idempotencyLeaseMs).toISOString(),
      runId: request.runId,
      chunkIndex: request.chunkIndex,
    };

    idemWriteLease_(key, leaseRecord);
    return {
      state: 'acquired',
      key,
      lease: {
        key,
        lock,
      },
    };
  } catch (error) {
    lock.releaseLock();
    throw error;
  }
}

function idemFinalizeSuccess_(request, ack, lease) {
  const key = buildIdempotencyKey_(request);
  const completedRecord = {
    state: 'completed',
    completedAt: nowIso_(),
    record: {
      run_id: request.runId,
      chunk_index: request.chunkIndex,
      rows_received: ack.rows_received,
      rows_written: ack.rows_written,
      schema_action: ack.schema_action,
      added_columns: cloneArray_(ack.added_columns),
      message: ack.message,
    },
  };

  idemWriteCompleted_(key, completedRecord);
  idemTrackRunKey_(request.runId, key);
  if (request.chunkIndex === request.totalChunks) {
    idemClearRunState_(request.runId);
  }
  idemReleaseLease_(lease);
}

function idemReleaseLease_(lease) {
  if (!lease) {
    return;
  }

  idemClearLease_(lease.key);
  if (lease.lock) {
    lease.lock.releaseLock();
  }
}

/* ==================== 7. DEDUPE INDEX V2 + LEGACY MIGRATION ==================== */

function createIndexStateV2_() {
  return {
    hasRows: false,
    legacySource: false,
    rowNumbers: Object.create(null),
    bucketSets: createEmptyBucketSets_(),
  };
}

function parseHashesBlobToSet_(value) {
  const hashes = String(value || '').split('\n');
  const output = Object.create(null);
  for (let index = 0; index < hashes.length; index += 1) {
    const hash = trimString_(hashes[index]);
    if (hash) {
      output[hash] = true;
    }
  }
  return output;
}

function indexLoadStateV2_(backend, targetKey) {
  const indexSheet = sheetGetSpreadsheet_(backend).getSheetByName(CONFIG.indexSheetName);
  if (!indexSheet) {
    return createIndexStateV2_();
  }

  const lastRow = indexSheet.getLastRow ? indexSheet.getLastRow() : 0;
  if (lastRow < 2) {
    return createIndexStateV2_();
  }

  const rows = indexSheet.getRange(2, 1, lastRow - 1, CONFIG.indexHeaders.length).getValues();
  const state = createIndexStateV2_();

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    if (row[0] !== targetKey) {
      continue;
    }

    const bucketId = normalizeBucketId_(row[1]);
    const bucketHeader = getBucketHeaderForBucketId_(bucketId);
    state.hasRows = true;
    state.rowNumbers[bucketHeader] = index + 2;
    state.bucketSets[bucketHeader] = parseHashesBlobToSet_(row[2]);
  }

  return state;
}

function indexLoadLegacyState_(backend, targetKey) {
  const legacySheet = sheetGetSpreadsheet_(backend).getSheetByName(CONFIG.legacyIndexSheetName);
  if (!legacySheet) {
    return null;
  }

  const lastRow = legacySheet.getLastRow ? legacySheet.getLastRow() : 0;
  if (lastRow < 2) {
    return null;
  }

  const rows = legacySheet.getRange(2, 1, lastRow - 1, CONFIG.legacyIndexHeaders.length).getValues();
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    if (row[0] !== targetKey) {
      continue;
    }

    return {
      hasRows: false,
      legacySource: true,
      rowNumbers: Object.create(null),
      bucketSets: parseIndexBucketSets_(row),
    };
  }

  return null;
}

function indexLoadStateForTarget_(backend, targetKey) {
  const v2State = indexLoadStateV2_(backend, targetKey);
  if (v2State.hasRows) {
    return v2State;
  }

  const legacyState = indexLoadLegacyState_(backend, targetKey);
  return legacyState || v2State;
}

function indexPrepareChunk_(context, request) {
  if (!request || !Array.isArray(request.records)) {
    return {
      records: [],
      indexBucketOps: [],
    };
  }

  const baseState = context.indexStateV2 || createIndexStateV2_();
  const bucketSets = cloneBucketSets_(baseState.bucketSets);
  const accepted = [];
  const seenInChunk = Object.create(null);
  const touchedHeaders = Object.create(null);

  for (let index = 0; index < request.records.length; index += 1) {
    const record = request.records[index];
    const dedupeHash = buildRecordDedupeHash_(request, record);
    const bucketHeader = getBucketHeaderForHash_(dedupeHash);
    if (seenInChunk[dedupeHash] || bucketSets[bucketHeader][dedupeHash]) {
      continue;
    }

    accepted.push(record);
    seenInChunk[dedupeHash] = true;
    bucketSets[bucketHeader][dedupeHash] = true;
    touchedHeaders[bucketHeader] = true;
  }

  const materializeHeaders = baseState.legacySource
    ? getNonEmptyBucketHeaders_(bucketSets)
    : Object.keys(touchedHeaders).sort();
  const updatedAt = nowIso_();
  const indexBucketOps = [];

  for (let index = 0; index < materializeHeaders.length; index += 1) {
    const bucketHeader = materializeHeaders[index];
    const bucketId = bucketHeader.substring('bucket_'.length);
    indexBucketOps.push({
      bucketHeader,
      bucketId,
      rowNumber: baseState.rowNumbers[bucketHeader] || 0,
      values: buildIndexBucketRowValues_(context.targetKey, bucketId, bucketSets, updatedAt),
    });
  }

  context.indexStateV2 = {
    hasRows: baseState.hasRows || indexBucketOps.length > 0,
    legacySource: false,
    rowNumbers: Object.assign(Object.create(null), baseState.rowNumbers),
    bucketSets,
  };
  context.indexState = context.indexStateV2;

  return {
    records: accepted,
    indexBucketOps,
  };
}

/* ==================== 8. BOOTSTRAP + CONTEXT ==================== */

function createBackendState_() {
  return {
    spreadsheetId: getTargetSpreadsheetId_(),
    spreadsheet: null,
    bootstrapCache: null,
  };
}

function sheetGetSpreadsheet_(backend) {
  if (!backend.spreadsheet) {
    backend.spreadsheet = backend.spreadsheetId
      ? SpreadsheetApp.openById(backend.spreadsheetId)
      : getTargetSpreadsheet_();
  }

  return backend.spreadsheet;
}

function sheetReadColumnCount_(sheet) {
  if (sheet && sheet.getMaxColumns) {
    const maxColumns = toIntegerOrNull_(sheet.getMaxColumns());
    if (maxColumns !== null && maxColumns > 0) {
      return maxColumns;
    }
  }

  if (sheet && sheet.getLastColumn) {
    const lastColumn = toIntegerOrNull_(sheet.getLastColumn());
    if (lastColumn !== null && lastColumn > 0) {
      return lastColumn;
    }
  }

  return 26;
}

function writeNormalizeColumnCount_(value, minimum) {
  const count = toIntegerOrNull_(value);
  if (count !== null && count > 0) {
    return count;
  }
  return Math.max(26, Number(minimum) || 0);
}

function sheetEnsureTargetSheet_(backend, sheetName, headerRow) {
  const spreadsheet = sheetGetSpreadsheet_(backend);
  let sheet = spreadsheet.getSheetByName(sheetName);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(sheetName);
  }
  if (sheet.getFrozenRows && sheet.getFrozenRows() !== headerRow) {
    sheet.setFrozenRows(headerRow);
  }
  return sheet;
}

function sheetEnsureBootstrap_(backend) {
  if (backend.bootstrapCache) {
    return cloneObject_(backend.bootstrapCache);
  }

  const spreadsheet = sheetGetSpreadsheet_(backend);

  let dataSheet = spreadsheet.getSheetByName(CONFIG.dataSheetName);
  if (!dataSheet) {
    dataSheet = spreadsheet.insertSheet(CONFIG.dataSheetName);
  }
  if (dataSheet.getFrozenRows && dataSheet.getFrozenRows() !== 1) {
    dataSheet.setFrozenRows(1);
  }

  let ledgerSheet = spreadsheet.getSheetByName(CONFIG.ledgerSheetName);
  if (!ledgerSheet) {
    ledgerSheet = spreadsheet.insertSheet(CONFIG.ledgerSheetName);
  }
  if (ledgerSheet.isSheetHidden && !ledgerSheet.isSheetHidden()) {
    ledgerSheet.hideSheet();
  }
  if (ledgerSheet.getFrozenRows && ledgerSheet.getFrozenRows() !== 1) {
    ledgerSheet.setFrozenRows(1);
  }

  let indexSheet = spreadsheet.getSheetByName(CONFIG.indexSheetName);
  if (!indexSheet) {
    indexSheet = spreadsheet.insertSheet(CONFIG.indexSheetName);
  }
  if (indexSheet.isSheetHidden && !indexSheet.isSheetHidden()) {
    indexSheet.hideSheet();
  }
  if (indexSheet.getFrozenRows && indexSheet.getFrozenRows() !== 1) {
    indexSheet.setFrozenRows(1);
  }

  backend.bootstrapCache = {
    spreadsheetId: spreadsheet.getId(),
    dataSheetName: dataSheet.getName(),
    ledgerSheetName: ledgerSheet.getName(),
    indexSheetName: indexSheet.getName(),
    dataSheetId: dataSheet.getSheetId(),
    ledgerSheetId: ledgerSheet.getSheetId(),
    indexSheetId: indexSheet.getSheetId(),
    dataSheetMaxColumns: sheetReadColumnCount_(dataSheet),
    ledgerSheetMaxColumns: sheetReadColumnCount_(ledgerSheet),
    indexSheetMaxColumns: sheetReadColumnCount_(indexSheet),
  };

  return cloneObject_(backend.bootstrapCache);
}

function sheetResolveTarget_(request) {
  if (request && request.target) {
    return {
      sheetName: request.target.sheetName,
      headerRow: request.target.headerRow,
    };
  }

  return getDefaultTarget_();
}

function sheetReadRangeRow_(valueRange) {
  if (!valueRange || !Array.isArray(valueRange.values) || !valueRange.values.length) {
    return [];
  }

  const firstRow = valueRange.values[0];
  return Array.isArray(firstRow) ? firstRow : [];
}

function sheetLoadRequestContext_(backend, request) {
  const bootstrap = sheetEnsureBootstrap_(backend);
  const target = sheetResolveTarget_(request);
  const targetSheet = sheetEnsureTargetSheet_(backend, target.sheetName, target.headerRow);
  const targetKey = buildIndexTargetKey_(request);
  const response = Sheets.Spreadsheets.Values.batchGet(bootstrap.spreadsheetId, {
    ranges: [
      `${target.sheetName}!${target.headerRow}:${target.headerRow}`,
      `${bootstrap.ledgerSheetName}!1:1`,
      `${bootstrap.indexSheetName}!1:1`,
    ],
    majorDimension: 'ROWS',
  });

  const valueRanges = response && response.valueRanges ? response.valueRanges : [];
  const dataHeaders = sheetReadRangeRow_(valueRanges[0]);
  const ledgerHeaders = sheetReadRangeRow_(valueRanges[1]);
  const indexHeaders = sheetReadRangeRow_(valueRanges[2]);
  const indexStateV2 = indexLoadStateForTarget_(backend, targetKey);

  return {
    spreadsheetId: bootstrap.spreadsheetId,
    targetSheetName: targetSheet.getName(),
    targetSheetId: targetSheet.getSheetId(),
    targetHeaderRow: target.headerRow,
    targetMaxColumns: sheetReadColumnCount_(targetSheet),
    existingHeaders: trimTrailingBlankCells_(dataHeaders),
    ledgerSheetId: bootstrap.ledgerSheetId,
    ledgerHeaders: trimTrailingBlankCells_(ledgerHeaders),
    ledgerMaxColumns: bootstrap.ledgerSheetMaxColumns,
    indexSheetId: bootstrap.indexSheetId,
    indexHeaders: trimTrailingBlankCells_(indexHeaders),
    indexMaxColumns: bootstrap.indexSheetMaxColumns,
    targetKey,
    indexStateV2,
    indexState: indexStateV2,
  };
}

function sheetListSheetNames_(backend) {
  const spreadsheet = sheetGetSpreadsheet_(backend);
  const sheets = spreadsheet.getSheets ? spreadsheet.getSheets() : [];
  const names = [];

  for (let index = 0; index < sheets.length; index += 1) {
    const sheet = sheets[index];
    if (!sheet || (sheet.isSheetHidden && sheet.isSheetHidden())) {
      continue;
    }

    const name = trimString_(sheet.getName ? sheet.getName() : '');
    if (name) {
      names.push(name);
    }
  }

  return names;
}

function sheetReadHeaders_(backend, target) {
  const normalizedTarget = sheetResolveTarget_({ target });
  const sheet = sheetGetSpreadsheet_(backend).getSheetByName(normalizedTarget.sheetName);
  if (!sheet) {
    return [];
  }

  const lastColumn = sheet.getLastColumn ? sheet.getLastColumn() : 0;
  if (lastColumn < 1) {
    return [];
  }

  const range = sheet.getRange(normalizedTarget.headerRow, 1, 1, lastColumn);
  const values = range && range.getValues ? range.getValues() : [];
  return trimTrailingBlankCells_(Array.isArray(values[0]) ? values[0] : []);
}

/* ==================== 9. CHUNK PREPARATION + BATCH WRITER ==================== */

function writeCoerceCellValue_(value) {
  if (value === null || value === undefined) {
    return '';
  }

  if (value instanceof Date) {
    return escapeFormulaValue_(value.toISOString());
  }

  if (typeof value === 'string') {
    return escapeFormulaValue_(value);
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }

  return escapeFormulaValue_(stableStringify_(value));
}

function writeBuildDataRow_(record, headers) {
  return headers.map((header) => writeCoerceCellValue_(record[header]));
}

function writeBuildLedgerRow_(ledgerEntry) {
  return CONFIG.ledgerHeaders.map((header) => ledgerEntry[header] !== undefined ? ledgerEntry[header] : '');
}

function writeBuildCellData_(value) {
  if (typeof value === 'boolean') {
    return { userEnteredValue: { boolValue: value } };
  }

  if (typeof value === 'number' && isFinite(value)) {
    return { userEnteredValue: { numberValue: value } };
  }

  return {
    userEnteredValue: {
      stringValue: value === null || value === undefined ? '' : String(value),
    },
  };
}

function writeBuildAppendRowsRequest_(sheetId, rows) {
  return {
    appendCells: {
      sheetId,
      rows: rows.map((row) => ({
        values: row.map((value) => writeBuildCellData_(value)),
      })),
      fields: 'userEnteredValue',
    },
  };
}

function writeBuildUpdateRowRequest_(sheetId, rowIndex, values) {
  return {
    updateCells: {
      start: {
        sheetId,
        rowIndex,
        columnIndex: 0,
      },
      rows: [{
        values: values.map((value) => writeBuildCellData_(value)),
      }],
      fields: 'userEnteredValue',
    },
  };
}

function writeBuildInsertColumnsRequest_(sheetId, columnIndex, count) {
  return {
    insertDimension: {
      range: {
        sheetId,
        dimension: 'COLUMNS',
        startIndex: columnIndex,
        endIndex: columnIndex + count,
      },
      inheritFromBefore: columnIndex > 0,
    },
  };
}

function writeBuildAppendColumnsRequest_(sheetId, count) {
  return {
    appendDimension: {
      sheetId,
      dimension: 'COLUMNS',
      length: count,
    },
  };
}

function writeEnsureColumnCapacityRequests_(requests, sheetId, currentColumns, requiredColumns) {
  const needed = Number(requiredColumns) || 0;
  let available = writeNormalizeColumnCount_(currentColumns, needed);
  if (needed <= 0 || needed <= available) {
    return available;
  }

  requests.push(writeBuildAppendColumnsRequest_(sheetId, needed - available));
  available = needed;
  return available;
}

function writeApplyChunk_(backend, args) {
  const context = args.context;
  const schemaPlan = args.schemaPlan || {
    targetHeaders: Array.isArray(args.headers) ? args.headers.slice() : cloneArray_(context.existingHeaders),
    columnInsertions: [],
  };
  const headers = cloneArray_(schemaPlan.targetHeaders);
  const records = Array.isArray(args.records) ? args.records : [];
  const ledgerEntry = args.ledgerEntry || null;
  const indexBucketOps = Array.isArray(args.indexBucketOps) ? args.indexBucketOps : [];
  const requests = [];
  const hadLedgerHeaders = context.ledgerHeaders.length > 0;
  const hadIndexHeaders = context.indexHeaders.length > 0;

  let targetMaxColumns = writeNormalizeColumnCount_(context.targetMaxColumns, headers.length);
  let ledgerMaxColumns = writeNormalizeColumnCount_(context.ledgerMaxColumns, CONFIG.ledgerHeaders.length);
  let indexMaxColumns = writeNormalizeColumnCount_(context.indexMaxColumns, CONFIG.indexHeaders.length);

  if (headers.length && !sameSequence_(context.existingHeaders, headers)) {
    const insertions = Array.isArray(schemaPlan.columnInsertions) ? schemaPlan.columnInsertions : [];
    for (let index = 0; index < insertions.length; index += 1) {
      const insertion = insertions[index];
      requests.push(
        writeBuildInsertColumnsRequest_(
          context.targetSheetId,
          insertion.index,
          insertion.count
        )
      );
      targetMaxColumns += insertion.count;
    }
    targetMaxColumns = writeEnsureColumnCapacityRequests_(
      requests,
      context.targetSheetId,
      targetMaxColumns,
      headers.length
    );
    requests.push(writeBuildUpdateRowRequest_(context.targetSheetId, context.targetHeaderRow - 1, headers));
  }

  if (!hadLedgerHeaders) {
    ledgerMaxColumns = writeEnsureColumnCapacityRequests_(
      requests,
      context.ledgerSheetId,
      ledgerMaxColumns,
      CONFIG.ledgerHeaders.length
    );
    requests.push(writeBuildUpdateRowRequest_(context.ledgerSheetId, 0, CONFIG.ledgerHeaders));
  }

  if (indexBucketOps.length && !hadIndexHeaders) {
    indexMaxColumns = writeEnsureColumnCapacityRequests_(
      requests,
      context.indexSheetId,
      indexMaxColumns,
      CONFIG.indexHeaders.length
    );
    requests.push(writeBuildUpdateRowRequest_(context.indexSheetId, 0, CONFIG.indexHeaders));
  }

  if (records.length) {
    targetMaxColumns = writeEnsureColumnCapacityRequests_(
      requests,
      context.targetSheetId,
      targetMaxColumns,
      headers.length
    );
    requests.push(writeBuildAppendRowsRequest_(
      context.targetSheetId,
      records.map((record) => writeBuildDataRow_(record, headers))
    ));
  }

  if (ledgerEntry) {
    ledgerMaxColumns = writeEnsureColumnCapacityRequests_(
      requests,
      context.ledgerSheetId,
      ledgerMaxColumns,
      CONFIG.ledgerHeaders.length
    );
    requests.push(writeBuildAppendRowsRequest_(
      context.ledgerSheetId,
      [writeBuildLedgerRow_(ledgerEntry)]
    ));
  }

  let indexLastRowBefore = 0;
  const indexUpdates = [];
  const indexAppends = [];
  if (indexBucketOps.length) {
    indexMaxColumns = writeEnsureColumnCapacityRequests_(
      requests,
      context.indexSheetId,
      indexMaxColumns,
      CONFIG.indexHeaders.length
    );

    const indexSheet = sheetGetSpreadsheet_(backend).getSheetByName(CONFIG.indexSheetName);
    indexLastRowBefore = indexSheet && indexSheet.getLastRow ? indexSheet.getLastRow() : 0;

    for (let index = 0; index < indexBucketOps.length; index += 1) {
      const op = indexBucketOps[index];
      if (op.rowNumber) {
        indexUpdates.push(op);
      } else {
        indexAppends.push(op);
      }
    }

    for (let index = 0; index < indexUpdates.length; index += 1) {
      const op = indexUpdates[index];
      requests.push(writeBuildUpdateRowRequest_(context.indexSheetId, op.rowNumber - 1, op.values));
    }

    if (indexAppends.length) {
      requests.push(writeBuildAppendRowsRequest_(
        context.indexSheetId,
        indexAppends.map((op) => op.values)
      ));
    }
  }

  if (!requests.length) {
    return;
  }

  Sheets.Spreadsheets.batchUpdate({
    requests,
    includeSpreadsheetInResponse: false,
    responseIncludeGridData: false,
  }, context.spreadsheetId);

  if (headers.length) {
    context.existingHeaders = headers.slice();
  }
  context.targetMaxColumns = targetMaxColumns;

  if (!hadLedgerHeaders) {
    context.ledgerHeaders = CONFIG.ledgerHeaders.slice();
  }
  context.ledgerMaxColumns = ledgerMaxColumns;

  if (indexBucketOps.length) {
    if (!hadIndexHeaders) {
      context.indexHeaders = CONFIG.indexHeaders.slice();
    }
    context.indexMaxColumns = indexMaxColumns;

    let nextRowNumber = indexLastRowBefore;
    if (!hadIndexHeaders || indexLastRowBefore < 1) {
      nextRowNumber = Math.max(nextRowNumber, 1);
    }

    for (let index = 0; index < indexAppends.length; index += 1) {
      nextRowNumber += 1;
      const op = indexAppends[index];
      context.indexStateV2.rowNumbers[op.bucketHeader] = nextRowNumber;
    }

    for (let index = 0; index < indexUpdates.length; index += 1) {
      const op = indexUpdates[index];
      context.indexStateV2.rowNumbers[op.bucketHeader] = op.rowNumber;
    }

    context.indexStateV2.hasRows = true;
    context.indexState = context.indexStateV2;
  }
}

/* ==================== 10. ENTRYPOINTS ==================== */

function createSheetsStore_() {
  const backend = createBackendState_();
  const api = {
    beginRequest(request) {
      return idemBeginRequest_(backend, request);
    },

    finalizeSuccess(request, ack, lease) {
      return idemFinalizeSuccess_(request, ack, lease);
    },

    releaseLease(lease) {
      return idemReleaseLease_(lease);
    },

    ensureBootstrap() {
      return sheetEnsureBootstrap_(backend);
    },

    loadRequestContext(request) {
      return sheetLoadRequestContext_(backend, request);
    },

    prepareChunk(context, request) {
      return indexPrepareChunk_(context, request);
    },

    writeChunk(args) {
      return writeApplyChunk_(backend, args);
    },

    listSheetNames() {
      return sheetListSheetNames_(backend);
    },

    readHeaders(target) {
      return sheetReadHeaders_(backend, target);
    },
  };

  Object.defineProperty(api, '_spreadsheet', {
    get() {
      return backend.spreadsheet;
    },
    set(value) {
      backend.spreadsheet = value;
    },
  });

  Object.defineProperty(api, '_bootstrapCache', {
    get() {
      return backend.bootstrapCache;
    },
    set(value) {
      backend.bootstrapCache = value;
    },
  });

  return api;
}

let SHEETS_STORE_ = null;

function getSheetsStore_() {
  if (!SHEETS_STORE_) {
    SHEETS_STORE_ = createSheetsStore_();
  }

  return SHEETS_STORE_;
}

function doGet(event) {
  try {
    const action = trimString_(event && event.parameter ? event.parameter.action : '').toLowerCase();
    const store = getSheetsStore_();

    if (action === 'sheets') {
      const sheetNames = store.listSheetNames();
      return makeJsonResponse_({
        ok: true,
        status: 'ready',
        sheets: sheetNames,
        sheet_names: sheetNames,
        data_sheet: CONFIG.dataSheetName,
        ledger_sheet: CONFIG.ledgerSheetName,
        index_sheet: CONFIG.indexSheetName,
      });
    }

    if (action === 'headers') {
      const target = protocolNormalizeTarget_({
        sheet_name: event && event.parameter ? event.parameter.sheet_name : '',
        header_row: event && event.parameter ? event.parameter.header_row : 1,
      });
      return makeJsonResponse_({
        ok: true,
        status: 'ready',
        target: {
          sheet_name: target.sheetName,
          header_row: target.headerRow,
        },
        headers: store.readHeaders(target),
      });
    }

    return makeJsonResponse_({
      ok: true,
      status: 'ready',
      message: 'Google Apps Script webhook backend is ready',
      protocol_version: CONFIG.protocolVersion,
      data_sheet: CONFIG.dataSheetName,
      ledger_sheet: CONFIG.ledgerSheetName,
      index_sheet: CONFIG.indexSheetName,
    });
  } catch (error) {
    return makeJsonResponse_(protocolBuildFailureAck_(null, error));
  }
}

function doPost(event) {
  const store = getSheetsStore_();
  let request = null;
  let lease = null;
  let context = null;

  try {
    request = protocolParseRequest_(event);
    logRequestStart_(request);

    const startState = store.beginRequest(request);
    if (startState.state === 'completed') {
      const duplicateAck = protocolBuildDuplicateAck_(request, startState.record);
      logSuccess_(duplicateAck);
      return makeJsonResponse_(duplicateAck);
    }

    lease = startState.lease;
    context = store.loadRequestContext(request);

    const schemaPlan = schemaDeriveWritePlan_(context.existingHeaders, request.schema.columns);
    if (!schemaPlan.allowed) {
      throw createWebhookError_(
        'SCHEMA_MISMATCH_RENAME_OR_REMOVE',
        false,
        schemaPlan.message,
        schemaPlan.details
      );
    }

    const preparedChunk = store.prepareChunk(context, request);
    const successAck = protocolBuildSuccessAck_(
      request,
      preparedChunk.records.length,
      schemaPlan
    );

    store.writeChunk({
      context,
      schemaPlan,
      records: preparedChunk.records,
      ledgerEntry: buildLedgerEntry_(request, successAck, 'completed'),
      indexBucketOps: preparedChunk.indexBucketOps,
    });

    store.finalizeSuccess(request, successAck, lease);
    lease = null;

    logSuccess_(successAck);
    return makeJsonResponse_(successAck);
  } catch (error) {
    const failureAck = protocolBuildFailureAck_(request, error);

    if (lease) {
      store.releaseLease(lease);
      lease = null;
    }

    if (request && request.runId !== undefined) {
      try {
        context = context || store.loadRequestContext(request);
        store.writeChunk({
          context,
          schemaPlan: {
            targetHeaders: cloneArray_(context.existingHeaders),
            columnInsertions: [],
          },
          records: [],
          ledgerEntry: buildLedgerEntry_(request, failureAck, 'failed'),
          indexBucketOps: [],
        });
      } catch (auditError) {
        logWarn_('ledger_write_failed', {
          run_id: request.runId,
          chunk_index: request.chunkIndex,
          message: auditError && auditError.message
            ? auditError.message
            : 'Unexpected ledger write failure',
        });
      }
    }

    logFailure_(failureAck);
    return makeJsonResponse_(failureAck);
  }
}
