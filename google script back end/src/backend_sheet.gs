function backendGetSpreadsheet_() {
  var spreadsheetId = backendTrimString_(PropertiesService.getScriptProperties().getProperty('SHEET_ID'));
  if (spreadsheetId) {
    return SpreadsheetApp.openById(spreadsheetId);
  }

  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw backendCreateError_(
      'NO_SPREADSHEET',
      true,
      'No active spreadsheet is available',
      {}
    );
  }

  return spreadsheet;
}

function backendGetOrCreateSheet_(spreadsheet, sheetName) {
  var sheet = spreadsheet.getSheetByName(sheetName);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(sheetName);
  }
  return sheet;
}

function backendListVisibleSheetNames_() {
  var spreadsheet = backendGetSpreadsheet_();
  var sheets = spreadsheet.getSheets ? spreadsheet.getSheets() : [];
  var names = [];

  for (var index = 0; index < sheets.length; index += 1) {
    var sheet = sheets[index];
    if (!sheet) {
      continue;
    }

    if (sheet.isSheetHidden && sheet.isSheetHidden()) {
      continue;
    }

    var name = backendTrimString_(sheet.getName ? sheet.getName() : '');
    if (name) {
      names.push(name);
    }
  }

  return names;
}

function backendSheetReadValues_(sheet) {
  if (!sheet || !sheet.getDataRange || !sheet.getDataRange()) {
    return [];
  }

  var values = sheet.getDataRange().getValues ? sheet.getDataRange().getValues() : [];
  if (!Array.isArray(values)) {
    return [];
  }

  return backendTrimTrailingBlankRows_(values.map(function normalizeRow(row) {
    return Array.isArray(row) ? backendTrimTrailingBlankCells_(row) : [];
  }));
}

function backendNormalizeTableWidth_(rows) {
  var width = 0;
  for (var index = 0; index < rows.length; index += 1) {
    var row = rows[index];
    if (Array.isArray(row) && row.length > width) {
      width = row.length;
    }
  }

  return rows.map(function normalizeRow(row) {
    var source = Array.isArray(row) ? row.slice(0) : [];
    while (source.length < width) {
      source.push('');
    }
    return source;
  });
}

function backendWriteSheetValues_(sheet, rows) {
  var normalized = backendNormalizeTableWidth_(Array.isArray(rows) ? rows : []);
  if (!normalized.length) {
    if (sheet.clearContents) {
      sheet.clearContents();
    }
    return;
  }

  if (sheet.clearContents) {
    sheet.clearContents();
  }

  sheet.getRange(1, 1, normalized.length, normalized[0].length).setValues(normalized);
}

function backendMainHeader_(columns) {
  return backendCloneArray_(columns).concat([
    BACKEND_V2_CONFIG.technicalDateColumnName,
    BACKEND_V2_CONFIG.technicalSourceColumnName,
  ]);
}

function backendStagingHeader_(columns) {
  return ['__chunk_index', '__row_index'].concat(backendMainHeader_(columns));
}

function backendCanonicalColumnName_(value) {
  return backendTrimString_(value).replace(/\s+/g, ' ').toLowerCase();
}

function backendIsTechnicalColumn_(value) {
  return value === BACKEND_V2_CONFIG.technicalDateColumnName
    || value === BACKEND_V2_CONFIG.technicalSourceColumnName;
}

function backendSplitMainHeader_(header) {
  var userColumns = [];
  var dateIndex = -1;
  var sourceIndex = -1;

  for (var index = 0; index < header.length; index += 1) {
    var columnName = backendTrimString_(header[index]);
    if (!columnName) {
      continue;
    }

    if (columnName === BACKEND_V2_CONFIG.technicalDateColumnName) {
      dateIndex = index;
      continue;
    }

    if (columnName === BACKEND_V2_CONFIG.technicalSourceColumnName) {
      sourceIndex = index;
      continue;
    }

    userColumns.push(columnName);
  }

  return {
    userColumns: userColumns,
    dateIndex: dateIndex,
    sourceIndex: sourceIndex,
  };
}

