var BACKEND_V2_CONFIG = Object.freeze({
  apiVersion: '2.0',
  protocolVersion: 'gas-sheet.v2',
  runStatePrefix: 'gasv2:run:',
  technicalDateColumnName: '__\u0414\u0430\u0442\u0430\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0438',
  technicalSourceColumnName: '__idb_source',
  legacySourceMarker: 'iDentBridge:gas-sheet:v2',
  stagingSheetPrefix: '__stage__',
  pingMessage: 'pong',
  defaultLockTimeoutMs: 2000,
  maxPayloadBytes: 5 * 1024 * 1024,
  maxSheetNameLength: 100,
  staleRunTtlMs: 12 * 60 * 60 * 1000,
});

function backendHandleRequest_(event, method, context) {
  void context;
  try {
    var normalizedMethod = backendTrimString_(method).toUpperCase();

    if (normalizedMethod === 'GET') {
      return backendHandleGetRequest_(event);
    }

    if (normalizedMethod === 'POST') {
      return backendHandlePostRequest_(event, context);
    }

    throw backendCreateError_(
      'INVALID_REQUEST_METHOD',
      false,
      'Unsupported request method: ' + (normalizedMethod || '<empty>'),
      { method: normalizedMethod || '' }
    );
  } catch (error) {
    return backendMakeJsonResponse_(backendBuildFailurePayload_(null, error));
  }
}

function backendHandleGetRequest_(event) {
  var action = backendTrimString_(event && event.parameter ? event.parameter.action : '').toLowerCase();
  backendCollectStaleRuns_(backendGetSpreadsheet_());

  if (action === 'ping') {
    return backendMakeJsonResponse_({
      ok: true,
      status: 'ready',
      action: 'ping',
      message: BACKEND_V2_CONFIG.pingMessage,
    });
  }

  if (action === 'sheets') {
    return backendMakeJsonResponse_({
      ok: true,
      status: 'ready',
      action: 'sheets',
      sheets: backendListVisibleSheetNames_(),
    });
  }

  return backendMakeJsonResponse_(backendBuildFailurePayload_(null, backendCreateError_(
    'INVALID_ACTION',
    false,
    'Unsupported GET action',
    { action: action }
  )));
}


function backendHandlePostRequest_(event, context) {
  void context;
  return backendWithScriptLock_(function handleLockedPost() {
    var request = backendParseV2Request_(event);
    var spreadsheet = backendGetSpreadsheet_();
    backendCollectStaleRuns_(spreadsheet);
    var mainSheet = backendEnsureMainSheet_(spreadsheet, request);

    if (request.totalChunks === 1) {
      backendRewriteMainSheet_(mainSheet, request, backendBuildMainRows_(request));
      return backendMakeJsonResponse_(
        backendBuildAck_(request, 'promoted', request.chunkRows, 'Chunk promoted')
      );
    }

    var state = backendLoadRunState_(request.runId);
    if (state && state.completed) {
      return backendMakeJsonResponse_(
        backendBuildAck_(request, 'promoted', 0, 'Run already promoted')
      );
    }

    if (!state) {
      state = backendCreateRunState_(request, backendBuildStagingSheetName_(request.sheetName, request.runId));
    } else {
      backendValidateExistingRunState_(state, request);
    }

    state.updated_at = backendNowIso_();
    backendSaveRunState_(state);

    var stagingSheet = backendEnsureStagingSheet_(spreadsheet, request, state.staging_sheet_name);
    var stagingResult = backendReplaceStagingChunkRows_(stagingSheet, request);
    state.updated_at = backendNowIso_();
    backendSaveRunState_(state);

    if (!backendHasAllChunks_(stagingSheet, request.totalChunks)) {
      return backendMakeJsonResponse_(
        backendBuildAck_(
          request,
          stagingResult.duplicate ? 'duplicate' : 'staged',
          stagingResult.duplicate ? 0 : request.chunkRows,
          stagingResult.duplicate ? 'Chunk already staged' : 'Chunk staged'
        )
      );
    }

    backendRewriteMainSheet_(mainSheet, request, backendBuildPromotedRows_(stagingSheet));
    backendDeleteStagingSheet_(spreadsheet, stagingSheet);
    state.completed = true;
    state.updated_at = backendNowIso_();
    backendSaveRunState_(state);

    return backendMakeJsonResponse_(
      backendBuildAck_(
        request,
        'promoted',
        stagingResult.duplicate ? 0 : request.chunkRows,
        stagingResult.duplicate ? 'Run promoted from existing staging data' : 'Chunk promoted'
      )
    );
  });
}

