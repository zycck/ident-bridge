function buildBackendV2_() {
  return {
    handleRequest: backendHandleRequest_,
  };
}

function backendHandleRequest_(event, method, context) {
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
    var sheetNames = backendListVisibleSheetNames_();
    return backendMakeJsonResponse_({
      ok: true,
      status: 'ready',
      action: 'sheets',
      sheets: sheetNames,
      sheet_names: sheetNames,
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
  return backendWithScriptLock_(function handleLockedPost() {
    var request = backendParseV2Request_(event, context);
    var spreadsheet = backendGetSpreadsheet_();
    backendCollectStaleRuns_(spreadsheet);
    var state = backendLoadRunState_(request.runId);

    if (state && state.promoted) {
      return backendMakeJsonResponse_(backendBuildPromotedAck_(request, 0, 'Run already promoted'));
    }

    if (!state) {
      state = backendCreateInitialRunState_(request, backendBuildStagingSheetName_(request.sheetName, request.runId));
    } else {
      backendValidateExistingRunState_(state, request);
      state.updated_at = backendNowIso_();
    }

    var mainSheet = backendEnsureMainSheet_(spreadsheet, request);
    var stagingSheetName = state.staging_sheet_name || backendBuildStagingSheetName_(request.sheetName, request.runId);
    state.staging_sheet_name = stagingSheetName;
    var stagingSheet = backendEnsureStagingSheet_(spreadsheet, request, stagingSheetName);

    var stagingResult = backendReplaceStagingChunkRows_(stagingSheet, request);
    state.updated_at = backendNowIso_();
    backendSaveRunState_(state);

    var stagedChunkSet = backendReadStageChunkIndexSet_(stagingSheet);
    var complete = Object.keys(stagedChunkSet).length === request.totalChunks;

    if (complete) {
      var promotedRows = backendBuildPromotedRows_(request, stagingSheet);
      backendRewriteMainSheet_(mainSheet, request, promotedRows);
      state.promoted = true;
      state.promoted_at = backendNowIso_();
      state.promoted_rows = promotedRows.length;
      state.updated_at = backendNowIso_();
      backendSaveRunState_(state);
      backendCleanupStagingSheet_(stagingSheet);

      return backendMakeJsonResponse_(backendBuildPromotedAck_(
        request,
        stagingResult.duplicate ? 0 : request.records.length,
        stagingResult.duplicate ? 'Run promoted from existing staging data' : 'Chunk promoted'
      ));
    }

    return backendMakeJsonResponse_(backendBuildChunkAck_(
      request,
      stagingResult.duplicate ? 'duplicate' : 'staged',
      stagingResult.duplicate ? 0 : request.records.length,
      stagingResult.duplicate ? 'Chunk already staged' : 'Chunk staged'
    ));
  });
}

function backendParseV2Request_(event, context) {
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
    state.total_chunks !== request.totalChunks ||
    state.total_rows !== request.totalRows ||
    !backendSequenceEquals_(backendCloneArray_(state.columns), request.columns)
  ) {
    throw backendCreateError_(
      'INVALID_RUN_STATE',
      false,
      'Run state does not match this request',
      {}
    );
  }
}

function backendBuildChunkAck_(request, status, rowsWritten, message) {
  return {
    ok: true,
    status: status,
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    total_chunks: request.totalChunks,
    total_rows: request.totalRows,
    rows_received: request.chunkRows,
    rows_written: rowsWritten,
    sheet_name: request.sheetName,
    export_date: request.exportDate,
    retryable: false,
    message: message,
  };
}

function backendBuildPromotedAck_(request, rowsWritten, message) {
  var ack = backendBuildChunkAck_(request, 'promoted', rowsWritten, message);
  ack.promoted = true;
  return ack;
}

function backendBuildFailurePayload_(request, error) {
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
    run_id: request && request.runId ? request.runId : undefined,
    chunk_index: request && request.chunkIndex ? request.chunkIndex : undefined,
    message: backendError.message,
    details: backendError.details || {},
  };
}

function backendBuildStagingSheetName_(sheetName, runId) {
  var base = BACKEND_V2_CONFIG.stagingSheetPrefix
    + backendSanitizeSheetName_(sheetName)
    + '__'
    + backendSanitizeSheetName_(runId);

  if (base.length <= BACKEND_V2_CONFIG.maxSheetNameLength) {
    return base;
  }

  var hash = backendSha256Hex_(sheetName + '\n' + runId).substring(0, 8);
  var prefixLength = BACKEND_V2_CONFIG.maxSheetNameLength - hash.length - 3;
  return base.substring(0, Math.max(prefixLength, 1)) + '__' + hash;
}