function backendMergeMainHeader_(currentHeader, requestColumns) {
  var split = backendSplitMainHeader_(currentHeader);
  var mergedUserColumns = backendCloneArray_(split.userColumns);
  var seen = Object.create(null);

  for (var index = 0; index < mergedUserColumns.length; index += 1) {
    seen[backendCanonicalColumnName_(mergedUserColumns[index])] = true;
  }

  for (var requestIndex = 0; requestIndex < requestColumns.length; requestIndex += 1) {
    var requestColumn = backendTrimString_(requestColumns[requestIndex]);
    var key = backendCanonicalColumnName_(requestColumn);
    if (!requestColumn || backendIsTechnicalColumn_(requestColumn) || seen[key]) {
      continue;
    }
    seen[key] = true;
    mergedUserColumns.push(requestColumn);
  }

  if (!mergedUserColumns.length) {
    mergedUserColumns = backendCloneArray_(requestColumns);
  }

  return backendMainHeader_(mergedUserColumns);
}

function backendBuildHeaderIndexMap_(header) {
  var map = Object.create(null);
  for (var index = 0; index < header.length; index += 1) {
    var key = backendCanonicalColumnName_(header[index]);
    if (key && map[key] === undefined) {
      map[key] = index;
    }
  }
  return map;
}

function backendProjectRowToHeader_(sourceHeader, row, targetHeader) {
  var sourceMap = backendBuildHeaderIndexMap_(sourceHeader);
  var projected = [];

  for (var index = 0; index < targetHeader.length; index += 1) {
    var key = backendCanonicalColumnName_(targetHeader[index]);
    var sourceIndex = sourceMap[key];
    projected.push(sourceIndex === undefined ? '' : backendCoerceCellValue_(row[sourceIndex]));
  }

  return projected;
}

function backendProjectRowsToHeader_(sourceHeader, rows, targetHeader) {
  var projectedRows = [];
  for (var index = 0; index < rows.length; index += 1) {
    projectedRows.push(backendProjectRowToHeader_(sourceHeader, rows[index], targetHeader));
  }
  return projectedRows;
}

function backendApplyLegacyMarkerMigration_(rows, header) {
  var split = backendSplitMainHeader_(header);
  if (split.dateIndex < 0 || split.sourceIndex < 0) {
    return false;
  }

  var changed = false;
  for (var index = 0; index < rows.length; index += 1) {
    var row = rows[index];
    if (!backendTrimString_(row[split.dateIndex])) {
      continue;
    }
    if (backendTrimString_(row[split.sourceIndex])) {
      continue;
    }
    row[split.sourceIndex] = BACKEND_V2_CONFIG.technicalSourceValue;
    changed = true;
  }

  return changed;
}

function backendHideTechnicalColumns_(sheet, header) {
  if (!sheet.hideColumns || header.length < 2) {
    return;
  }

  sheet.hideColumns(header.length - 1, 2);
}

function backendEnsureMainSheet_(spreadsheet, request) {
  var sheet = backendGetOrCreateSheet_(spreadsheet, request.sheetName);
  if (sheet.getFrozenRows && sheet.getFrozenRows() !== 1) {
    sheet.setFrozenRows(1);
  }

  var currentRows = backendSheetReadValues_(sheet);
  var currentHeader = currentRows.length ? backendTrimTrailingBlankCells_(currentRows[0]) : [];
  var currentSplit = backendSplitMainHeader_(currentHeader);
  var mergedHeader = backendMergeMainHeader_(currentHeader, request.columns);
  var existingDataRows = currentRows.length > 1 ? currentRows.slice(1) : [];
  var projectedRows = currentHeader.length
    ? backendProjectRowsToHeader_(currentHeader, existingDataRows, mergedHeader)
    : existingDataRows;
  var migrated = currentHeader.length
    && currentSplit.dateIndex >= 0
    && currentSplit.sourceIndex < 0
    ? backendApplyLegacyMarkerMigration_(projectedRows, mergedHeader)
    : false;

  if (!currentRows.length) {
    backendWriteSheetValues_(sheet, [mergedHeader]);
  } else if (!backendSequenceEquals_(currentHeader, mergedHeader) || migrated) {
    backendWriteSheetValues_(sheet, [mergedHeader].concat(projectedRows));
  }

  backendHideTechnicalColumns_(sheet, mergedHeader);
  return sheet;
}

