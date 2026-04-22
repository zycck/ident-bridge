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

function backendEnsureSheetCapacity_(sheet, minRows, minColumns) {
  const requiredRows = Math.max(0, Number(minRows) || 0);
  const requiredColumns = Math.max(0, Number(minColumns) || 0);

  const maxRows = sheet.getMaxRows ? Number(sheet.getMaxRows()) || 0 : (sheet.getLastRow ? Number(sheet.getLastRow()) || 0 : 0);
  if (requiredRows > maxRows && sheet.insertRowsAfter) {
    sheet.insertRowsAfter(Math.max(maxRows, 1), requiredRows - maxRows);
  }

  const maxColumns = sheet.getMaxColumns ? Number(sheet.getMaxColumns()) || 0 : (sheet.getLastColumn ? Number(sheet.getLastColumn()) || 0 : 0);
  if (requiredColumns > maxColumns && sheet.insertColumnsAfter) {
    sheet.insertColumnsAfter(Math.max(maxColumns, 1), requiredColumns - maxColumns);
  }
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
  backendEnsureSheetCapacity_(sheet, normalized.length, normalized[0].length);
  sheet.getRange(1, 1, normalized.length, normalized[0].length).setValues(normalized);
}

function backendWriteRowsAt_(sheet, startRow, rows) {
  if (!rows.length) {
    return;
  }

  const normalized = backendNormalizeTableWidth_(rows);
  backendEnsureSheetCapacity_(sheet, startRow + normalized.length - 1, normalized[0].length);
  sheet.getRange(startRow, 1, normalized.length, normalized[0].length).setValues(normalized);
}

function backendMainHeader_(columns) {
  return backendCloneArray_(columns).concat([
    BACKEND_V2_CONFIG.technicalDateColumnName,
    BACKEND_V2_CONFIG.technicalSourceColumnName,
  ]);
}

function backendCanonicalColumnName_(value) {
  return backendTrimString_(value).replace(/\s+/g, ' ').toLowerCase();
}

function backendIsTechnicalColumn_(value) {
  return value === BACKEND_V2_CONFIG.technicalDateColumnName
    || value === BACKEND_V2_CONFIG.technicalSourceColumnName;
}

