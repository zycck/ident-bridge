const BACKEND_V2_CONFIG = Object.freeze({
  apiVersion: '2.0',
  protocolVersion: 'gas-sheet.v2',
  technicalDateColumnName: '__\u0414\u0430\u0442\u0430\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0438',
  technicalSourceColumnName: '__idb_source',
  legacySourceMarker: 'iDentBridge:gas-sheet:v2',
  legacySourceIds: Object.freeze(['iDentBridge:gas-sheet:v2']),
  pingMessage: 'pong',
  defaultLockTimeoutMs: 2000,
  maxPayloadBytes: 5 * 1024 * 1024,
  spreadsheetLocale: 'ru_RU',
  columnFormats: Object.freeze({
    period: 'MM.yyyy',
    date: 'dd.MM.yyyy',
    datetime: 'dd.MM.yyyy hh:mm:ss',
    time: 'hh:mm:ss',
    number: '0.###############',
  }),
  writeModes: Object.freeze({
    append: 'append',
    replaceAll: 'replace_all',
    replaceByDateSource: 'replace_by_date_source',
  }),
});

function backendHandleRequest_(event, method, context) {
  void context;
  try {
    const normalizedMethod = backendTrimString_(method).toUpperCase();
    if (normalizedMethod === 'GET') {
      return backendHandleGetRequest_(event);
    }

    if (normalizedMethod === 'POST') {
      return backendHandlePostRequest_(event);
    }

    throw backendCreateError_(
      'INVALID_REQUEST_METHOD',
      false,
      `Unsupported request method: ${normalizedMethod || '<empty>'}`,
      { method: normalizedMethod || '' }
    );
  } catch (error) {
    return backendMakeJsonResponse_(backendBuildFailurePayload_(error));
  }
}

function backendHandleGetRequest_(event) {
  const action = backendTrimString_(event?.parameter?.action).toLowerCase();
  if (action === 'ping') {
    return backendMakeJsonResponse_(backendBuildAckPayload_({
      ok: true,
      status: 'ready',
      action: 'ping',
      message: BACKEND_V2_CONFIG.pingMessage,
    }));
  }

  if (action === 'sheets') {
    const spreadsheet = backendGetSpreadsheet_(backendGetScriptProperties_());
    return backendMakeJsonResponse_(backendBuildAckPayload_({
      ok: true,
      status: 'ready',
      action: 'sheets',
      sheets: backendListVisibleSheetNames_(spreadsheet),
    }));
  }

  return backendMakeJsonResponse_(backendBuildFailurePayload_(backendCreateError_(
    'INVALID_ACTION',
    false,
    'Unsupported GET action',
    { action }
  )));
}

function backendHandlePostRequest_(event) {
  return backendWithScriptLock_(() => {
    const request = backendParseV2Request_(event);
    const spreadsheet = backendGetSpreadsheet_(backendGetScriptProperties_());
    const mainContext = backendEnsureMainSheet_(spreadsheet, request);
    const writeRequest = request.chunkIndex === 1
      ? request
      : { ...request, writeMode: BACKEND_V2_CONFIG.writeModes.append };
    backendApplyWriteMode_(spreadsheet, mainContext, writeRequest, backendBuildMainRows_(request));
    backendApplySheetLocaleAndFormats_(spreadsheet, mainContext, request);
    return backendMakeJsonResponse_(backendBuildAck_(request, 'accepted', request.chunkRows, 'Chunk accepted'));
  });
}

