function backendGetSpreadsheet_(scriptProperties) {
  const spreadsheetId = backendTrimString_(scriptProperties.getProperty('SHEET_ID'));
  if (spreadsheetId) {
    return SpreadsheetApp.openById(spreadsheetId);
  }

  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw backendCreateError_('NO_SPREADSHEET', true, 'No active spreadsheet is available', {});
  }

  return spreadsheet;
}

function backendGetOrCreateSheet_(spreadsheet, sheetName) {
  let sheet = spreadsheet.getSheetByName(sheetName);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(sheetName);
  }
  return sheet;
}

function backendListVisibleSheetNames_(spreadsheet) {
  const names = [];
  for (const sheet of spreadsheet.getSheets ? spreadsheet.getSheets() : []) {
    if (!sheet) {
      continue;
    }
    if (sheet.isSheetHidden?.()) {
      continue;
    }

    const name = backendTrimString_(sheet.getName?.());
    if (name) {
      names.push(name);
    }
  }
  return names;
}

function backendReadFullSheetValues_(sheet) {
  const lastRow = sheet.getLastRow ? sheet.getLastRow() : 0;
  const lastColumn = sheet.getLastColumn ? sheet.getLastColumn() : 0;
  if (lastRow < 1 || lastColumn < 1) {
    return [];
  }

  const values = sheet.getRange(1, 1, lastRow, lastColumn).getValues();
  return backendTrimTrailingBlankRows_(values.map((row) => backendTrimTrailingBlankCells_(Array.isArray(row) ? row : [])));
}

function backendReadHeader_(sheet) {
  const lastColumn = sheet.getLastColumn ? sheet.getLastColumn() : 0;
  if (lastColumn < 1) {
    return [];
  }

  const values = sheet.getRange(1, 1, 1, lastColumn).getValues();
  return values.length ? backendTrimTrailingBlankCells_(values[0]) : [];
}

function backendNormalizeTableWidth_(rows) {
  const width = rows.reduce((maxWidth, row) => Math.max(maxWidth, Array.isArray(row) ? row.length : 0), 0);
  return rows.map((row) => {
    const source = Array.isArray(row) ? row.slice(0) : [];
    while (source.length < width) {
      source.push('');
    }
    return source;
  });
}

