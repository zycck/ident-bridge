function createWebhookError_(errorCode, retryable, message, details) {
  var error = new Error(message);
  error.webhookError = true;
  error.errorCode = errorCode;
  error.retryable = retryable === true;
  error.details = details || {};
  return error;
}

function buildSuccessAck_(request, rowsWritten, schemaAction, addedColumns) {
  var status = schemaAction === 'extended' ? 'schema_extended' : 'accepted';
  return {
    ok: true,
    status: status,
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    rows_received: request.chunkRows,
    rows_written: rowsWritten,
    retryable: false,
    schema_action: schemaAction,
    added_columns: cloneArray_(addedColumns),
    message: 'Chunk written successfully'
  };
}

function buildFailureAck_(request, error) {
  var safeRequest = request || {};
  if (error && error.webhookError) {
    return {
      ok: false,
      error_code: error.errorCode || 'UNKNOWN_ERROR',
      retryable: error.retryable === true,
      run_id: safeRequest.runId || '',
      chunk_index: safeRequest.chunkIndex !== undefined ? safeRequest.chunkIndex : '',
      message: error.message || 'Request failed',
      details: error.details || {}
    };
  }

  return {
    ok: false,
    error_code: 'INTERNAL_WRITE_ERROR',
    retryable: true,
    run_id: safeRequest.runId || '',
    chunk_index: safeRequest.chunkIndex !== undefined ? safeRequest.chunkIndex : '',
    message: 'Unexpected server error',
    details: {}
  };
}

function makeJsonResponse_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function logSuccess_(ack) {
  logInfo_('chunk_success', {
    run_id: ack.run_id,
    chunk_index: ack.chunk_index,
    rows_received: ack.rows_received,
    rows_written: ack.rows_written,
    status: ack.status,
    schema_action: ack.schema_action
  });
}

function logFailure_(ack) {
  logWarn_('chunk_failure', {
    run_id: ack.run_id,
    chunk_index: ack.chunk_index,
    error_code: ack.error_code,
    retryable: ack.retryable,
    status: ack.status || 'failed'
  });
}
