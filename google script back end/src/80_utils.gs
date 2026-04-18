function isPlainObject_(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function trimString_(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeColumnName_(value) {
  if (value === null || value === undefined) {
    return '';
  }

  return String(value).trim();
}

function toIntegerOrNull_(value) {
  if (typeof value === 'number' && isFinite(value) && Math.floor(value) === value) {
    return value;
  }

  if (typeof value === 'string' && /^\s*-?\d+\s*$/.test(value)) {
    return parseInt(value, 10);
  }

  return null;
}

function sameSequence_(left, right) {
  if (left.length !== right.length) {
    return false;
  }

  for (var i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) {
      return false;
    }
  }

  return true;
}

function toLookupSet_(values) {
  var set = Object.create(null);
  for (var i = 0; i < values.length; i += 1) {
    set[values[i]] = true;
  }
  return set;
}

function difference_(values, lookupSet) {
  var output = [];
  for (var i = 0; i < values.length; i += 1) {
    if (!lookupSet[values[i]]) {
      output.push(values[i]);
    }
  }
  return output;
}

function cloneObject_(value) {
  return JSON.parse(JSON.stringify(value));
}

function cloneArray_(value) {
  return Array.isArray(value) ? value.slice(0) : [];
}

function parseJsonOrDefault_(value, defaultValue) {
  if (value === null || value === undefined || value === '') {
    return defaultValue;
  }

  try {
    return JSON.parse(value);
  } catch (error) {
    return defaultValue;
  }
}

function trimTrailingBlankCells_(row) {
  var end = row.length;
  while (end > 0 && (row[end - 1] === '' || row[end - 1] === null || row[end - 1] === undefined)) {
    end -= 1;
  }
  return row.slice(0, end);
}

function escapeFormulaValue_(value) {
  if (typeof value !== 'string' || !value.length) {
    return value;
  }

  var first = value.charAt(0);
  if (first === '=' || first === '+' || first === '-' || first === '@' || first === '\t' || first === '\r' || first === '\n') {
    return "'" + value;
  }

  return value;
}

function trimToLength_(value, maxLength) {
  if (typeof value !== 'string' || value.length <= maxLength) {
    return value;
  }

  return value.substring(0, maxLength) + '...';
}

function stableStringify_(value) {
  return JSON.stringify(normalizeForStableStringify_(value));
}

function normalizeForStableStringify_(value) {
  if (value === null || value === undefined) {
    return value;
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (Array.isArray(value)) {
    var arrayValue = [];
    for (var i = 0; i < value.length; i += 1) {
      arrayValue.push(normalizeForStableStringify_(value[i]));
    }
    return arrayValue;
  }

  if (isPlainObject_(value)) {
    var keys = Object.keys(value).sort();
    var objectValue = {};
    for (var j = 0; j < keys.length; j += 1) {
      objectValue[keys[j]] = normalizeForStableStringify_(value[keys[j]]);
    }
    return objectValue;
  }

  return value;
}

function sha256Hex_(value) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    String(value),
    Utilities.Charset.UTF_8
  );

  var hex = [];
  for (var i = 0; i < bytes.length; i += 1) {
    var byteValue = bytes[i];
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
