function analyzeSchemaTransition_(existingHeaders, incomingColumns) {
  var existing = normalizeIncomingHeaderList_(existingHeaders);
  var incoming = normalizeIncomingHeaderList_(incomingColumns);

  if (!existing.length) {
    return {
      allowed: true,
      schemaAction: 'extended',
      addedColumns: incoming.slice(0),
      targetHeaders: incoming.slice(0),
      message: 'Initial schema registered'
    };
  }

  var existingSet = toLookupSet_(existing);
  var incomingSet = toLookupSet_(incoming);
  var missingColumns = difference_(existing, incomingSet);
  var addedColumns = difference_(incoming, existingSet);

  if (missingColumns.length) {
    return blockedSchemaTransition_(
      'Incoming columns removed or renamed existing columns',
      {
        missing_columns: missingColumns,
        existing_columns: existing,
        incoming_columns: incoming
      }
    );
  }

  if (addedColumns.length) {
    return {
      allowed: true,
      schemaAction: 'extended',
      addedColumns: addedColumns,
      targetHeaders: existing.concat(addedColumns),
      message: 'Columns appended to the right'
    };
  }

  if (sameSequence_(existing, incoming)) {
    return {
      allowed: true,
      schemaAction: 'unchanged',
      addedColumns: [],
      targetHeaders: existing.slice(0),
      message: 'Schema unchanged'
    };
  }

  return {
    allowed: true,
    schemaAction: 'unchanged',
    addedColumns: [],
    targetHeaders: existing.slice(0),
    message: 'Incoming columns reordered by name'
  };
}

function normalizeIncomingHeaderList_(values) {
  if (!Array.isArray(values)) {
    return [];
  }

  var normalized = [];
  for (var i = 0; i < values.length; i += 1) {
    normalized.push(normalizeColumnName_(values[i]));
  }
  return normalized;
}

function blockedSchemaTransition_(message, details) {
  return {
    allowed: false,
    schemaAction: 'blocked',
    addedColumns: [],
    targetHeaders: [],
    message: message,
    details: details
  };
}
