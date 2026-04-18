function doGet(event) {
  return makeJsonResponse_({
    ok: true,
    status: 'ready',
    message: 'Google Apps Script webhook backend is ready',
    protocol_version: CONFIG.protocolVersion,
    data_sheet: CONFIG.dataSheetName,
    ledger_sheet: CONFIG.ledgerSheetName,
  });
}

function doPost(event) {
  const store = getSheetsStore_();
  let request = null;
  let lease = null;
  let context = null;

  try {
    request = parseWebhookRequest_(event);
    logRequestStart_(request);

    const startState = store.beginRequest(request);
    if (startState.state === 'completed') {
      const duplicateAck = buildDuplicateSuccessAck_(request, startState.record);
      logSuccess_(duplicateAck);
      return makeJsonResponse_(duplicateAck);
    }

    lease = startState.lease;
    context = store.loadRequestContext();

    const schemaTransition = analyzeSchemaTransition_(context.existingHeaders, request.schema.columns);
    if (!schemaTransition.allowed) {
      throw createWebhookError_(
        'SCHEMA_MISMATCH_RENAME_OR_REMOVE',
        false,
        schemaTransition.message,
        schemaTransition.details
      );
    }

    const successAck = buildSuccessAck_(
      request,
      request.records.length,
      schemaTransition.schemaAction,
      schemaTransition.addedColumns
    );

    store.writeChunk({
      context,
      headers: schemaTransition.targetHeaders,
      records: request.records,
      ledgerEntry: buildLedgerEntry_(request, successAck, 'completed'),
    });

    store.finalizeSuccess(request, successAck, lease);
    lease = null;

    logSuccess_(successAck);
    return makeJsonResponse_(successAck);
  } catch (error) {
    const failureAck = buildFailureAck_(request, error);

    if (lease) {
      store.releaseLease(lease);
      lease = null;
    }

    if (request && request.runId !== undefined) {
      try {
        context = context || store.loadRequestContext();
        store.writeChunk({
          context,
          headers: context.existingHeaders,
          records: [],
          ledgerEntry: buildLedgerEntry_(request, failureAck, 'failed'),
        });
      } catch (auditError) {
        logWarn_('ledger_write_failed', {
          run_id: request.runId,
          chunk_index: request.chunkIndex,
          message: auditError && auditError.message ? auditError.message : 'Unexpected ledger write failure',
        });
      }
    }

    logFailure_(failureAck);
    return makeJsonResponse_(failureAck);
  }
}