function backendParseV2Request_(event) {
  const raw = typeof event?.postData?.contents === 'string' ? event.postData.contents : '';
  if (!raw) {
    throw backendCreateError_('MALFORMED_JSON', false, 'POST body must contain JSON', { field: 'body' });
  }

  if (backendMeasureUtf8Bytes_(raw) > BACKEND_V2_CONFIG.maxPayloadBytes) {
    throw backendCreateError_(
      'PAYLOAD_TOO_LARGE',
      false,
      'POST body exceeds configured payload limit',
      { max_payload_bytes: BACKEND_V2_CONFIG.maxPayloadBytes }
    );
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (_error) {
    throw backendCreateError_('MALFORMED_JSON', false, 'POST body is not valid JSON', { field: 'body' });
  }

  return backendNormalizeV2Payload_(payload);
}

function backendNormalizeV2Payload_(payload) {
  if (!backendIsPlainObject_(payload)) {
    throw backendCreateError_('INVALID_PAYLOAD', false, 'Request body must be a JSON object', { field: 'body' });
  }

  const request = {
    protocolVersion: backendRequireString_(payload.protocol_version, 'protocol_version'),
    jobName: backendRequireString_(payload.job_name, 'job_name'),
    runId: backendRequireString_(payload.run_id, 'run_id'),
    chunkIndex: backendRequireInteger_(payload.chunk_index, 'chunk_index'),
    totalChunks: backendRequireInteger_(payload.total_chunks, 'total_chunks'),
    totalRows: backendRequireInteger_(payload.total_rows, 'total_rows'),
    chunkRows: backendRequireInteger_(payload.chunk_rows, 'chunk_rows'),
    sheetName: backendRequireString_(payload.sheet_name, 'sheet_name'),
    exportDate: backendRequireString_(payload.export_date, 'export_date'),
    sourceId: backendRequireString_(payload.source_id, 'source_id'),
    writeMode: backendNormalizeWriteMode_(payload.write_mode),
    checksum: backendRequireString_(payload.checksum, 'checksum'),
    columns: backendNormalizeColumns_(payload.columns),
    records: backendNormalizeRecords_(payload.records),
  };

  if (request.protocolVersion !== BACKEND_V2_CONFIG.protocolVersion) {
    throw backendCreateError_(
      'INVALID_PROTOCOL_VERSION',
      false,
      'Unsupported protocol version',
      { protocol_version: request.protocolVersion }
    );
  }

  if (request.totalChunks < 1) {
    throw backendCreateError_('INVALID_PAYLOAD', false, 'total_chunks must be at least 1', { field: 'total_chunks' });
  }

  if (request.chunkIndex < 1 || request.chunkIndex > request.totalChunks) {
    throw backendCreateError_(
      'INVALID_PAYLOAD',
      false,
      'chunk_index must be within total_chunks',
      { field: 'chunk_index', total_chunks: request.totalChunks }
    );
  }

  if (request.chunkRows !== request.records.length) {
    throw backendCreateError_(
      'INVALID_RECORDS_SHAPE',
      false,
      'chunk_rows must match the number of records',
      { field: 'chunk_rows', chunk_rows: request.chunkRows, records: request.records.length }
    );
  }

  const expectedChecksum = backendComputeRequestChecksum_(request);
  if (expectedChecksum !== request.checksum) {
    throw backendCreateError_(
      'CHECKSUM_MISMATCH',
      false,
      'Checksum mismatch',
      { expected_checksum: expectedChecksum }
    );
  }

  return request;
}

function backendRequireString_(value, fieldName) {
  const normalized = backendTrimString_(value);
  if (!normalized) {
    throw backendCreateError_('INVALID_PAYLOAD', false, `Missing ${fieldName}`, { field: fieldName });
  }
  return normalized;
}

function backendRequireInteger_(value, fieldName) {
  const normalized = backendToInteger_(value);
  if (normalized === null) {
    throw backendCreateError_('INVALID_PAYLOAD', false, `Invalid ${fieldName}`, { field: fieldName });
  }
  return normalized;
}

function backendNormalizeColumns_(value) {
  if (!Array.isArray(value) || !value.length) {
    throw backendCreateError_('INVALID_PAYLOAD', false, 'columns must be a non-empty array', { field: 'columns' });
  }

  const columns = [];
  const seen = new Set();
  for (const rawColumn of value) {
    const columnName = backendTrimString_(rawColumn);
    if (!columnName) {
      throw backendCreateError_('INVALID_PAYLOAD', false, 'columns may not contain empty values', { field: 'columns' });
    }

    const key = columnName.toLowerCase();
    if (seen.has(key)) {
      throw backendCreateError_('INVALID_PAYLOAD', false, 'columns must be unique', { field: 'columns' });
    }

    seen.add(key);
    columns.push(columnName);
  }
  return columns;
}

function backendNormalizeRecords_(value) {
  if (!Array.isArray(value)) {
    throw backendCreateError_('INVALID_RECORDS_SHAPE', false, 'records must be an array', { field: 'records' });
  }

  return value.map((record) => {
    if (!backendIsPlainObject_(record)) {
      throw backendCreateError_('INVALID_RECORDS_SHAPE', false, 'records must contain objects', { field: 'records' });
    }
    return { ...record };
  });
}

function backendNormalizeWriteMode_(value) {
  const normalized = backendTrimString_(value);
  if (Object.values(BACKEND_V2_CONFIG.writeModes).includes(normalized)) {
    return normalized;
  }

  throw backendCreateError_('INVALID_PAYLOAD', false, 'Unsupported write_mode', { field: 'write_mode' });
}

function backendBuildAck_(request, status, rowsWritten, message) {
  return backendBuildAckPayload_({
    ok: true,
    status,
    rows_received: request.chunkRows,
    rows_written: rowsWritten,
    retryable: false,
    message,
  });
}

function backendBuildAckPayload_(payload) {
  return { ...payload };
}

function backendBuildFailurePayload_(error) {
  const backendError = error?.backendError
    ? error
    : backendCreateError_(
        'INTERNAL_ERROR',
        true,
        `Unexpected server error: ${error?.message || 'Unknown error'}`,
        { internal_message: error?.message || 'Unknown error' }
      );

  return backendBuildAckPayload_({
    ok: false,
    error_code: backendError.errorCode || 'INTERNAL_ERROR',
    retryable: backendError.retryable === true,
    message: backendError.message,
    details: backendError.details || {},
  });
}

function backendGetScriptProperties_() {
  return PropertiesService.getScriptProperties();
}

function backendWithScriptLock_(callback) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(BACKEND_V2_CONFIG.defaultLockTimeoutMs)) {
    throw backendCreateError_('LOCK_UNAVAILABLE', true, 'Could not acquire script lock', {});
  }

  try {
    return callback();
  } finally {
    lock.releaseLock();
  }
}