function backendRewriteWholeSheet_(sheet, rows) {
  const normalized = backendNormalizeTableWidth_(rows);
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

function backendWriteRowsAt_(sheet, startRow, rows) {
  if (!rows.length) {
    return;
  }

  const normalized = backendNormalizeTableWidth_(rows);
  sheet.getRange(startRow, 1, normalized.length, normalized[0].length).setValues(normalized);
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
  const userColumns = [];
  let dateIndex = -1;
  let sourceIndex = -1;

  header.forEach((rawColumnName, index) => {
    const columnName = backendTrimString_(rawColumnName);
    if (!columnName) {
      return;
    }

    if (columnName === BACKEND_V2_CONFIG.technicalDateColumnName) {
      dateIndex = index;
      return;
    }

    if (columnName === BACKEND_V2_CONFIG.technicalSourceColumnName) {
      sourceIndex = index;
      return;
    }

    userColumns.push(columnName);
  });

  return { userColumns, dateIndex, sourceIndex };
}

function backendMergeMainHeader_(currentHeader, requestColumns) {
  const { userColumns } = backendSplitMainHeader_(currentHeader);
  const mergedUserColumns = backendCloneArray_(userColumns);
  const seen = new Set(mergedUserColumns.map((column) => backendCanonicalColumnName_(column)));

  for (const rawColumn of requestColumns) {
    const columnName = backendTrimString_(rawColumn);
    const key = backendCanonicalColumnName_(columnName);
    if (!columnName || backendIsTechnicalColumn_(columnName) || seen.has(key)) {
      continue;
    }
    seen.add(key);
    mergedUserColumns.push(columnName);
  }

  return backendMainHeader_(mergedUserColumns.length ? mergedUserColumns : backendCloneArray_(requestColumns));
}

function backendBuildHeaderIndexMap_(header) {
  return header.reduce((map, rawColumnName, index) => {
    const key = backendCanonicalColumnName_(rawColumnName);
    if (key && map[key] === undefined) {
      map[key] = index;
    }
    return map;
  }, {});
}

function backendProjectRowToHeader_(sourceHeader, row, targetHeader) {
  const sourceMap = backendBuildHeaderIndexMap_(sourceHeader);
  return targetHeader.map((targetColumn) => {
    const sourceIndex = sourceMap[backendCanonicalColumnName_(targetColumn)];
    return sourceIndex === undefined ? '' : backendCoerceCellValue_(row[sourceIndex]);
  });
}

function backendProjectRowsToHeader_(sourceHeader, rows, targetHeader) {
  return rows.map((row) => backendProjectRowToHeader_(sourceHeader, row, targetHeader));
}

function backendApplyLegacyMarkerMigration_(rows, header, request, currentSplit) {
  const { dateIndex, sourceIndex } = backendSplitMainHeader_(header);
  if (dateIndex < 0 || sourceIndex < 0) {
    return false;
  }

  const sourceWasMissing = Boolean(currentSplit) && currentSplit.sourceIndex < 0;
  let changed = false;
  for (const row of rows) {
    const dateValue = backendTrimString_(row[dateIndex]);
    if (!dateValue) {
      continue;
    }

    const sourceValue = backendTrimString_(row[sourceIndex]);
    if (sourceWasMissing && !sourceValue) {
      row[sourceIndex] = request.sourceId;
      changed = true;
      continue;
    }

    if (sourceValue === BACKEND_V2_CONFIG.legacySourceMarker) {
      row[sourceIndex] = request.sourceId;
      changed = true;
    }
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
  const sheet = backendGetOrCreateSheet_(spreadsheet, request.sheetName);
  if (sheet.getFrozenRows?.() !== 1) {
    sheet.setFrozenRows(1);
  }

  const currentHeader = backendReadHeader_(sheet);
  const currentSplit = backendSplitMainHeader_(currentHeader);
  const mergedHeader = backendMergeMainHeader_(currentHeader, request.columns);

  if (!currentHeader.length) {
    backendRewriteWholeSheet_(sheet, [mergedHeader]);
    backendHideTechnicalColumns_(sheet, mergedHeader);
    return { sheet, sheetId: sheet.getSheetId(), header: mergedHeader };
  }

  const headerChanged = !backendSequenceEquals_(currentHeader, mergedHeader);
  const needsMigration = currentSplit.dateIndex >= 0
    && (currentSplit.sourceIndex < 0 || currentHeader.includes(BACKEND_V2_CONFIG.legacySourceMarker));

  if (headerChanged || needsMigration) {
    const existingRows = backendReadFullSheetValues_(sheet);
    const dataRows = existingRows.length > 1 ? existingRows.slice(1) : [];
    const projectedRows = backendProjectRowsToHeader_(currentHeader, dataRows, mergedHeader);
    const migrated = backendApplyLegacyMarkerMigration_(projectedRows, mergedHeader, request, currentSplit);

    if (headerChanged || migrated) {
      backendRewriteWholeSheet_(sheet, [mergedHeader].concat(projectedRows));
    }
  }

  backendHideTechnicalColumns_(sheet, mergedHeader);
  return { sheet, sheetId: sheet.getSheetId(), header: mergedHeader };
}

function backendEnsureStagingSheet_(spreadsheet, request, stagingSheetName) {
  const sheet = backendGetOrCreateSheet_(spreadsheet, stagingSheetName);
  if (sheet.hideSheet) {
    sheet.hideSheet();
  }
  if (sheet.getFrozenRows?.() !== 1) {
    sheet.setFrozenRows(1);
  }

  const header = backendStagingHeader_(request.columns);
  const currentHeader = backendReadHeader_(sheet);
  if (!backendSequenceEquals_(currentHeader, header)) {
    backendRewriteWholeSheet_(sheet, [header]);
  }

  return sheet;
}

function backendBuildMainRows_(request) {
  return request.records.map((record) => {
    const row = request.columns.map((columnName) => backendCoerceCellValue_(record[columnName]));
    row.push(backendCoerceCellValue_(request.exportDate));
    row.push(backendCoerceCellValue_(request.sourceId));
    return row;
  });
}

function backendBuildStagingRows_(request) {
  return backendBuildMainRows_(request).map((row, index) => [request.chunkIndex, index + 1].concat(row));
}

function backendAppendStagingChunkRows_(sheet, request) {
  const rows = backendBuildStagingRows_(request);
  if (!rows.length) {
    return;
  }

  const startRow = Math.max(sheet.getLastRow ? sheet.getLastRow() : 0, 1) + 1;
  backendWriteRowsAt_(sheet, startRow, rows);
}

function backendReadPromotedRows_(sheet) {
  const rows = backendReadFullSheetValues_(sheet);
  const stagedRows = rows.length > 1 ? rows.slice(1) : [];

  return stagedRows
    .map((row) => ({
      chunkIndex: backendToInteger_(row[0]) || 0,
      rowIndex: backendToInteger_(row[1]) || 0,
      values: row.slice(2),
    }))
    .sort((left, right) => {
      if (left.chunkIndex !== right.chunkIndex) {
        return left.chunkIndex - right.chunkIndex;
      }
      return left.rowIndex - right.rowIndex;
    })
    .map((row) => row.values);
}

function backendColumnNumberToLetters_(columnNumber) {
  let value = Number(columnNumber);
  let output = '';
  while (value > 0) {
    const offset = (value - 1) % 26;
    output = String.fromCharCode(65 + offset) + output;
    value = Math.floor((value - 1) / 26);
  }
  return output || 'A';
}

function backendQuoteSheetNameForA1_(sheetName) {
  return `'${String(sheetName).replace(/'/g, "''")}'`;
}

function backendBatchGetValues_(spreadsheetId, ranges) {
  const response = Sheets.Spreadsheets.Values.batchGet(spreadsheetId, {
    ranges,
    majorDimension: 'ROWS',
  });
  return Array.isArray(response?.valueRanges) ? response.valueRanges : [];
}

function backendBuildDeleteRowsRequest_(sheetId, startRow, count) {
  return {
    deleteDimension: {
      range: {
        sheetId,
        dimension: 'ROWS',
        startIndex: startRow - 1,
        endIndex: startRow - 1 + count,
      },
    },
  };
}

function backendBuildInsertRowsRequest_(sheetId, startRow, count) {
  return {
    insertDimension: {
      range: {
        sheetId,
        dimension: 'ROWS',
        startIndex: startRow - 1,
        endIndex: startRow - 1 + count,
      },
      inheritFromBefore: startRow > 1,
    },
  };
}

function backendRunBatchUpdate_(spreadsheet, requests) {
  if (!requests.length) {
    return;
  }

  Sheets.Spreadsheets.batchUpdate({ requests }, spreadsheet.getId());
}

function backendCompressRowNumbersToRanges_(rowNumbers) {
  const normalized = rowNumbers.slice(0).sort((left, right) => left - right);
  if (!normalized.length) {
    return [];
  }

  const ranges = [];
  let start = normalized[0];
  let end = start;

  for (let index = 1; index < normalized.length; index += 1) {
    const current = normalized[index];
    if (current === end + 1) {
      end = current;
      continue;
    }

    ranges.push({ start, count: end - start + 1 });
    start = current;
    end = current;
  }

  ranges.push({ start, count: end - start + 1 });
  return ranges;
}

function backendReadOwnedRowNumbers_(spreadsheet, mainContext, request) {
  const { dateIndex, sourceIndex } = backendSplitMainHeader_(mainContext.header);
  if (dateIndex < 0 || sourceIndex < 0) {
    return [];
  }

  const quotedSheetName = backendQuoteSheetNameForA1_(mainContext.sheet.getName());
  const dateColumn = backendColumnNumberToLetters_(dateIndex + 1);
  const sourceColumn = backendColumnNumberToLetters_(sourceIndex + 1);
  const valueRanges = backendBatchGetValues_(spreadsheet.getId(), [
    `${quotedSheetName}!${dateColumn}2:${dateColumn}`,
    `${quotedSheetName}!${sourceColumn}2:${sourceColumn}`,
  ]);

  const dateValues = valueRanges[0]?.values || [];
  const sourceValues = valueRanges[1]?.values || [];
  const rowCount = Math.max(dateValues.length, sourceValues.length);
  const rowNumbers = [];

  for (let index = 0; index < rowCount; index += 1) {
    const dateValue = backendTrimString_(dateValues[index]?.[0]);
    const sourceValue = backendTrimString_(sourceValues[index]?.[0]);
    const sameSource = sourceValue === request.sourceId || sourceValue === BACKEND_V2_CONFIG.legacySourceMarker;
    if (dateValue === request.exportDate && sameSource) {
      rowNumbers.push(index + 2);
    }
  }

  return rowNumbers;
}

function backendApplyAppendMode_(mainContext, promotedRows) {
  if (!promotedRows.length) {
    return;
  }

  const startRow = Math.max(mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0, 1) + 1;
  backendWriteRowsAt_(mainContext.sheet, startRow, promotedRows);
}

function backendApplyReplaceAllMode_(spreadsheet, mainContext, promotedRows) {
  const lastRow = mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0;
  if (lastRow > 1) {
    backendRunBatchUpdate_(spreadsheet, [
      backendBuildDeleteRowsRequest_(mainContext.sheetId, 2, lastRow - 1),
    ]);
  }

  if (!promotedRows.length) {
    return;
  }

  backendWriteRowsAt_(mainContext.sheet, 2, promotedRows);
}

function backendApplyReplaceByDateSourceMode_(spreadsheet, mainContext, request, promotedRows) {
  const matchedRowNumbers = backendReadOwnedRowNumbers_(spreadsheet, mainContext, request);
  const ranges = backendCompressRowNumbersToRanges_(matchedRowNumbers);
  const insertionRow = ranges.length
    ? ranges[0].start
    : Math.max(mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0, 1) + 1;

  const requests = ranges
    .slice(0)
    .reverse()
    .map((range) => backendBuildDeleteRowsRequest_(mainContext.sheetId, range.start, range.count));

  if (promotedRows.length && ranges.length) {
    requests.push(backendBuildInsertRowsRequest_(mainContext.sheetId, insertionRow, promotedRows.length));
  }

  backendRunBatchUpdate_(spreadsheet, requests);

  if (!promotedRows.length) {
    return;
  }

  backendWriteRowsAt_(mainContext.sheet, insertionRow, promotedRows);
}

function backendApplyWriteMode_(spreadsheet, mainContext, request, rows) {
  const promotedRows = backendProjectRowsToHeader_(backendMainHeader_(request.columns), rows, mainContext.header);
  if (request.writeMode === BACKEND_V2_CONFIG.writeModes.append) {
    backendApplyAppendMode_(mainContext, promotedRows);
    return;
  }

  if (request.writeMode === BACKEND_V2_CONFIG.writeModes.replaceAll) {
    backendApplyReplaceAllMode_(spreadsheet, mainContext, promotedRows);
    return;
  }

  backendApplyReplaceByDateSourceMode_(spreadsheet, mainContext, request, promotedRows);
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