function backendEnsureStagingSheet_(spreadsheet, request, stagingSheetName) {
  var sheet = backendGetOrCreateSheet_(spreadsheet, stagingSheetName);
  if (sheet.hideSheet) {
    sheet.hideSheet();
  }
  if (sheet.getFrozenRows && sheet.getFrozenRows() !== 1) {
    sheet.setFrozenRows(1);
  }

  var header = backendStagingHeader_(request.columns);
  var currentRows = backendSheetReadValues_(sheet);
  var currentHeader = currentRows.length ? backendTrimTrailingBlankCells_(currentRows[0]) : [];

  if (!backendSequenceEquals_(currentHeader, header)) {
    backendWriteSheetValues_(sheet, [header]);
  }

  return sheet;
}

function backendBuildMainRows_(request) {
  var rows = [];

  for (var rowIndex = 0; rowIndex < request.records.length; rowIndex += 1) {
    var record = request.records[rowIndex];
    var row = [];

    for (var columnIndex = 0; columnIndex < request.columns.length; columnIndex += 1) {
      var columnName = request.columns[columnIndex];
      row.push(backendCoerceCellValue_(record[columnName]));
    }

    row.push(backendCoerceCellValue_(request.exportDate));
    row.push(BACKEND_V2_CONFIG.technicalSourceValue);
    rows.push(row);
  }

  return rows;
}

function backendBuildStagingRows_(request) {
  var directRows = backendBuildMainRows_(request);
  return directRows.map(function mapDirectRow(row, index) {
    return [request.chunkIndex, index + 1].concat(row);
  });
}

function backendReadStagedChunkRows_(sheet) {
  var rows = backendSheetReadValues_(sheet);
  return rows.length > 1 ? rows.slice(1) : [];
}

function backendReplaceStagingChunkRows_(sheet, request) {
  var header = backendStagingHeader_(request.columns);
  var existingRows = backendReadStagedChunkRows_(sheet);
  var retainedRows = [];
  var duplicate = false;

  for (var index = 0; index < existingRows.length; index += 1) {
    var row = existingRows[index];
    if (backendToInteger_(row[0]) === request.chunkIndex) {
      duplicate = true;
      continue;
    }
    retainedRows.push(row);
  }

  backendWriteSheetValues_(sheet, [header].concat(retainedRows).concat(backendBuildStagingRows_(request)));
  return {
    duplicate: duplicate,
  };
}

function backendReadStageChunkIndexSet_(sheet) {
  var rows = backendReadStagedChunkRows_(sheet);
  var set = Object.create(null);

  for (var index = 0; index < rows.length; index += 1) {
    var chunkIndex = backendToInteger_(rows[index][0]);
    if (chunkIndex !== null) {
      set[chunkIndex] = true;
    }
  }

  return set;
}

function backendHasAllChunks_(sheet, totalChunks) {
  var chunkSet = backendReadStageChunkIndexSet_(sheet);
  return Object.keys(chunkSet).length === totalChunks;
}

function backendBuildPromotedRows_(sheet) {
  var rows = backendReadStagedChunkRows_(sheet);
  var promotedRows = [];

  for (var index = 0; index < rows.length; index += 1) {
    var row = rows[index];
    promotedRows.push({
      chunkIndex: backendToInteger_(row[0]) || 0,
      rowIndex: backendToInteger_(row[1]) || 0,
      values: row.slice(2),
    });
  }

  promotedRows.sort(function sortPromotedRows(left, right) {
    if (left.chunkIndex !== right.chunkIndex) {
      return left.chunkIndex - right.chunkIndex;
    }
    return left.rowIndex - right.rowIndex;
  });

  return promotedRows.map(function mapPromotedRow(row) {
    return row.values;
  });
}