function backendIsPlainObject_(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function backendTrimString_(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function backendCloneArray_(value) {
  return Array.isArray(value) ? value.slice(0) : [];
}

function backendNormalizeForStableStringify_(value) {
  if (value === null || value === undefined) {
    return value;
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (Array.isArray(value)) {
    return value.map((item) => backendNormalizeForStableStringify_(item));
  }

  if (backendIsPlainObject_(value)) {
    return Object.keys(value)
      .sort()
      .reduce((normalized, key) => {
        normalized[key] = backendNormalizeForStableStringify_(value[key]);
        return normalized;
      }, {});
  }

  return value;
}

function backendStableStringify_(value) {
  return JSON.stringify(backendNormalizeForStableStringify_(value));
}

function backendSha256Hex_(value) {
  const bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    String(value),
    Utilities.Charset.UTF_8
  );

  return bytes
    .map((byteValue) => {
      const normalized = byteValue < 0 ? byteValue + 256 : byteValue;
      return normalized.toString(16).padStart(2, '0');
    })
    .join('');
}

function backendCreateError_(errorCode, retryable, message, details) {
  const error = new Error(message);
  error.backendError = true;
  error.errorCode = errorCode;
  error.retryable = retryable === true;
  error.details = details || {};
  return error;
}

function backendMakeJsonResponse_(payload) {
  const response = backendIsPlainObject_(payload) ? { ...payload } : { value: payload };
  if (!Object.prototype.hasOwnProperty.call(response, 'api_version')) {
    response.api_version = BACKEND_V2_CONFIG.apiVersion;
  }

  return ContentService
    .createTextOutput(JSON.stringify(response))
    .setMimeType(ContentService.MimeType.JSON);
}

function backendToInteger_(value) {
  if (typeof value === 'number' && isFinite(value) && Math.floor(value) === value) {
    return value;
  }

  if (typeof value === 'string' && /^\s*-?\d+\s*$/.test(value)) {
    return parseInt(value, 10);
  }

  return null;
}

function backendSequenceEquals_(left, right) {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((value, index) => value === right[index]);
}

function backendTrimTrailingBlankCells_(row) {
  let end = row.length;
  while (end > 0 && (row[end - 1] === '' || row[end - 1] === null || row[end - 1] === undefined)) {
    end -= 1;
  }
  return row.slice(0, end);
}

function backendTrimTrailingBlankRows_(rows) {
  let end = rows.length;
  while (end > 0) {
    const row = rows[end - 1];
    const hasValue = row.some((value) => value !== '' && value !== null && value !== undefined);
    if (hasValue) {
      break;
    }
    end -= 1;
  }
  return rows.slice(0, end);
}

function backendCoerceCellValue_(value) {
  if (value === null || value === undefined) {
    return '';
  }

  if (value instanceof Date) {
    return backendEscapeFormulaValue_(value.toISOString());
  }

  if (typeof value === 'string') {
    return backendEscapeFormulaValue_(value);
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }

  return backendEscapeFormulaValue_(backendStableStringify_(value));
}

function backendEscapeFormulaValue_(value) {
  if (typeof value !== 'string' || !value.length) {
    return value;
  }

  const first = value.charAt(0);
  if (['=', '+', '-', '@', '\t', '\r', '\n'].includes(first)) {
    return `'${value}`;
  }

  return value;
}

function backendComputeRequestChecksum_(request) {
  return backendSha256Hex_(backendStableStringify_({
    protocol_version: request.protocolVersion,
    job_name: request.jobName,
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    total_chunks: request.totalChunks,
    total_rows: request.totalRows,
    chunk_rows: request.chunkRows,
    sheet_name: request.sheetName,
    export_date: request.exportDate,
    source_id: request.sourceId,
    write_mode: request.writeMode,
    columns: request.columns,
    records: request.records,
  }));
}

function backendMeasureUtf8Bytes_(value) {
  if (typeof Utilities !== 'undefined' && Utilities && typeof Utilities.newBlob === 'function') {
    return Utilities.newBlob(String(value)).getBytes().length;
  }
  return unescape(encodeURIComponent(String(value))).length;
}
