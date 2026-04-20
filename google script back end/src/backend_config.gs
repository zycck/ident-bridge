var BACKEND_V2_CONFIG = Object.freeze({
  apiVersion: '2.0',
  protocolVersion: 'gas-sheet.v2',
  authTokenProperty: 'AUTH_TOKEN',
  runStatePrefix: 'gasv2:run:',
  technicalColumnName: '__\u0414\u0430\u0442\u0430\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0438',
  stagingSheetPrefix: '__stage__',
  pingMessage: 'pong',
  defaultLockTimeoutMs: 2000,
  maxPayloadBytes: 5 * 1024 * 1024,
  maxSheetNameLength: 100,
  staleRunTtlMs: 12 * 60 * 60 * 1000,
});