function backendIsLegacySourceId_(value) {
  const normalized = backendTrimString_(value);
  return normalized
    ? BACKEND_V2_CONFIG.legacySourceIds.includes(normalized)
    : false;
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

    if (backendIsLegacySourceId_(sourceValue)) {
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

function backendApplySheetLocaleAndFormats_(spreadsheet, mainContext, request) {
  if (request.chunkIndex !== 1) {
    return;
  }

  backendEnsureSpreadsheetLocale_(spreadsheet);
  const headerMap = backendBuildHeaderIndexMap_(mainContext.header);
  const maxRows = Math.max(
    (mainContext.sheet.getMaxRows ? Number(mainContext.sheet.getMaxRows()) || 0 : 0) - 1,
    1
  );

  for (const columnName of request.columns) {
    const columnIndex = headerMap[backendCanonicalColumnName_(columnName)];
    const format = backendFormatForColumnKind_(backendInferColumnKind_(columnName, request.records));
    if (columnIndex === undefined || !format || !mainContext.sheet.getRange) {
      continue;
    }
    mainContext.sheet.getRange(2, columnIndex + 1, maxRows, 1).setNumberFormat(format);
  }
}

function backendEnsureSpreadsheetLocale_(spreadsheet) {
  if (!spreadsheet || !spreadsheet.setSpreadsheetLocale) {
    return;
  }
  const current = backendTrimString_(spreadsheet.getSpreadsheetLocale ? spreadsheet.getSpreadsheetLocale() : '');
  if (current !== BACKEND_V2_CONFIG.spreadsheetLocale) {
    spreadsheet.setSpreadsheetLocale(BACKEND_V2_CONFIG.spreadsheetLocale);
  }
}

function backendInferColumnKind_(columnName, records) {
  for (const record of records || []) {
    if (!backendIsPlainObject_(record)) {
      continue;
    }
    const parsed = backendTryParseTypedCellValue_(columnName, record[columnName]);
    if (parsed?.kind) {
      return parsed.kind;
    }
  }
  return null;
}

function backendFormatForColumnKind_(kind) {
  if (!kind) {
    return '';
  }
  return BACKEND_V2_CONFIG.columnFormats[kind] || '';
}

function backendTryParseTypedCellValue_(columnName, value) {
  if (value === null || value === undefined || typeof value === 'boolean') {
    return null;
  }

  if (typeof value === 'number' && isFinite(value)) {
    return { kind: 'number', value };
  }

  const text = backendTrimString_(value);
  if (!text) {
    return null;
  }

  if (backendLooksLikePeriodColumn_(columnName)) {
    const period = backendParsePeriodSerial_(text);
    if (period !== null) {
      return { kind: 'period', value: period };
    }
  }

  if (backendLooksLikeDateTimeColumn_(columnName)) {
    const dateTime = backendParseIsoDateTimeSerial_(text);
    if (dateTime !== null) {
      return { kind: 'datetime', value: dateTime };
    }
  }

  if (backendLooksLikeDateColumn_(columnName)) {
    const dateValue = backendParseIsoDateSerial_(text);
    if (dateValue !== null) {
      return { kind: 'date', value: dateValue };
    }
  }

  if (backendLooksLikeTimeColumn_(columnName) && !backendLooksLikeDateColumn_(columnName)) {
    const timeValue = backendParseTimeSerial_(text);
    if (timeValue !== null) {
      return { kind: 'time', value: timeValue };
    }
  }

  return null;
}

function backendLooksLikePeriodColumn_(columnName) {
  const canonical = backendCanonicalColumnName_(columnName);
  return canonical.includes('period') || canonical.includes('период');
}

function backendLooksLikeDateColumn_(columnName) {
  const canonical = backendCanonicalColumnName_(columnName);
  return canonical.includes('date')
    || canonical.includes('дата')
    || canonical.includes('day')
    || canonical.includes('день');
}

function backendLooksLikeTimeColumn_(columnName) {
  const canonical = backendCanonicalColumnName_(columnName);
  return canonical.includes('time')
    || canonical.includes('время')
    || canonical.includes('час');
}

function backendLooksLikeDateTimeColumn_(columnName) {
  const canonical = backendCanonicalColumnName_(columnName);
  return canonical.includes('datetime')
    || canonical.includes('timestamp')
    || canonical.includes('created')
    || canonical.includes('updated')
    || canonical.includes('added')
    || (backendLooksLikeDateColumn_(columnName) && backendLooksLikeTimeColumn_(columnName));
}

function backendParsePeriodSerial_(value) {
  const text = backendTrimString_(value);
  let match = text.match(/^(\d{4})-(\d{2})$/);
  if (match) {
    return backendDateSerialFromUtcParts_(Number(match[1]), Number(match[2]), 1, 0, 0, 0, 0);
  }
  match = text.match(/^(\d{2})\.(\d{4})$/);
  if (match) {
    return backendDateSerialFromUtcParts_(Number(match[2]), Number(match[1]), 1, 0, 0, 0, 0);
  }
  return null;
}

function backendParseIsoDateSerial_(value) {
  const match = backendTrimString_(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return null;
  }
  return backendDateSerialFromUtcParts_(Number(match[1]), Number(match[2]), Number(match[3]), 0, 0, 0, 0);
}

function backendParseIsoDateTimeSerial_(value) {
  const match = backendTrimString_(value).match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$/
  );
  if (!match) {
    return null;
  }
  const milliseconds = match[7] ? Number(String(match[7]).padEnd(3, '0').slice(0, 3)) : 0;
  return backendDateSerialFromUtcParts_(
    Number(match[1]),
    Number(match[2]),
    Number(match[3]),
    Number(match[4]),
    Number(match[5]),
    Number(match[6]),
    milliseconds
  );
}

function backendParseTimeSerial_(value) {
  const match = backendTrimString_(value).match(/^(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/);
  if (!match) {
    return null;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  const seconds = match[3] ? Number(match[3]) : 0;
  const milliseconds = match[4] ? Number(String(match[4]).padEnd(3, '0').slice(0, 3)) : 0;
  if (hours > 23 || minutes > 59 || seconds > 59) {
    return null;
  }
  return (hours * 3600 + minutes * 60 + seconds + (milliseconds / 1000)) / 86400;
}

function backendDateSerialFromUtcParts_(year, month, day, hour, minute, second, millisecond) {
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return null;
  }

  const utcMs = Date.UTC(year, month - 1, day, hour || 0, minute || 0, second || 0, millisecond || 0);
  const normalized = new Date(utcMs);
  if (
    normalized.getUTCFullYear() !== year
    || normalized.getUTCMonth() !== month - 1
    || normalized.getUTCDate() !== day
    || normalized.getUTCHours() !== (hour || 0)
    || normalized.getUTCMinutes() !== (minute || 0)
    || normalized.getUTCSeconds() !== (second || 0)
  ) {
    return null;
  }

  return (utcMs - Date.UTC(1899, 11, 30, 0, 0, 0, 0)) / 86400000;
}

function backendEnsureMainSheet_(spreadsheet, request) {
  const sheet = backendGetOrCreateSheet_(spreadsheet, request.sheetName);
  if ((sheet.getFrozenRows?.() || 0) > 0) {
    sheet.setFrozenRows(0);
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

function backendBuildMainRows_(request) {
  return request.records.map((record) => {
    const row = request.columns.map((columnName) => backendCoerceRequestCellValue_(columnName, record[columnName]));
    row.push(backendCoerceCellValue_(request.exportDate));
    row.push(backendCoerceCellValue_(request.sourceId));
    return row;
  });
}

function backendCoerceRequestCellValue_(columnName, value) {
  const parsed = backendTryParseTypedCellValue_(columnName, value);
  if (parsed) {
    return parsed.value;
  }
  return backendCoerceCellValue_(value);
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

  const lastRow = mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0;
  if (lastRow < 2) {
    return [];
  }

  const quotedSheetName = backendQuoteSheetNameForA1_(mainContext.sheet.getName());
  const dateColumn = backendColumnNumberToLetters_(dateIndex + 1);
  const sourceColumn = backendColumnNumberToLetters_(sourceIndex + 1);
  const valueRanges = backendBatchGetValues_(spreadsheet.getId(), [
    `${quotedSheetName}!${dateColumn}2:${dateColumn}${lastRow}`,
    `${quotedSheetName}!${sourceColumn}2:${sourceColumn}${lastRow}`,
  ]);

  const dateValues = valueRanges[0]?.values || [];
  const sourceValues = valueRanges[1]?.values || [];
  const rowCount = Math.max(dateValues.length, sourceValues.length);
  const rowNumbers = [];

  for (let index = 0; index < rowCount; index += 1) {
    const dateValue = backendTrimString_(dateValues[index]?.[0]);
    const sourceValue = backendTrimString_(sourceValues[index]?.[0]);
    const sameSource = sourceValue === request.sourceId || backendIsLegacySourceId_(sourceValue);
    if (dateValue === request.exportDate && sameSource) {
      rowNumbers.push(index + 2);
    }
  }

  return rowNumbers;
}

function backendApplyAppendMode_(mainContext, projectedRows) {
  if (!projectedRows.length) {
    return;
  }

  const startRow = Math.max(mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0, 1) + 1;
  backendWriteRowsAt_(mainContext.sheet, startRow, projectedRows);
}

function backendApplyReplaceAllMode_(spreadsheet, mainContext, projectedRows) {
  const lastRow = mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0;
  if (lastRow > 1) {
    backendRunBatchUpdate_(spreadsheet, [
      backendBuildDeleteRowsRequest_(mainContext.sheetId, 2, lastRow - 1),
    ]);
  }

  if (!projectedRows.length) {
    return;
  }

  backendWriteRowsAt_(mainContext.sheet, 2, projectedRows);
}

function backendApplyReplaceByDateSourceMode_(spreadsheet, mainContext, request, projectedRows) {
  const matchedRowNumbers = backendReadOwnedRowNumbers_(spreadsheet, mainContext, request);
  const ranges = backendCompressRowNumbersToRanges_(matchedRowNumbers);
  const insertionRow = ranges.length
    ? ranges[0].start
    : Math.max(mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0, 1) + 1;

  const requests = ranges
    .slice(0)
    .reverse()
    .map((range) => backendBuildDeleteRowsRequest_(mainContext.sheetId, range.start, range.count));

  if (projectedRows.length && ranges.length) {
    requests.push(backendBuildInsertRowsRequest_(mainContext.sheetId, insertionRow, projectedRows.length));
  }

  backendRunBatchUpdate_(spreadsheet, requests);

  if (!projectedRows.length) {
    return;
  }

  backendWriteRowsAt_(mainContext.sheet, insertionRow, projectedRows);
}

function backendApplyWriteMode_(spreadsheet, mainContext, request, rows) {
  const projectedRows = backendProjectRowsToHeader_(backendMainHeader_(request.columns), rows, mainContext.header);
  if (request.writeMode === BACKEND_V2_CONFIG.writeModes.append) {
    backendApplyAppendMode_(mainContext, projectedRows);
    return;
  }

  if (request.writeMode === BACKEND_V2_CONFIG.writeModes.replaceAll) {
    backendApplyReplaceAllMode_(spreadsheet, mainContext, projectedRows);
    return;
  }

  backendApplyReplaceByDateSourceMode_(spreadsheet, mainContext, request, projectedRows);
}
