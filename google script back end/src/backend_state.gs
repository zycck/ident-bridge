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

function backendDeleteRunState_(runId) {
  PropertiesService.getScriptProperties().deleteProperty(backendRunStateKey_(runId));
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
      if (stagingSheet && spreadsheet.deleteSheet) {
        spreadsheet.deleteSheet(stagingSheet);
      } else if (stagingSheet && stagingSheet.clearContents) {
        stagingSheet.clearContents();
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

function backendCreateInitialRunState_(request, stagingSheetName) {
  return {
    protocol_version: request.protocolVersion,
    job_name: request.jobName,
    run_id: request.runId,
    sheet_name: request.sheetName,
    export_date: request.exportDate,
    columns: backendCloneArray_(request.columns),
    total_chunks: request.totalChunks,
    total_rows: request.totalRows,
    staging_sheet_name: stagingSheetName,
    promoted: false,
    created_at: backendNowIso_(),
    updated_at: backendNowIso_(),
  };
}
