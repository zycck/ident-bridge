function logRequestStart_(request) {
  logInfo_('chunk_received', {
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    total_chunks: request.totalChunks,
    chunk_rows: request.chunkRows,
    chunk_bytes: request.chunkBytes,
    schema_mode: request.schema.mode,
    column_count: request.schema.columns.length
  });
}

function logInfo_(eventName, context) {
  writeStructuredLog_('INFO', eventName, context);
}

function logWarn_(eventName, context) {
  writeStructuredLog_('WARN', eventName, context);
}

function logError_(eventName, context) {
  writeStructuredLog_('ERROR', eventName, context);
}

function writeStructuredLog_(level, eventName, context) {
  var entry = {
    level: level,
    event: eventName,
    time: nowIso_(),
    context: sanitizeLogContext_(context || {})
  };

  Logger.log(JSON.stringify(entry));
}

function sanitizeLogContext_(context) {
  var output = {};
  var keys = Object.keys(context || {});

  for (var i = 0; i < keys.length; i += 1) {
    var key = keys[i];
    if (shouldRedactLogKey_(key)) {
      continue;
    }

    output[key] = sanitizeLogValue_(context[key]);
  }

  return output;
}

function shouldRedactLogKey_(key) {
  var lowered = String(key || '').toLowerCase();
  return lowered.indexOf('payload') !== -1 ||
    lowered.indexOf('records') !== -1 ||
    lowered.indexOf('body') !== -1 ||
    lowered.indexOf('token') !== -1 ||
    lowered.indexOf('secret') !== -1 ||
    lowered.indexOf('url') !== -1 ||
    lowered.indexOf('authorization') !== -1;
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
    return '[array:' + value.length + ']';
  }

  if (isPlainObject_(value)) {
    return '[object:' + Object.keys(value).length + ']';
  }

  return '[value]';
}

function looksSensitiveString_(value) {
  var lower = String(value).toLowerCase();
  return lower.indexOf('http://') === 0 ||
    lower.indexOf('https://') === 0 ||
    lower.indexOf('bearer ') === 0 ||
    lower.indexOf('token') !== -1 ||
    lower.indexOf('secret') !== -1 ||
    lower.indexOf('password') !== -1;
}

