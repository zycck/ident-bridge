const CONFIG = Object.freeze({
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
  maxLogPreviewLength: 120,
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

function isPlainObject_(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
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
  } catch (error) {
    return defaultValue;
  }
}

function trimTrailingBlankCells_(row) {
  let end = row.length;
  while (end > 0 && (row[end - 1] === '' || row[end - 1] === null || row[end - 1] === undefined)) {
    end -= 1;
  }
  return row.slice(0, end);
}

function escapeFormulaValue_(value) {
  if (typeof value !== 'string' || !value.length) {
    return value;
  }

  const first = value.charAt(0);
  if (first === '=' || first === '+' || first === '-' || first === '@' || first === '\t' || first === '\r' || first === '\n') {
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
