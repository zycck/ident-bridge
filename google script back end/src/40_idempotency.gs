function buildIdempotencyKey_(request) {
  var keyMaterial = stableStringify_({
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
      columns: request.schema.columns,
      checksum: request.schema.checksum
    },
    records: request.records
  });

  return CONFIG.idempotencyPropertyPrefix + sha256Hex_(keyMaterial);
}

function lookupIdempotencyState_(request) {
  var key = buildIdempotencyKey_(request);
  var stored = readStoredIdempotencyRecord_(key);
  if (stored && stored.state === 'completed') {
    return {
      state: 'completed',
      key: key,
      record: stored.record
    };
  }

  if (stored && stored.state === 'processing') {
    return {
      state: 'processing',
      key: key,
      record: stored.record
    };
  }

  return {
    state: 'missing',
    key: key,
    record: null
  };
}

function acquireIdempotencyLease_(request) {
  var key = buildIdempotencyKey_(request);
  var lock = LockService.getScriptLock();

  if (!lock.tryLock(5000)) {
    throw createWebhookError_('IDEMPOTENCY_BUSY', true, 'Could not obtain idempotency lock', {
      run_id: request.runId,
      chunk_index: request.chunkIndex
    });
  }

  try {
    var existing = readStoredIdempotencyRecord_(key);
    if (existing && existing.state === 'completed') {
      return {
        key: key,
        lock: lock,
        state: 'completed',
        record: existing.record
      };
    }

    if (existing && existing.state === 'processing') {
      throw createWebhookError_('IDEMPOTENCY_BUSY', true, 'Chunk is already being processed', {
        run_id: request.runId,
        chunk_index: request.chunkIndex
      });
    }

    var lease = {
      state: 'processing',
      key: key,
      startedAt: nowIso_(),
      expiresAt: new Date(Date.now() + CONFIG.idempotencyLeaseMs).toISOString(),
      runId: request.runId,
      chunkIndex: request.chunkIndex
    };

    writeStoredIdempotencyLease_(key, lease);
    return {
      key: key,
      lock: lock,
      state: 'processing',
      record: lease
    };
  } catch (error) {
    lock.releaseLock();
    throw error;
  }
}

function releaseIdempotencyLease_(lease) {
  if (!lease) {
    return;
  }

  clearStoredIdempotencyLease_(lease.key);

  if (lease.lock) {
    lease.lock.releaseLock();
  }
}

function finalizeIdempotencySuccess_(request, successAck) {
  var key = buildIdempotencyKey_(request);
  var stored = {
    state: 'completed',
    completedAt: nowIso_(),
    record: {
      run_id: request.runId,
      chunk_index: request.chunkIndex,
      rows_received: successAck.rows_received,
      rows_written: successAck.rows_written,
      schema_action: successAck.schema_action,
      added_columns: cloneArray_(successAck.added_columns),
      message: successAck.message
    }
  };

  writeStoredIdempotencyRecord_(key, stored);
  appendIdempotencyLedgerRow_(request, successAck, 'completed');
}

function appendIdempotencyFailure_(request, failureAck) {
  appendIdempotencyLedgerRow_(request, failureAck, 'failed');
}

function buildDuplicateSuccessAck_(request, storedRecord) {
  return {
    ok: true,
    status: 'duplicate',
    run_id: request.runId,
    chunk_index: request.chunkIndex,
    rows_received: request.chunkRows,
    rows_written: 0,
    retryable: false,
    schema_action: storedRecord && storedRecord.schema_action ? storedRecord.schema_action : 'duplicate_replay',
    added_columns: storedRecord && storedRecord.added_columns ? cloneArray_(storedRecord.added_columns) : [],
    message: 'Chunk already processed; duplicate replay skipped'
  };
}

function readStoredIdempotencyRecord_(key) {
  var cache = CacheService.getScriptCache();
  var completedCacheKey = getIdempotencyCompletedKey_(key);
  var leaseCacheKey = getIdempotencyLeaseKey_(key);

  var cached = cache.get(completedCacheKey);
  if (cached) {
    return JSON.parse(cached);
  }

  var properties = PropertiesService.getScriptProperties();
  var completedValue = properties.getProperty(completedCacheKey);
  if (completedValue) {
    cache.put(completedCacheKey, completedValue, CONFIG.idempotencyCacheSeconds);
    return JSON.parse(completedValue);
  }

  var leaseCached = cache.get(leaseCacheKey);
  if (leaseCached) {
    var cachedLease = JSON.parse(leaseCached);
    if (cachedLease && cachedLease.state === 'processing' && !isLeaseExpired_(cachedLease)) {
      return cachedLease;
    }

    clearStoredIdempotencyLease_(key);
  }

  var leaseValue = properties.getProperty(leaseCacheKey);
  if (leaseValue) {
    var persistedLease = JSON.parse(leaseValue);
    if (persistedLease && persistedLease.state === 'processing' && !isLeaseExpired_(persistedLease)) {
      cache.put(leaseCacheKey, leaseValue, CONFIG.idempotencyCacheSeconds);
      return persistedLease;
    }

    clearStoredIdempotencyLease_(key);
  }

  var ledgerRecord = findLedgerRecordByKey_(key);
  if (ledgerRecord) {
    var persisted = {
      state: ledgerRecord.state,
      record: ledgerRecord.record
    };
    if (persisted.state === 'completed') {
      writeStoredIdempotencyRecord_(key, persisted);
    }
    return persisted;
  }

  return null;
}

function writeStoredIdempotencyRecord_(key, storedRecord) {
  var payload = JSON.stringify(storedRecord);
  var properties = PropertiesService.getScriptProperties();
  var cache = CacheService.getScriptCache();

  properties.setProperty(getIdempotencyCompletedKey_(key), payload);
  cache.put(getIdempotencyCompletedKey_(key), payload, CONFIG.idempotencyCacheSeconds);
}

function writeStoredIdempotencyLease_(key, leaseRecord) {
  var payload = JSON.stringify(leaseRecord);
  var properties = PropertiesService.getScriptProperties();
  var cache = CacheService.getScriptCache();

  properties.setProperty(getIdempotencyLeaseKey_(key), payload);
  cache.put(getIdempotencyLeaseKey_(key), payload, CONFIG.idempotencyCacheSeconds);
}

function clearStoredIdempotencyLease_(key) {
  PropertiesService.getScriptProperties().deleteProperty(getIdempotencyLeaseKey_(key));
  CacheService.getScriptCache().remove(getIdempotencyLeaseKey_(key));
}

function getIdempotencyCompletedKey_(key) {
  return key + ':completed';
}

function getIdempotencyLeaseKey_(key) {
  return key + ':lease';
}

function isLeaseExpired_(leaseRecord) {
  if (!leaseRecord || !leaseRecord.expiresAt) {
    return true;
  }

  var expiresAt = new Date(leaseRecord.expiresAt).getTime();
  return isNaN(expiresAt) || expiresAt <= Date.now();
}
