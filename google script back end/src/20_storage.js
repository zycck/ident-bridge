class SheetsStore {
  constructor({ spreadsheetId, dataSheetName, ledgerSheetName }) {
    this.spreadsheetId = trimString_(spreadsheetId);
    this.dataSheetName = dataSheetName;
    this.ledgerSheetName = ledgerSheetName;
    this._spreadsheet = null;
    this._bootstrapCache = null;
  }

  beginRequest(request) {
    const key = buildIdempotencyKey_(request);
    const cachedState = this._readIdempotencyState(key);

    if (cachedState && cachedState.state === 'completed') {
      return {
        state: 'completed',
        key,
        record: cachedState.record,
      };
    }

    const lock = LockService.getScriptLock();
    if (!lock.tryLock(5000)) {
      throw createWebhookError_('IDEMPOTENCY_BUSY', true, 'Could not obtain idempotency lock', {
        run_id: request.runId,
        chunk_index: request.chunkIndex,
      });
    }

    try {
      const lockedState = this._readIdempotencyState(key);

      if (lockedState && lockedState.state === 'completed') {
        lock.releaseLock();
        return {
          state: 'completed',
          key,
          record: lockedState.record,
        };
      }

      if (lockedState && lockedState.state === 'processing') {
        throw createWebhookError_('IDEMPOTENCY_BUSY', true, 'Chunk is already being processed', {
          run_id: request.runId,
          chunk_index: request.chunkIndex,
        });
      }

      const leaseRecord = {
        state: 'processing',
        key,
        startedAt: nowIso_(),
        expiresAt: new Date(Date.now() + CONFIG.idempotencyLeaseMs).toISOString(),
        runId: request.runId,
        chunkIndex: request.chunkIndex,
      };

      this._writeLease(key, leaseRecord);
      return {
        state: 'acquired',
        key,
        lease: {
          key,
          lock,
        },
      };
    } catch (error) {
      lock.releaseLock();
      throw error;
    }
  }

  finalizeSuccess(request, ack, lease) {
    const key = buildIdempotencyKey_(request);
    const completedRecord = {
      state: 'completed',
      completedAt: nowIso_(),
      record: {
        run_id: request.runId,
        chunk_index: request.chunkIndex,
        rows_received: ack.rows_received,
        rows_written: ack.rows_written,
        schema_action: ack.schema_action,
        added_columns: cloneArray_(ack.added_columns),
        message: ack.message,
      },
    };

    this._writeCompleted(key, completedRecord);
    this._trackRunKey_(request.runId, key);
    if (request.chunkIndex === request.totalChunks) {
      this._clearRunState_(request.runId);
    }
    this.releaseLease(lease);
  }

  releaseLease(lease) {
    if (!lease) {
      return;
    }

    this._clearLease(lease.key);
    if (lease.lock) {
      lease.lock.releaseLock();
    }
  }

  ensureBootstrap() {
    if (this._bootstrapCache) {
      return cloneObject_(this._bootstrapCache);
    }

    const spreadsheet = this._getSpreadsheet();

    let dataSheet = spreadsheet.getSheetByName(this.dataSheetName);
    if (!dataSheet) {
      dataSheet = spreadsheet.insertSheet(this.dataSheetName);
    }
    if (dataSheet.getFrozenRows() !== 1) {
      dataSheet.setFrozenRows(1);
    }

    let ledgerSheet = spreadsheet.getSheetByName(this.ledgerSheetName);
    if (!ledgerSheet) {
      ledgerSheet = spreadsheet.insertSheet(this.ledgerSheetName);
    }
    if (!ledgerSheet.isSheetHidden()) {
      ledgerSheet.hideSheet();
    }
    if (ledgerSheet.getFrozenRows() !== 1) {
      ledgerSheet.setFrozenRows(1);
    }

    this._bootstrapCache = {
      spreadsheetId: spreadsheet.getId(),
      dataSheetName: dataSheet.getName(),
      ledgerSheetName: ledgerSheet.getName(),
      dataSheetId: dataSheet.getSheetId(),
      ledgerSheetId: ledgerSheet.getSheetId(),
    };

    return cloneObject_(this._bootstrapCache);
  }

  loadRequestContext() {
    const bootstrap = this.ensureBootstrap();
    const response = Sheets.Spreadsheets.Values.batchGet(bootstrap.spreadsheetId, {
      ranges: [
        `${bootstrap.dataSheetName}!1:1`,
        `${bootstrap.ledgerSheetName}!1:1`,
      ],
      majorDimension: 'ROWS',
    });

    const valueRanges = response && response.valueRanges ? response.valueRanges : [];
    const dataHeaders = this._readRangeRow_(valueRanges[0]);
    const ledgerHeaders = this._readRangeRow_(valueRanges[1]);

    return {
      ...bootstrap,
      existingHeaders: trimTrailingBlankCells_(dataHeaders),
      ledgerHeaders: trimTrailingBlankCells_(ledgerHeaders),
    };
  }

  writeChunk({ context, headers, records, ledgerEntry }) {
    const requests = [];

    if (Array.isArray(headers) && headers.length && !sameSequence_(context.existingHeaders, headers)) {
      requests.push(this._buildUpdateRowRequest_(context.dataSheetId, 0, headers));
    }

    if (!context.ledgerHeaders.length) {
      requests.push(this._buildUpdateRowRequest_(context.ledgerSheetId, 0, CONFIG.ledgerHeaders));
    }

    if (Array.isArray(records) && records.length) {
      requests.push(this._buildAppendRowsRequest_(context.dataSheetId, records.map((record) => (
        this._buildDataRow_(record, headers)
      ))));
    }

    if (ledgerEntry) {
      requests.push(this._buildAppendRowsRequest_(context.ledgerSheetId, [
        this._buildLedgerRow_(ledgerEntry),
      ]));
    }

    if (!requests.length) {
      return;
    }

    Sheets.Spreadsheets.batchUpdate({
      requests,
      includeSpreadsheetInResponse: false,
      responseIncludeGridData: false,
    }, context.spreadsheetId);

    if (Array.isArray(headers) && headers.length) {
      context.existingHeaders = headers.slice();
    }

    if (!context.ledgerHeaders.length) {
      context.ledgerHeaders = CONFIG.ledgerHeaders.slice();
    }
  }

  _getSpreadsheet() {
    if (!this._spreadsheet) {
      this._spreadsheet = this.spreadsheetId
        ? SpreadsheetApp.openById(this.spreadsheetId)
        : getTargetSpreadsheet_();
    }

    return this._spreadsheet;
  }

  _readRangeRow_(valueRange) {
    if (!valueRange || !Array.isArray(valueRange.values) || !valueRange.values.length) {
      return [];
    }

    const firstRow = valueRange.values[0];
    return Array.isArray(firstRow) ? firstRow : [];
  }

  _buildDataRow_(record, headers) {
    return headers.map((header) => this._coerceCellValue_(record[header]));
  }

  _buildLedgerRow_(ledgerEntry) {
    return CONFIG.ledgerHeaders.map((header) => ledgerEntry[header] !== undefined ? ledgerEntry[header] : '');
  }

  _coerceCellValue_(value) {
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

  _buildAppendRowsRequest_(sheetId, rows) {
    return {
      appendCells: {
        sheetId,
        rows: rows.map((row) => ({
          values: row.map((value) => this._buildCellData_(value)),
        })),
        fields: 'userEnteredValue',
      },
    };
  }

  _buildUpdateRowRequest_(sheetId, rowIndex, values) {
    return {
      updateCells: {
        start: {
          sheetId,
          rowIndex,
          columnIndex: 0,
        },
        rows: [{
          values: values.map((value) => this._buildCellData_(value)),
        }],
        fields: 'userEnteredValue',
      },
    };
  }

  _buildCellData_(value) {
    if (typeof value === 'boolean') {
      return { userEnteredValue: { boolValue: value } };
    }

    if (typeof value === 'number' && isFinite(value)) {
      return { userEnteredValue: { numberValue: value } };
    }

    return {
      userEnteredValue: {
        stringValue: value === null || value === undefined ? '' : String(value),
      },
    };
  }

  _readIdempotencyState(key) {
    const cache = CacheService.getScriptCache();
    const completedKey = getIdempotencyCompletedKey_(key);
    const leaseKey = getIdempotencyLeaseKey_(key);

    const cachedCompleted = cache.get(completedKey);
    if (cachedCompleted) {
      return JSON.parse(cachedCompleted);
    }

    const properties = PropertiesService.getScriptProperties();
    const storedCompleted = properties.getProperty(completedKey);
    if (storedCompleted) {
      cache.put(completedKey, storedCompleted, CONFIG.idempotencyCacheSeconds);
      return JSON.parse(storedCompleted);
    }

    const cachedLease = cache.get(leaseKey);
    if (cachedLease) {
      const parsedLease = JSON.parse(cachedLease);
      if (parsedLease && parsedLease.state === 'processing' && !isLeaseExpired_(parsedLease)) {
        return {
          state: 'processing',
          record: parsedLease,
        };
      }

      this._clearLease(key);
    }

    const storedLease = properties.getProperty(leaseKey);
    if (storedLease) {
      const parsedLease = JSON.parse(storedLease);
      if (parsedLease && parsedLease.state === 'processing' && !isLeaseExpired_(parsedLease)) {
        cache.put(leaseKey, storedLease, CONFIG.idempotencyCacheSeconds);
        return {
          state: 'processing',
          record: parsedLease,
        };
      }

      this._clearLease(key);
    }

    const recoveredCompleted = this._recoverCompletedStateFromLedger_(key);
    if (recoveredCompleted) {
      this._writeCompleted(key, recoveredCompleted);
      return recoveredCompleted;
    }

    return null;
  }

  _writeCompleted(key, record) {
    const payload = JSON.stringify(record);
    const completedKey = getIdempotencyCompletedKey_(key);

    PropertiesService.getScriptProperties().setProperty(completedKey, payload);
    CacheService.getScriptCache().put(completedKey, payload, CONFIG.idempotencyCacheSeconds);
  }

  _writeLease(key, record) {
    const payload = JSON.stringify(record);
    const leaseKey = getIdempotencyLeaseKey_(key);

    PropertiesService.getScriptProperties().setProperty(leaseKey, payload);
    CacheService.getScriptCache().put(leaseKey, payload, CONFIG.idempotencyCacheSeconds);
  }

  _clearLease(key) {
    const leaseKey = getIdempotencyLeaseKey_(key);
    PropertiesService.getScriptProperties().deleteProperty(leaseKey);
    CacheService.getScriptCache().remove(leaseKey);
  }

  _trackRunKey_(runId, key) {
    const properties = PropertiesService.getScriptProperties();
    const runKey = getIdempotencyRunKey_(runId);
    const current = parseJsonOrDefault_(properties.getProperty(runKey), []);

    if (current.indexOf(key) === -1) {
      const next = current.concat([key]);
      properties.setProperty(runKey, JSON.stringify(next));
    }
  }

  _clearRunState_(runId) {
    const properties = PropertiesService.getScriptProperties();
    const cache = CacheService.getScriptCache();
    const runKey = getIdempotencyRunKey_(runId);
    const trackedKeys = parseJsonOrDefault_(properties.getProperty(runKey), []);

    for (let index = 0; index < trackedKeys.length; index += 1) {
      const key = trackedKeys[index];
      const completedKey = getIdempotencyCompletedKey_(key);
      const leaseKey = getIdempotencyLeaseKey_(key);

      properties.deleteProperty(completedKey);
      properties.deleteProperty(leaseKey);
      cache.remove(completedKey);
      cache.remove(leaseKey);
    }

    properties.deleteProperty(runKey);
  }

  _recoverCompletedStateFromLedger_(key) {
    const bootstrap = this.ensureBootstrap();
    const ledgerSheet = this._getSpreadsheet().getSheetByName(this.ledgerSheetName);

    if (!ledgerSheet) {
      return null;
    }

    const lastRow = ledgerSheet.getLastRow();
    if (lastRow < 2) {
      return null;
    }

    const response = Sheets.Spreadsheets.Values.get(
      bootstrap.spreadsheetId,
      `${bootstrap.ledgerSheetName}!A2:O${lastRow}`
    );
    const rows = response && Array.isArray(response.values) ? response.values : [];

    for (let index = rows.length - 1; index >= 0; index -= 1) {
      const row = rows[index];
      if (row[1] !== key || row[2] !== 'completed') {
        continue;
      }

      return {
        state: 'completed',
        record: {
          run_id: row[3] || '',
          chunk_index: toIntegerOrNull_(row[4]) || 0,
          status: row[6] || '',
          error_code: row[7] || '',
          retryable: row[8] === 'TRUE',
          rows_received: toIntegerOrNull_(row[9]) || 0,
          rows_written: toIntegerOrNull_(row[10]) || 0,
          schema_action: row[11] || '',
          added_columns: parseJsonOrDefault_(row[12], []),
          message: row[13] || '',
          details: parseJsonOrDefault_(row[14], {}),
        },
      };
    }

    return null;
  }
}

let SHEETS_STORE_ = null;

function getSheetsStore_() {
  if (!SHEETS_STORE_) {
    SHEETS_STORE_ = new SheetsStore({
      spreadsheetId: getTargetSpreadsheetId_(),
      dataSheetName: CONFIG.dataSheetName,
      ledgerSheetName: CONFIG.ledgerSheetName,
    });
  }

  return SHEETS_STORE_;
}

function buildIdempotencyKey_(request) {
  return `${CONFIG.idempotencyPropertyPrefix}${sha256Hex_(stableStringify_({
    protocol_version: request.protocolVersion,
    job_name: request.jobName,
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    total_chunks: request.totalChunks,
    total_rows: request.totalRows,
    chunk_rows: request.chunkRows,
    chunk_bytes: request.chunkBytes,
    schema: {
      mode: request.schema.mode,
      columns: request.schema.columns.slice().map((column) => normalizeColumnName_(column)).sort(),
      checksum: request.schema.checksum,
    },
    records: request.records,
  }))}`;
}

function getIdempotencyCompletedKey_(key) {
  return `${key}:completed`;
}

function getIdempotencyLeaseKey_(key) {
  return `${key}:lease`;
}

function getIdempotencyRunKey_(runId) {
  return `${CONFIG.idempotencyPropertyPrefix}run:${runId}`;
}

function isLeaseExpired_(leaseRecord) {
  if (!leaseRecord || !leaseRecord.expiresAt) {
    return true;
  }

  const expiresAt = new Date(leaseRecord.expiresAt).getTime();
  return isNaN(expiresAt) || expiresAt <= Date.now();
}