function backendParseV2Request_(event) {
  var raw = event && event.postData && typeof event.postData.contents === 'string'
    ? event.postData.contents
    : '';

  if (!raw) {
    throw backendCreateError_(
      'MALFORMED_JSON',
      false,
      'POST body must contain JSON',
      { field: 'body' }
    );
  }

  if (backendMeasureUtf8Bytes_(raw) > BACKEND_V2_CONFIG.maxPayloadBytes) {
    throw backendCreateError_(
      'PAYLOAD_TOO_LARGE',
      false,
      'POST body exceeds configured payload limit',
      { max_payload_bytes: BACKEND_V2_CONFIG.maxPayloadBytes }
    );
  }

  var payload;
  try {
    payload = JSON.parse(raw);
  } catch (_error) {
    throw backendCreateError_(
      'MALFORMED_JSON',
      false,
      'POST body is not valid JSON',
      { field: 'body' }
    );
  }

  return backendNormalizeV2Payload_(payload);
}

function backendNormalizeRequiredString_(value, fieldName) {
  var normalized = backendTrimString_(value);
  if (!normalized) {
    throw backendCreateError_(
      'INVALID_PAYLOAD',
      false,
      'Missing ' + fieldName,
      { field: fieldName }
    );
  }
  return normalized;
}

function backendNormalizeRequiredInteger_(value, fieldName) {
  var normalized = backendToInteger_(value);
  if (normalized === null) {
    throw backendCreateError_(
      'INVALID_PAYLOAD',
      false,
      'Invalid ' + fieldName,
      { field: fieldName }
    );
  }
  return normalized;
}

function backendNormalizeColumns_(value) {
  if (!Array.isArray(value) || !value.length) {
    throw backendCreateError_(
      'INVALID_PAYLOAD',
      false,
      'columns must be a non-empty array',
      { field: 'columns' }
    );
  }

  var columns = [];
  var seen = Object.create(null);

  for (var index = 0; index < value.length; index += 1) {
    var columnName = backendTrimString_(value[index]);
    if (!columnName) {
      throw backendCreateError_(
        'INVALID_PAYLOAD',
        false,
        'columns may not contain empty values',
        { field: 'columns' }
      );
    }

    if (seen[columnName]) {
      throw backendCreateError_(
        'INVALID_PAYLOAD',
        false,
        'columns must be unique',
        { field: 'columns' }
      );
    }

    seen[columnName] = true;
    columns.push(columnName);
  }

  return columns;
}

function backendNormalizeRecords_(value) {
  if (!Array.isArray(value)) {
    throw backendCreateError_(
      'INVALID_RECORDS_SHAPE',
      false,
      'records must be an array',
      { field: 'records' }
    );
  }

  var records = [];
  for (var index = 0; index < value.length; index += 1) {
    if (!backendIsPlainObject_(value[index])) {
      throw backendCreateError_(
        'INVALID_RECORDS_SHAPE',
        false,
        'records must contain objects',
        { field: 'records' }
      );
    }

    records.push(Object.assign({}, value[index]));
  }

  return records;
}

function backendNormalizeWriteMode_(value) {
  var normalized = backendTrimString_(value);
  if (
    normalized === 'append' ||
    normalized === 'replace_all' ||
    normalized === 'replace_by_date_source'
  ) {
    return normalized;
  }

  throw backendCreateError_(
    'INVALID_PAYLOAD',
    false,
    'Unsupported write_mode',
    { field: 'write_mode' }
  );
}

