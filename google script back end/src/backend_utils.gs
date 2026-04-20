function backendIsPlainObject_(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function backendTrimString_(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function backendCloneArray_(value) {
  return Array.isArray(value) ? value.slice(0) : [];
}

function backendNowIso_() {
  return new Date().toISOString();
}

function backendNormalizeForStableStringify_(value) {
  if (value === null || value === undefined) {
    return value;
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (Array.isArray(value)) {
    return value.map(function normalizeArrayItem(item) {
      return backendNormalizeForStableStringify_(item);
    });
  }

  if (backendIsPlainObject_(value)) {
    var normalized = {};
    var keys = Object.keys(value).sort();

    for (var index = 0; index < keys.length; index += 1) {
      var key = keys[index];
      normalized[key] = backendNormalizeForStableStringify_(value[key]);
    }

    return normalized;
  }

  return value;
}

function backendStableStringify_(value) {
  return JSON.stringify(backendNormalizeForStableStringify_(value));
}

function backendSha256Hex_(value) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    String(value),
    Utilities.Charset.UTF_8
  );
  var hex = [];

  for (var index = 0; index < bytes.length; index += 1) {
    var byteValue = bytes[index];
    if (byteValue < 0) {
      byteValue += 256;
    }

    var text = byteValue.toString(16);
    if (text.length === 1) {
      text = '0' + text;
    }

    hex.push(text);
  }

  return hex.join('');
}

function backendCreateError_(errorCode, retryable, message, details) {
  var error = new Error(message);
  error.backendError = true;
  error.errorCode = errorCode;
  error.retryable = retryable === true;
  error.details = details || {};
  return error;
}

function backendMakeJsonResponse_(payload) {
  var response = backendIsPlainObject_(payload)
    ? Object.assign({}, payload)
    : { value: payload };

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

  for (var index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) {
      return false;
    }
  }

  return true;
}

function backendTrimTrailingBlankCells_(row) {
  var end = row.length;
  while (end > 0 && (row[end - 1] === '' || row[end - 1] === null || row[end - 1] === undefined)) {
    end -= 1;
  }
  return row.slice(0, end);
}

function backendTrimTrailingBlankRows_(rows) {
  var end = rows.length;
  while (end > 0) {
    var row = rows[end - 1];
    var hasValue = false;
    for (var index = 0; index < row.length; index += 1) {
      if (row[index] !== '' && row[index] !== null && row[index] !== undefined) {
        hasValue = true;
        break;
      }
    }
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

  var first = value.charAt(0);
  if (
    first === '=' ||
    first === '+' ||
    first === '-' ||
    first === '@' ||
    first === '\t' ||
    first === '\r' ||
    first === '\n'
  ) {
    return "'" + value;
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
    columns: request.columns,
    records: request.records,
  }));
}

function backendSanitizeSheetName_(value) {
  var text = backendTrimString_(value).replace(/[\[\]\:\*\?\/\\]/g, '_');
  if (!text) {
    text = 'sheet';
  }
  return text;
}

function backendMeasureUtf8Bytes_(value) {
  if (typeof Utilities !== 'undefined' && Utilities && typeof Utilities.newBlob === 'function') {
    return Utilities.newBlob(String(value)).getBytes().length;
  }

  return unescape(encodeURIComponent(String(value))).length;
}
