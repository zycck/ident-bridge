function getTargetSpreadsheet_() {
  var spreadsheetId = getTargetSpreadsheetId_();
  if (spreadsheetId) {
    return SpreadsheetApp.openById(spreadsheetId);
  }

  var activeSpreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!activeSpreadsheet) {
    throw createWebhookError_('NO_SPREADSHEET', true, 'No active spreadsheet is available for writing', {});
  }

  return activeSpreadsheet;
}

function getOrCreateDataSheet_(spreadsheet) {
  return getOrCreateSheet_(spreadsheet, CONFIG.dataSheetName, false);
}

function getOrCreateLedgerSheet_(spreadsheet) {
  return getOrCreateSheet_(spreadsheet, CONFIG.ledgerSheetName, true);
}

function getOrCreateSheet_(spreadsheet, sheetName, hidden) {
  var sheet = spreadsheet.getSheetByName(sheetName);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(sheetName);
  }

  if (hidden) {
    sheet.hideSheet();
  }

  return sheet;
}

function readHeaderRow_(sheet) {
  if (sheet.getLastRow() < 1 || sheet.getLastColumn() < 1) {
    return [];
  }

  return trimTrailingBlankCells_(sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0]);
}

function ensureDataHeaders_(sheet, headers) {
  if (!headers || !headers.length) {
    return;
  }

  var currentHeaders = readHeaderRow_(sheet);
  if (!currentHeaders.length) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
    return;
  }

  if (sameSequence_(currentHeaders, headers)) {
    return;
  }

  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.setFrozenRows(1);
}

function appendChunkRows_(sheet, headers, records) {
  if (!records.length) {
    return 0;
  }

  var rows = [];
  for (var i = 0; i < records.length; i += 1) {
    rows.push(buildSheetRow_(records[i], headers));
  }

  var startRow = sheet.getLastRow() + 1;
  sheet.getRange(startRow, 1, rows.length, headers.length).setValues(rows);
  return rows.length;
}

function buildSheetRow_(record, headers) {
  var row = [];
  for (var i = 0; i < headers.length; i += 1) {
    row.push(coerceSheetCellValue_(record[headers[i]]));
  }
  return row;
}

function coerceSheetCellValue_(value) {
  if (value === null || value === undefined) {
    return '';
  }

  if (value instanceof Date) {
    return escapeFormulaValue_(value.toISOString());
  }

  if (typeof value === 'string') {
    return escapeFormulaValue_(value);
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }

  return escapeFormulaValue_(stableStringify_(value));
}

function appendIdempotencyLedgerRow_(request, ack, state) {
  var spreadsheet = getTargetSpreadsheet_();
  var ledgerSheet = getOrCreateLedgerSheet_(spreadsheet);
  ensureLedgerHeaders_(ledgerSheet);

  var key = buildIdempotencyKey_(request);
  var row = [
    nowIso_(),
    key,
    state,
    request.runId,
    request.chunkIndex,
    request.jobName,
    ack.status || '',
    ack.error_code || '',
    ack.retryable === true ? 'TRUE' : 'FALSE',
    ack.rows_received !== undefined ? ack.rows_received : '',
    ack.rows_written !== undefined ? ack.rows_written : '',
    ack.schema_action || '',
    stableStringify_(ack.added_columns || []),
    ack.message || '',
    stableStringify_(ack.details || {})
  ];

  ledgerSheet.appendRow(row);
}

function ensureLedgerHeaders_(sheet) {
  if (sheet.getLastRow() > 0) {
    return;
  }

  sheet.getRange(1, 1, 1, 15).setValues([[
    'created_at',
    'idempotency_key',
    'state',
    'run_id',
    'chunk_index',
    'job_name',
    'status',
    'error_code',
    'retryable',
    'rows_received',
    'rows_written',
    'schema_action',
    'added_columns_json',
    'message',
    'details_json'
  ]]);
  sheet.setFrozenRows(1);
}

function findLedgerRecordByKey_(key) {
  var spreadsheet = getTargetSpreadsheet_();
  var sheet = spreadsheet.getSheetByName(CONFIG.ledgerSheetName);
  if (!sheet || sheet.getLastRow() < 2) {
    return null;
  }

  var rows = sheet.getDataRange().getValues();
  for (var i = rows.length - 1; i >= 1; i -= 1) {
    if (rows[i][1] === key) {
      return {
        state: rows[i][2],
        record: {
          run_id: rows[i][3],
          chunk_index: rows[i][4],
          status: rows[i][6],
          error_code: rows[i][7],
          retryable: rows[i][8] === 'TRUE',
          rows_received: rows[i][9],
          rows_written: rows[i][10],
          schema_action: rows[i][11],
          added_columns: parseJsonOrDefault_(rows[i][12], []),
          message: rows[i][13],
          details: parseJsonOrDefault_(rows[i][14], {})
        }
      };
    }
  }

  return null;
}

