function parseWebhookRequest_(event) {
  const raw = event && event.postData && typeof event.postData.contents === 'string'
    ? event.postData.contents
    : '';

  if (!raw) {
    throw createWebhookError_('MALFORMED_JSON', false, 'POST body must contain JSON', {
      field: 'body',
    });
  }

  if (Utilities.newBlob(raw).getBytes().length > CONFIG.maxChunkBytes) {
    throw createWebhookError_('PAYLOAD_TOO_LARGE', false, 'POST body exceeds configured payload limit', {
      max_chunk_bytes: CONFIG.maxChunkBytes,
    });
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw createWebhookError_('MALFORMED_JSON', false, 'POST body is not valid JSON', {
      field: 'body',
    });
  }

  return normalizeWebhookRequest_(payload);
}

function normalizeWebhookRequest_(payload) {
  if (!isPlainObject_(payload)) {
    throw createWebhookError_('INVALID_PAYLOAD', false, 'Request body must be a JSON object', {
      field: 'body',
    });
  }

  const protocolVersion = normalizeRequiredString_(payload.protocol_version, 'protocol_version');
  if (protocolVersion !== CONFIG.protocolVersion) {
    throw createWebhookError_('INVALID_PROTOCOL_VERSION', false, 'Unsupported protocol version', {
      protocol_version: protocolVersion,
    });
  }

  const jobName = normalizeRequiredString_(payload.job_name, 'job_name');
  const runId = normalizeRequiredString_(payload.run_id, 'run_id');
  const chunkIndex = normalizeRequiredInteger_(payload.chunk_index, 'chunk_index');
  const totalChunks = normalizeRequiredInteger_(payload.total_chunks, 'total_chunks');
  const totalRows = normalizeRequiredInteger_(payload.total_rows, 'total_rows');
  const chunkRows = normalizeRequiredInteger_(payload.chunk_rows, 'chunk_rows');
  const chunkBytes = normalizeRequiredInteger_(payload.chunk_bytes, 'chunk_bytes');

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

  const schema = normalizeSchemaBlock_(payload.schema);
  const records = normalizeRecordList_(payload.records);

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
  };
}

function normalizeSchemaBlock_(schema) {
  if (!isPlainObject_(schema)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'schema must be a JSON object', {
      field: 'schema',
    });
  }

  const mode = normalizeRequiredString_(schema.mode, 'schema.mode').toLowerCase();
  if (mode !== CONFIG.schemaMode) {
    throw createWebhookError_('INVALID_PROTOCOL_VERSION', false, 'Unsupported schema mode', {
      field: 'schema.mode',
      schema_mode: mode,
    });
  }

  const columns = normalizeColumnList_(schema.columns);
  const checksum = normalizeRequiredString_(schema.checksum, 'schema.checksum');

  if (columns.length > CONFIG.maxColumns) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'Too many schema columns', {
      field: 'schema.columns',
    });
  }

  return { mode, columns, checksum };
}

function normalizeColumnList_(columns) {
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

function normalizeRecordList_(records) {
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

function normalizeRequiredString_(value, fieldName) {
  const text = trimString_(value);
  if (!text) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, `${fieldName} is required`, {
      field: fieldName,
    });
  }

  return text;
}

function normalizeRequiredInteger_(value, fieldName) {
  const integerValue = toIntegerOrNull_(value);
  if (integerValue === null) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, `${fieldName} must be an integer`, {
      field: fieldName,
    });
  }

  return integerValue;
}

function analyzeSchemaTransition_(existingHeaders, incomingColumns) {
  const existing = normalizeIncomingHeaderList_(existingHeaders);
  const incoming = normalizeIncomingHeaderList_(incomingColumns);

  if (!existing.length) {
    return {
      allowed: true,
      schemaAction: 'extended',
      addedColumns: incoming.slice(),
      targetHeaders: incoming.slice(),
      message: 'Initial schema registered',
    };
  }

  const existingSet = toLookupSet_(existing);
  const incomingSet = toLookupSet_(incoming);
  const missingColumns = difference_(existing, incomingSet);
  const addedColumns = difference_(incoming, existingSet);

  if (missingColumns.length) {
    return blockedSchemaTransition_('Incoming columns removed or renamed existing columns', {
      missing_columns: missingColumns,
      existing_columns: existing,
      incoming_columns: incoming,
    });
  }

  if (addedColumns.length) {
    return {
      allowed: true,
      schemaAction: 'extended',
      addedColumns,
      targetHeaders: existing.concat(addedColumns),
      message: 'Columns appended to the right',
    };
  }

  return {
    allowed: true,
    schemaAction: 'unchanged',
    addedColumns: [],
    targetHeaders: existing.slice(),
    message: sameSequence_(existing, incoming)
      ? 'Schema unchanged'
      : 'Incoming columns reordered by name',
  };
}

function normalizeIncomingHeaderList_(values) {
  if (!Array.isArray(values)) {
    return [];
  }

  return values.map((value) => normalizeColumnName_(value));
}

function blockedSchemaTransition_(message, details) {
  return {
    allowed: false,
    schemaAction: 'blocked',
    addedColumns: [],
    targetHeaders: [],
    message,
    details,
  };
}

function buildSuccessAck_(request, rowsWritten, schemaAction, addedColumns) {
  return {
    ok: true,
    status: schemaAction === 'extended' ? 'schema_extended' : 'accepted',
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    rows_received: request.chunkRows,
    rows_written: rowsWritten,
    retryable: false,
    schema_action: schemaAction,
    added_columns: cloneArray_(addedColumns),
    message: 'Chunk written successfully',
  };
}

function buildDuplicateSuccessAck_(request, storedRecord) {
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

function buildFailureAck_(request, error) {
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

  return {
    ok: false,
    error_code: 'INTERNAL_WRITE_ERROR',
    retryable: true,
    run_id: safeRequest.runId || '',
    chunk_index: safeRequest.chunkIndex !== undefined ? safeRequest.chunkIndex : '',
    message: 'Unexpected server error',
    details: {},
  };
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
