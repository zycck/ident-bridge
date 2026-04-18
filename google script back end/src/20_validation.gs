function normalizeWebhookRequest_(payload) {
  if (!isPlainObject_(payload)) {
    throw createWebhookError_('INVALID_PAYLOAD', false, 'Request body must be a JSON object', {
      field: 'body'
    });
  }

  var protocolVersion = normalizeRequiredString_(payload.protocol_version, 'protocol_version');
  if (protocolVersion !== CONFIG.protocolVersion) {
    throw createWebhookError_('INVALID_PROTOCOL_VERSION', false, 'Unsupported protocol version', {
      protocol_version: protocolVersion
    });
  }

  var jobName = normalizeRequiredString_(payload.job_name, 'job_name');
  var runId = normalizeRequiredString_(payload.run_id, 'run_id');
  var chunkIndex = normalizeRequiredInteger_(payload.chunk_index, 'chunk_index');
  var totalChunks = normalizeRequiredInteger_(payload.total_chunks, 'total_chunks');
  var totalRows = normalizeRequiredInteger_(payload.total_rows, 'total_rows');
  var chunkRows = normalizeRequiredInteger_(payload.chunk_rows, 'chunk_rows');
  var chunkBytes = normalizeRequiredInteger_(payload.chunk_bytes, 'chunk_bytes');

  if (totalChunks < 1) {
    throw createWebhookError_('INVALID_PAYLOAD', false, 'total_chunks must be at least 1', {
      field: 'total_chunks'
    });
  }

  if (chunkIndex < 1 || chunkIndex > totalChunks) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'chunk_index must be within total_chunks using 1-based indexing', {
      field: 'chunk_index'
    });
  }

  if (totalRows < 0 || chunkRows < 0 || chunkBytes < 0) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'Row and byte counts must be non-negative', {
      field: 'counts'
    });
  }

  if (chunkRows > totalRows && totalRows !== 0) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'chunk_rows cannot exceed total_rows', {
      field: 'chunk_rows'
    });
  }

  var schema = normalizeSchemaBlock_(payload.schema);
  var records = normalizeRecordList_(payload.records, schema.columns.length);

  if (records.length !== chunkRows) {
    throw createWebhookError_('INVALID_PAYLOAD', false, 'chunk_rows must match records length', {
      field: 'chunk_rows'
    });
  }

  return {
    protocolVersion: protocolVersion,
    jobName: jobName,
    runId: runId,
    chunkIndex: chunkIndex,
    totalChunks: totalChunks,
    totalRows: totalRows,
    chunkRows: chunkRows,
    chunkBytes: chunkBytes,
    schema: schema,
    records: records
  };
}

function normalizeSchemaBlock_(schema) {
  if (!isPlainObject_(schema)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'schema must be a JSON object', {
      field: 'schema'
    });
  }

  var mode = normalizeRequiredString_(schema.mode, 'schema.mode').toLowerCase();
  if (mode !== CONFIG.schemaMode) {
    throw createWebhookError_('INVALID_PROTOCOL_VERSION', false, 'Unsupported schema mode', {
      field: 'schema.mode',
      schema_mode: mode
    });
  }
  var columns = normalizeColumnList_(schema.columns);
  var checksum = normalizeRequiredString_(schema.checksum, 'schema.checksum');

  if (columns.length > CONFIG.maxColumns) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'Too many schema columns', {
      field: 'schema.columns'
    });
  }

  return {
    mode: mode,
    columns: columns,
    checksum: checksum
  };
}

function normalizeColumnList_(columns) {
  if (!Array.isArray(columns)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'schema.columns must be an array', {
      field: 'schema.columns'
    });
  }

  var normalized = [];
  var seen = Object.create(null);

  for (var i = 0; i < columns.length; i += 1) {
    var name = normalizeColumnName_(columns[i]);
    if (!name) {
      throw createWebhookError_('SCHEMA_EMPTY_COLUMN_NAME', false, 'Empty schema columns are blocked', {
        field: 'schema.columns'
      });
    }

    if (seen[name]) {
      throw createWebhookError_('SCHEMA_DUPLICATE_COLUMNS', false, 'Duplicate schema columns are blocked', {
        field: 'schema.columns'
      });
    }

    seen[name] = true;
    normalized.push(name);
  }

  return normalized;
}

function normalizeRecordList_(records, expectedWidth) {
  if (!Array.isArray(records)) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'records must be an array', {
      field: 'records'
    });
  }

  if (records.length > CONFIG.maxRecordsPerChunk) {
    throw createWebhookError_('PAYLOAD_TOO_LARGE', false, 'Too many records in a chunk', {
      field: 'records'
    });
  }

  var normalized = [];

  for (var i = 0; i < records.length; i += 1) {
    if (!isPlainObject_(records[i])) {
      throw createWebhookError_('INVALID_RECORDS_SHAPE', false, 'Each record must be a JSON object', {
        field: 'records'
      });
    }

    normalized.push(cloneObject_(records[i]));
  }

  return normalized;
}

function normalizeRequiredString_(value, fieldName) {
  var text = trimString_(value);
  if (!text) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, fieldName + ' is required', {
      field: fieldName
    });
  }

  return text;
}

function normalizeRequiredInteger_(value, fieldName) {
  var integerValue = toIntegerOrNull_(value);
  if (integerValue === null) {
    throw createWebhookError_('INVALID_RECORDS_SHAPE', false, fieldName + ' must be an integer', {
      field: fieldName
    });
  }

  return integerValue;
}
