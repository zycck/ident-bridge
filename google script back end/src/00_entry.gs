function doGet(e) {
  return makeJsonResponse_({
    ok: true,
    status: 'ready',
    message: 'Google Apps Script webhook backend is ready',
    protocol_version: CONFIG.protocolVersion,
    data_sheet: CONFIG.dataSheetName,
    ledger_sheet: CONFIG.ledgerSheetName
  });
}

function doPost(e) {
  var request;
  var lease = null;

  try {
    request = parseWebhookRequest_(e);
    logRequestStart_(request);

    var idempotency = lookupIdempotencyState_(request);
    if (idempotency.state === 'completed') {
      var duplicateAck = buildDuplicateSuccessAck_(request, idempotency.record);
      logSuccess_(duplicateAck);
      return makeJsonResponse_(duplicateAck);
    }

    if (idempotency.state === 'processing') {
      throw createWebhookError_(
        'IDEMPOTENCY_BUSY',
        true,
        'Chunk is already being processed',
        {
          run_id: request.runId,
          chunk_index: request.chunkIndex
        }
      );
    }

    lease = acquireIdempotencyLease_(request);

    var spreadsheet = getTargetSpreadsheet_();
    var dataSheet = getOrCreateDataSheet_(spreadsheet);
    var existingHeaders = readHeaderRow_(dataSheet);
    var schemaTransition = analyzeSchemaTransition_(existingHeaders, request.schema.columns);

    if (!schemaTransition.allowed) {
      throw createWebhookError_(
        'SCHEMA_MISMATCH_RENAME_OR_REMOVE',
        false,
        schemaTransition.message,
        schemaTransition.details
      );
    }

    var headersForWrite = schemaTransition.targetHeaders;
    ensureDataHeaders_(dataSheet, headersForWrite);

    var rowsWritten = appendChunkRows_(dataSheet, headersForWrite, request.records);
    var successAck = buildSuccessAck_(request, rowsWritten, schemaTransition.schemaAction, schemaTransition.addedColumns);

    finalizeIdempotencySuccess_(request, successAck);
    releaseIdempotencyLease_(lease);
    logSuccess_(successAck);
    return makeJsonResponse_(successAck);
  } catch (error) {
    if (lease) {
      releaseIdempotencyLease_(lease);
    }

    var failureAck = buildFailureAck_(request, error);
    logFailure_(failureAck);

    if (request && request.runId !== undefined) {
      appendIdempotencyFailure_(request, failureAck);
    }

    return makeJsonResponse_(failureAck);
  }
}

function parseWebhookRequest_(e) {
  var raw = e && e.postData && typeof e.postData.contents === 'string' ? e.postData.contents : '';
  if (!raw) {
    throw createWebhookError_('MALFORMED_JSON', false, 'POST body must contain JSON', {
      field: 'body'
    });
  }

  if (Utilities.newBlob(raw).getBytes().length > CONFIG.maxChunkBytes) {
    throw createWebhookError_('PAYLOAD_TOO_LARGE', false, 'POST body exceeds configured payload limit', {
      max_chunk_bytes: CONFIG.maxChunkBytes
    });
  }

  var payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw createWebhookError_('MALFORMED_JSON', false, 'POST body is not valid JSON', {
      field: 'body'
    });
  }

  return normalizeWebhookRequest_(payload);
}