function backendRewriteMainSheet_(sheet, request, promotedRows) {
  var currentRows = backendSheetReadValues_(sheet);
  var currentHeader = currentRows.length ? backendTrimTrailingBlankCells_(currentRows[0]) : [];
  var header = currentHeader.length ? backendMergeMainHeader_(currentHeader, request.columns) : backendMainHeader_(request.columns);
  var dataRows = currentRows.length > 1 ? currentRows.slice(1) : [];
  var split = backendSplitMainHeader_(header);
  var retainedRows = [];

  for (var index = 0; index < dataRows.length; index += 1) {
    var row = dataRows[index];
    var sameDate = backendTrimString_(row[split.dateIndex]) === request.exportDate;
    var sameSource = backendTrimString_(row[split.sourceIndex]) === BACKEND_V2_CONFIG.technicalSourceValue;
    if (sameDate && sameSource) {
      continue;
    }
    retainedRows.push(row);
  }

  var promoted = backendProjectRowsToHeader_(backendMainHeader_(request.columns), promotedRows, header);
  backendWriteSheetValues_(sheet, [header].concat(retainedRows).concat(promoted));
  backendHideTechnicalColumns_(sheet, header);
}

function backendDeleteStagingSheet_(spreadsheet, sheet) {
  if (spreadsheet.deleteSheet) {
    spreadsheet.deleteSheet(sheet);
    return;
  }

  if (sheet.clearContents) {
    sheet.clearContents();
  }
}

function backendRunStateKey_(runId) {
  return BACKEND_V2_CONFIG.runStatePrefix + backendTrimString_(runId);
}

function backendLoadRunState_(runId) {
  var raw = PropertiesService.getScriptProperties().getProperty(backendRunStateKey_(runId));
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw);
  } catch (_error) {
    return null;
  }
}

function backendSaveRunState_(state) {
  var runId = backendTrimString_(state && state.run_id);
  if (!runId) {
    throw backendCreateError_(
      'INVALID_RUN_STATE',
      false,
      'Run state is missing run_id',
      {}
    );
  }

  PropertiesService.getScriptProperties().setProperty(
    backendRunStateKey_(runId),
    JSON.stringify(state)
  );
}

function backendParseIsoTimestampMs_(value) {
  var text = backendTrimString_(value);
  if (!text) {
    return null;
  }

  var parsed = Date.parse(text);
  if (isNaN(parsed)) {
    return null;
  }

  return parsed;
}

function backendCollectStaleRuns_(spreadsheet) {
  var properties = PropertiesService.getScriptProperties().getProperties();
  var keys = Object.keys(properties || {});
  var now = Date.now();

  for (var index = 0; index < keys.length; index += 1) {
    var key = keys[index];
    if (key.indexOf(BACKEND_V2_CONFIG.runStatePrefix) !== 0) {
      continue;
    }

    var state;
    try {
      state = JSON.parse(properties[key]);
    } catch (_error) {
      PropertiesService.getScriptProperties().deleteProperty(key);
      continue;
    }

    var updatedAt = backendParseIsoTimestampMs_(state && state.updated_at);
    if (updatedAt !== null && (now - updatedAt) <= BACKEND_V2_CONFIG.staleRunTtlMs) {
      continue;
    }

    var stagingSheetName = backendTrimString_(state && state.staging_sheet_name);
    if (stagingSheetName) {
      var stagingSheet = spreadsheet.getSheetByName(stagingSheetName);
      if (stagingSheet) {
        backendDeleteStagingSheet_(spreadsheet, stagingSheet);
      }
    }

    PropertiesService.getScriptProperties().deleteProperty(key);
  }
}

function backendWithScriptLock_(callback) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(BACKEND_V2_CONFIG.defaultLockTimeoutMs)) {
    throw backendCreateError_(
      'LOCK_UNAVAILABLE',
      true,
      'Could not acquire script lock',
      {}
    );
  }

  try {
    return callback();
  } finally {
    lock.releaseLock();
  }
}

function backendCreateRunState_(request, stagingSheetName) {
  return {
    protocol_version: request.protocolVersion,
    job_name: request.jobName,
    run_id: request.runId,
    sheet_name: request.sheetName,
    export_date: request.exportDate,
    total_chunks: request.totalChunks,
    total_rows: request.totalRows,
    staging_sheet_name: stagingSheetName,
    completed: false,
    updated_at: backendNowIso_(),
  };
}
