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

  var width = normalized[0].length;
  sheet.getRange(1, 1, normalized.length, width).setValues(normalized);
}

function backendMainHeader_(columns) {
  return backendCloneArray_(columns).concat([BACKEND_V2_CONFIG.technicalColumnName]);
}

function backendStagingHeader_(columns) {
  return ['__chunk_index', '__row_index'].concat(backendCloneArray_(columns)).concat([BACKEND_V2_CONFIG.technicalColumnName]);
}

function backendCanonicalColumnName_(value) {
  return backendTrimString_(value).replace(/\s+/g, ' ').toLowerCase();
}

function backendSplitMainHeader_(header) {
  var userColumns = [];
  var technicalIndex = -1;

  for (var index = 0; index < header.length; index += 1) {
    var columnName = backendTrimString_(header[index]);
    if (!columnName) {
      continue;
    }
    if (columnName === BACKEND_V2_CONFIG.technicalColumnName) {
      technicalIndex = index;
      continue;
    }
    userColumns.push(columnName);
  }

  return {
    userColumns: userColumns,
    technicalIndex: technicalIndex,
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
    if (!requestColumn || seen[key]) {
      continue;
    }
    seen[key] = true;
    mergedUserColumns.push(requestColumn);
  }

  if (!mergedUserColumns.length) {
    mergedUserColumns = backendCloneArray_(requestColumns);
  }

  return mergedUserColumns.concat([BACKEND_V2_CONFIG.technicalColumnName]);
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

function backendEnsureMainSheet_(spreadsheet, request) {
  var sheet = backendGetOrCreateSheet_(spreadsheet, request.sheetName);
  if (sheet.getFrozenRows && sheet.getFrozenRows() !== 1) {
    sheet.setFrozenRows(1);
  }

  var currentRows = backendSheetReadValues_(sheet);
  var currentHeader = currentRows.length ? backendTrimTrailingBlankCells_(currentRows[0]) : [];
  var mergedHeader = backendMergeMainHeader_(currentHeader, request.columns);

  if (!backendSequenceEquals_(currentHeader, mergedHeader)) {
    var existingDataRows = currentRows.length > 1 ? currentRows.slice(1) : [];
    var projectedRows = currentHeader.length
      ? backendProjectRowsToHeader_(currentHeader, existingDataRows, mergedHeader)
      : existingDataRows;
    backendWriteSheetValues_(sheet, [mergedHeader].concat(projectedRows));
  } else if (!currentRows.length) {
    backendWriteSheetValues_(sheet, [mergedHeader]);
  }

  if (sheet.hideColumns) {
    sheet.hideColumns(mergedHeader.length, 1);
  }

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

function backendBuildStagingRows_(request) {
  var rows = [];
  for (var rowIndex = 0; rowIndex < request.records.length; rowIndex += 1) {
    var record = request.records[rowIndex];
    var row = [request.chunkIndex, rowIndex + 1];

    for (var columnIndex = 0; columnIndex < request.columns.length; columnIndex += 1) {
      var columnName = request.columns[columnIndex];
      row.push(backendCoerceCellValue_(record[columnName]));
    }

    row.push(backendCoerceCellValue_(request.exportDate));
    rows.push(row);
  }

  return rows;
}

function backendReadStagedChunkRows_(sheet) {
  var rows = backendSheetReadValues_(sheet);
  return rows.length > 1 ? rows.slice(1) : [];
}

function backendReplaceStagingChunkRows_(sheet, request) {
  var header = backendStagingHeader_(request.columns);
  var existingRows = backendReadStagedChunkRows_(sheet);
  var retainedRows = [];
  var chunkIndex = request.chunkIndex;

  for (var index = 0; index < existingRows.length; index += 1) {
    var row = existingRows[index];
    if (backendToInteger_(row[0]) === chunkIndex) {
      continue;
    }
    retainedRows.push(row);
  }

  var nextRows = retainedRows.concat(backendBuildStagingRows_(request));
  backendWriteSheetValues_(sheet, [header].concat(nextRows));
  return {
    duplicate: retainedRows.length !== existingRows.length,
    rows: nextRows,
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

function backendBuildPromotedRows_(request, sheet) {
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

function backendRewriteMainSheet_(sheet, request, stagedRows) {
  var currentRows = backendSheetReadValues_(sheet);
  var header = currentRows.length ? backendTrimTrailingBlankCells_(currentRows[0]) : backendMainHeader_(request.columns);
  var split = backendSplitMainHeader_(header);
  var techIndex = split.technicalIndex >= 0 ? split.technicalIndex : header.length - 1;
  var dataRows = currentRows.length > 1 ? currentRows.slice(1) : [];
  var retainedRows = [];

  for (var index = 0; index < dataRows.length; index += 1) {
    var row = dataRows[index];
    if (backendTrimString_(row[techIndex]) === request.exportDate) {
      continue;
    }
    retainedRows.push(row);
  }

  var stagingHeader = backendMainHeader_(request.columns);
  var promotedRows = backendProjectRowsToHeader_(stagingHeader, stagedRows, header);
  backendWriteSheetValues_(sheet, [header].concat(retainedRows).concat(promotedRows));
  if (sheet.hideColumns) {
    sheet.hideColumns(header.length, 1);
  }
}

function backendCleanupStagingSheet_(sheet) {
  if (sheet.clearContents) {
    sheet.clearContents();
  }
}