function backendNormalizeV2Payload_(payload) {
  if (!backendIsPlainObject_(payload)) {
    throw backendCreateError_(
      'INVALID_PAYLOAD',
      false,
      'Request body must be a JSON object',
      { field: 'body' }
    );
  }

  var protocolVersion = backendNormalizeRequiredString_(payload.protocol_version, 'protocol_version');
  if (protocolVersion !== BACKEND_V2_CONFIG.protocolVersion) {
    throw backendCreateError_(
      'INVALID_PROTOCOL_VERSION',
      false,
      'Unsupported protocol version',
      { protocol_version: protocolVersion }
    );
  }

  var jobName = backendNormalizeRequiredString_(payload.job_name, 'job_name');
  var runId = backendNormalizeRequiredString_(payload.run_id, 'run_id');
  var chunkIndex = backendNormalizeRequiredInteger_(payload.chunk_index, 'chunk_index');
  var totalChunks = backendNormalizeRequiredInteger_(payload.total_chunks, 'total_chunks');
  var totalRows = backendNormalizeRequiredInteger_(payload.total_rows, 'total_rows');
  var chunkRows = backendNormalizeRequiredInteger_(payload.chunk_rows, 'chunk_rows');
  var sheetName = backendNormalizeRequiredString_(payload.sheet_name, 'sheet_name');
  var exportDate = backendNormalizeRequiredString_(payload.export_date, 'export_date');
  var sourceId = backendNormalizeRequiredString_(payload.source_id, 'source_id');
  var writeMode = backendNormalizeWriteMode_(payload.write_mode);
  var checksum = backendNormalizeRequiredString_(payload.checksum, 'checksum');
  var columns = backendNormalizeColumns_(payload.columns);
  var records = backendNormalizeRecords_(payload.records);

  if (totalChunks < 1) {
    throw backendCreateError_(
      'INVALID_PAYLOAD',
      false,
      'total_chunks must be at least 1',
      { field: 'total_chunks' }
    );
  }

  if (chunkIndex < 1 || chunkIndex > totalChunks) {
    throw backendCreateError_(
      'INVALID_PAYLOAD',
      false,
      'chunk_index must be within total_chunks',
      {
        field: 'chunk_index',
        total_chunks: totalChunks,
      }
    );
  }

  if (chunkRows !== records.length) {
    throw backendCreateError_(
      'INVALID_RECORDS_SHAPE',
      false,
      'chunk_rows must match the number of records',
      {
        field: 'chunk_rows',
        chunk_rows: chunkRows,
        records: records.length,
      }
    );
  }

  var request = {
    protocolVersion: protocolVersion,
    jobName: jobName,
    runId: runId,
    chunkIndex: chunkIndex,
    totalChunks: totalChunks,
    totalRows: totalRows,
    chunkRows: chunkRows,
    sheetName: sheetName,
    exportDate: exportDate,
    sourceId: sourceId,
    writeMode: writeMode,
    columns: columns,
    records: records,
    checksum: checksum,
  };

  var expectedChecksum = backendComputeRequestChecksum_(request);
  if (expectedChecksum !== checksum) {
    throw backendCreateError_(
      'CHECKSUM_MISMATCH',
      false,
      'Checksum mismatch',
      {
        expected_checksum: expectedChecksum,
      }
    );
  }

  return request;
}

function backendValidateExistingRunState_(state, request) {
  if (!state || !backendIsPlainObject_(state)) {
    throw backendCreateError_(
      'INVALID_RUN_STATE',
      false,
      'Run state is not available',
      {}
    );
  }

  if (
    backendTrimString_(state.protocol_version) !== request.protocolVersion ||
    backendTrimString_(state.job_name) !== request.jobName ||
    backendTrimString_(state.run_id) !== request.runId ||
    backendTrimString_(state.sheet_name) !== request.sheetName ||
    backendTrimString_(state.export_date) !== request.exportDate ||
    backendTrimString_(state.source_id) !== request.sourceId ||
    backendTrimString_(state.write_mode) !== request.writeMode ||
    state.total_chunks !== request.totalChunks ||
    state.total_rows !== request.totalRows
  ) {
    throw backendCreateError_(
      'INVALID_RUN_STATE',
      false,
      'Run state does not match this request',
      {}
    );
  }
}

function backendBuildAck_(request, status, rowsWritten, message) {
  return {
    ok: true,
    status: status,
    rows_received: request.chunkRows,
    rows_written: rowsWritten,
    retryable: false,
    message: message,
  };
}

function backendBuildFailurePayload_(request, error) {
  void request;
  var backendError = error && error.backendError
    ? error
    : backendCreateError_(
        'INTERNAL_ERROR',
        true,
        'Unexpected server error: ' + (error && error.message ? error.message : 'Unknown error'),
        {
          internal_message: error && error.message ? error.message : 'Unknown error',
        }
      );

  return {
    ok: false,
    error_code: backendError.errorCode || 'INTERNAL_ERROR',
    retryable: backendError.retryable === true,
    message: backendError.message,
    details: backendError.details || {},
  };
}

function backendBuildStagingSheetName_(sheetName, runId) {
  var safeSheetName = backendSanitizeSheetName_(sheetName);
  var safeRunId = backendSanitizeSheetName_(runId);
  var runSuffix = safeRunId.length > 12 ? safeRunId.substring(safeRunId.length - 12) : safeRunId;
  var base = BACKEND_V2_CONFIG.stagingSheetPrefix + safeSheetName + '__' + runSuffix;

  if (base.length <= BACKEND_V2_CONFIG.maxSheetNameLength) {
    return base;
  }

  var hash = backendSha256Hex_(sheetName + '\n' + runId).substring(0, 8);
  var prefixLength = BACKEND_V2_CONFIG.maxSheetNameLength - hash.length - 3;
  return base.substring(0, Math.max(prefixLength, 1)) + '__' + hash;
}
