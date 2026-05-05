function backendGetSpreadsheet_(properties) {
  const spreadsheetId = backendTrimString_(properties.getProperty('SHEET_ID'));
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

function backendReadHeader_(sheet) {
  const lastColumn = sheet.getLastColumn ? sheet.getLastColumn() : 0;
  if (lastColumn < 1) {
    return [];
  }

  const values = sheet.getRange(1, 1, 1, lastColumn).getValues();
  return values.length ? backendTrimTrailingBlankCells_(values[0]) : [];
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

function backendOwnedHeader_(request) {
  const columns = [];
  const seen = new Set();
  for (const rawColumn of request.columns) {
    const columnName = backendTrimString_(rawColumn);
    const key = backendCanonicalColumnName_(columnName);
    if (!columnName || backendIsTechnicalColumn_(columnName) || seen.has(key)) {
      continue;
    }
    seen.add(key);
    columns.push(columnName);
  }
  columns.push(BACKEND_V2_CONFIG.technicalDateColumnName);
  columns.push(BACKEND_V2_CONFIG.technicalSourceColumnName);
  return columns;
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

function backendColumnMarkerPayload_(columnName, sourceId) {
  return JSON.stringify({
    sourceId,
    columnName,
    canonicalName: backendCanonicalColumnName_(columnName),
  });
}

function backendReadColumnMarker_(sheet, columnNumber) {
  if (!sheet.getRange) {
    return null;
  }

  try {
    const range = sheet.getRange(1, columnNumber);
    if (!range.getDeveloperMetadata) {
      return null;
    }

    for (const metadata of range.getDeveloperMetadata() || []) {
      if (metadata.getKey?.() !== BACKEND_V2_CONFIG.columnMetadataKey) {
        continue;
      }
      try {
        const marker = JSON.parse(backendTrimString_(metadata.getValue?.()));
        if (backendIsPlainObject_(marker)) {
          return marker;
        }
      } catch (_error) {
        continue;
      }
    }
  } catch (_error) {
    return null;
  }
  return null;
}

function backendWriteColumnMarker_(sheet, columnNumber, columnName, sourceId) {
  if (!sheet.getRange) {
    return;
  }

  try {
    const range = sheet.getRange(1, columnNumber);
    if (!range.getDeveloperMetadata || !range.addDeveloperMetadata) {
      return;
    }

    for (const metadata of range.getDeveloperMetadata() || []) {
      if (metadata.getKey?.() === BACKEND_V2_CONFIG.columnMetadataKey && metadata.remove) {
        metadata.remove();
      }
    }
    range.addDeveloperMetadata(BACKEND_V2_CONFIG.columnMetadataKey, backendColumnMarkerPayload_(columnName, sourceId));
  } catch (_error) {
    return;
  }
}

function backendFindMarkedColumnNumber_(sheet, header, columnName, request, claimedColumns) {
  const key = backendCanonicalColumnName_(columnName);
  for (let index = 0; index < header.length; index += 1) {
    const columnNumber = index + 1;
    if (claimedColumns.has(columnNumber) || backendCanonicalColumnName_(header[index]) !== key) {
      continue;
    }

    const marker = backendReadColumnMarker_(sheet, columnNumber);
    if (
      marker
      && backendTrimString_(marker.sourceId) === request.sourceId
      && backendCanonicalColumnName_(marker.columnName) === key
    ) {
      return columnNumber;
    }
  }
  return 0;
}

function backendFindHeaderColumnNumber_(header, columnName, claimedColumns, preferredColumnNumber) {
  const key = backendCanonicalColumnName_(columnName);
  let bestColumnNumber = 0;
  let bestDistance = Number.MAX_SAFE_INTEGER;

  for (let index = 0; index < header.length; index += 1) {
    const columnNumber = index + 1;
    if (claimedColumns.has(columnNumber) || backendCanonicalColumnName_(header[index]) !== key) {
      continue;
    }

    if (!preferredColumnNumber) {
      return columnNumber;
    }

    const distance = Math.abs(columnNumber - preferredColumnNumber);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestColumnNumber = columnNumber;
    }
  }

  return bestColumnNumber;
}

function backendAppendHeaderColumn_(sheet, header, columnName) {
  const columnNumber = header.length + 1;
  backendEnsureSheetCapacity_(sheet, 1, columnNumber);
  sheet.getRange(1, columnNumber).setValues([[columnName]]);
  header[columnNumber - 1] = columnName;
  return columnNumber;
}

function backendResolveOwnedColumnNumber_(sheet, header, columnName, request, claimedColumns) {
  const markedColumnNumber = backendFindMarkedColumnNumber_(sheet, header, columnName, request, claimedColumns);
  if (markedColumnNumber) {
    return markedColumnNumber;
  }

  const headerColumnNumber = backendFindHeaderColumnNumber_(header, columnName, claimedColumns, 0);
  return headerColumnNumber || backendAppendHeaderColumn_(sheet, header, columnName);
}

function backendBuildOwnedLayout_(sheet, currentHeader, request) {
  const header = backendCloneArray_(currentHeader);
  const claimedColumns = new Set();
  const ownedColumns = [];

  for (const columnName of backendOwnedHeader_(request)) {
    const columnNumber = backendResolveOwnedColumnNumber_(sheet, header, columnName, request, claimedColumns);
    claimedColumns.add(columnNumber);
    ownedColumns.push({
      name: columnName,
      canonicalName: backendCanonicalColumnName_(columnName),
      columnNumber,
      technical: backendIsTechnicalColumn_(columnName),
    });
    backendWriteColumnMarker_(sheet, columnNumber, columnName, request.sourceId);
  }

  const ownedColumnNumbers = new Set(ownedColumns.map((column) => column.columnNumber));
  let hasExternalColumns = false;
  for (let index = 0; index < header.length; index += 1) {
    if (backendTrimString_(header[index]) && !ownedColumnNumbers.has(index + 1)) {
      hasExternalColumns = true;
      break;
    }
  }

  const dateColumn = ownedColumns.find((column) => column.name === BACKEND_V2_CONFIG.technicalDateColumnName);
  const sourceColumn = ownedColumns.find((column) => column.name === BACKEND_V2_CONFIG.technicalSourceColumnName);
  return {
    header,
    ownedColumns,
    hasExternalColumns,
    dateColumnNumber: dateColumn?.columnNumber || 0,
    sourceColumnNumber: sourceColumn?.columnNumber || 0,
  };
}

function backendHideTechnicalColumns_(sheet, layout) {
  if (!sheet.hideColumns || !layout) {
    return;
  }

  for (const column of layout.ownedColumns) {
    if (column.technical) {
      sheet.hideColumns(column.columnNumber, 1);
    }
  }
}

function backendApplySheetLocaleAndFormats_(spreadsheet, mainContext, request) {
  if (request.chunkIndex !== 1) {
    return;
  }

  backendEnsureSpreadsheetLocale_(spreadsheet);
  const maxRows = Math.max(
    (mainContext.sheet.getMaxRows ? Number(mainContext.sheet.getMaxRows()) || 0 : 0) - 1,
    1
  );

  for (const columnName of request.columns) {
    const ownedColumn = mainContext.ownedColumns.find((column) => (
      backendCanonicalColumnName_(column.name) === backendCanonicalColumnName_(columnName)
    ));
    const format = backendFormatForColumnKind_(backendInferColumnKind_(columnName, request.records));
    if (!ownedColumn || !format || !mainContext.sheet.getRange) {
      continue;
    }
    mainContext.sheet.getRange(2, ownedColumn.columnNumber, maxRows, 1).setNumberFormat(format);
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
  const layout = backendBuildOwnedLayout_(sheet, currentHeader, request);
  backendHideTechnicalColumns_(sheet, layout);
  return {
    sheet,
    sheetId: sheet.getSheetId(),
    header: layout.header,
    ownedColumns: layout.ownedColumns,
    hasExternalColumns: layout.hasExternalColumns,
    dateColumnNumber: layout.dateColumnNumber,
    sourceColumnNumber: layout.sourceColumnNumber,
  };
}

function backendBuildMainRows_(request) {
  const columns = backendOwnedHeader_(request);
  return request.records.map((record) => {
    return columns.map((columnName) => {
      if (columnName === BACKEND_V2_CONFIG.technicalDateColumnName) {
        return backendCoerceCellValue_(request.exportDate);
      }
      if (columnName === BACKEND_V2_CONFIG.technicalSourceColumnName) {
        return backendCoerceCellValue_(request.sourceId);
      }
      return backendCoerceRequestCellValue_(columnName, record[columnName]);
    });
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
  if (!mainContext.dateColumnNumber || !mainContext.sourceColumnNumber) {
    return [];
  }

  const lastRow = mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0;
  if (lastRow < 2) {
    return [];
  }

  const quotedSheetName = backendQuoteSheetNameForA1_(mainContext.sheet.getName());
  const dateColumn = backendColumnNumberToLetters_(mainContext.dateColumnNumber);
  const sourceColumn = backendColumnNumberToLetters_(mainContext.sourceColumnNumber);
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

function backendReadOwnedRowNumbersByMonth_(spreadsheet, mainContext, request) {
  if (!mainContext.dateColumnNumber || !mainContext.sourceColumnNumber) {
    return [];
  }

  const lastRow = mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0;
  if (lastRow < 2) {
    return [];
  }

  const monthPrefix = backendTrimString_(request.exportDate).slice(0, 7);
  if (monthPrefix.length < 7) {
    return [];
  }

  const quotedSheetName = backendQuoteSheetNameForA1_(mainContext.sheet.getName());
  const dateColumn = backendColumnNumberToLetters_(mainContext.dateColumnNumber);
  const sourceColumn = backendColumnNumberToLetters_(mainContext.sourceColumnNumber);
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
    if (dateValue.length >= 7 && dateValue.slice(0, 7) === monthPrefix && sameSource) {
      rowNumbers.push(index + 2);
    }
  }

  return rowNumbers;
}

function backendWriteOwnedRowsAt_(mainContext, startRow, rows) {
  if (!rows.length) {
    return;
  }

  backendEnsureSheetCapacity_(mainContext.sheet, startRow + rows.length - 1, mainContext.sheet.getMaxColumns?.() || mainContext.header.length);
  for (let columnOffset = 0; columnOffset < mainContext.ownedColumns.length; columnOffset += 1) {
    const targetColumn = mainContext.ownedColumns[columnOffset].columnNumber;
    const values = rows.map((row) => [row[columnOffset] === undefined ? '' : row[columnOffset]]);
    mainContext.sheet.getRange(startRow, targetColumn, rows.length, 1).setValues(values);
  }
}

function backendClearOwnedRows_(mainContext, rowNumbers) {
  const ranges = backendCompressRowNumbersToRanges_(rowNumbers);
  for (const range of ranges) {
    for (const column of mainContext.ownedColumns) {
      mainContext.sheet.getRange(range.start, column.columnNumber, range.count, 1).clearContent();
    }
  }
}

function backendClearOwnedRowRange_(mainContext, startRow, count) {
  if (count <= 0) {
    return;
  }
  backendClearOwnedRows_(mainContext, Array.from({ length: count }, (_value, index) => startRow + index));
}

function backendApplyOwnedOnlyReplace_(mainContext, matchedRowNumbers, projectedRows) {
  const targetRows = matchedRowNumbers.slice(0).sort((left, right) => left - right);
  const writeCount = Math.min(targetRows.length, projectedRows.length);

  for (let index = 0; index < writeCount; index += 1) {
    backendWriteOwnedRowsAt_(mainContext, targetRows[index], [projectedRows[index]]);
  }

  if (targetRows.length > projectedRows.length) {
    backendClearOwnedRows_(mainContext, targetRows.slice(projectedRows.length));
  }

  if (projectedRows.length > targetRows.length) {
    const startRow = Math.max(mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0, 1) + 1;
    backendWriteOwnedRowsAt_(mainContext, startRow, projectedRows.slice(targetRows.length));
  }
}

function backendApplyAppendMode_(mainContext, projectedRows) {
  if (!projectedRows.length) {
    return;
  }

  const startRow = Math.max(mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0, 1) + 1;
  backendWriteOwnedRowsAt_(mainContext, startRow, projectedRows);
}

function backendApplyReplaceAllMode_(spreadsheet, mainContext, projectedRows) {
  const lastRow = mainContext.sheet.getLastRow ? mainContext.sheet.getLastRow() : 0;
  if (mainContext.hasExternalColumns) {
    if (lastRow > 1) {
      backendClearOwnedRowRange_(mainContext, 2, lastRow - 1);
    }
    if (projectedRows.length) {
      backendWriteOwnedRowsAt_(mainContext, 2, projectedRows);
    }
    return;
  }

  if (lastRow > 1) {
    backendRunBatchUpdate_(spreadsheet, [
      backendBuildDeleteRowsRequest_(mainContext.sheetId, 2, lastRow - 1),
    ]);
  }

  if (!projectedRows.length) {
    return;
  }

  backendWriteOwnedRowsAt_(mainContext, 2, projectedRows);
}

function backendApplyReplaceByDateSourceMode_(spreadsheet, mainContext, request, projectedRows) {
  const matchedRowNumbers = backendReadOwnedRowNumbers_(spreadsheet, mainContext, request);
  if (mainContext.hasExternalColumns) {
    backendApplyOwnedOnlyReplace_(mainContext, matchedRowNumbers, projectedRows);
    return;
  }

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

  backendWriteOwnedRowsAt_(mainContext, insertionRow, projectedRows);
}

function backendApplyReplaceByMonthSourceMode_(spreadsheet, mainContext, request, projectedRows) {
  const matchedRowNumbers = backendReadOwnedRowNumbersByMonth_(spreadsheet, mainContext, request);
  if (mainContext.hasExternalColumns) {
    backendApplyOwnedOnlyReplace_(mainContext, matchedRowNumbers, projectedRows);
    return;
  }

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

  backendWriteOwnedRowsAt_(mainContext, insertionRow, projectedRows);
}

function backendApplyWriteMode_(spreadsheet, mainContext, request, rows) {
  const projectedRows = rows;
  if (request.writeMode === BACKEND_V2_CONFIG.writeModes.append) {
    backendApplyAppendMode_(mainContext, projectedRows);
    return;
  }

  if (request.writeMode === BACKEND_V2_CONFIG.writeModes.replaceAll) {
    backendApplyReplaceAllMode_(spreadsheet, mainContext, projectedRows);
    return;
  }

  if (request.writeMode === BACKEND_V2_CONFIG.writeModes.replaceByMonthSource) {
    backendApplyReplaceByMonthSourceMode_(spreadsheet, mainContext, request, projectedRows);
    return;
  }

  backendApplyReplaceByDateSourceMode_(spreadsheet, mainContext, request, projectedRows);
}
