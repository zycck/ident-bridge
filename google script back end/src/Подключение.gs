/*
Скопируйте этот файл в Apps Script-проект, который будет вызывать библиотеку backend.
*/

function doGet(e) {
  return iDBBackend.handleRequest(e, 'GET', null);
}

function doPost(e) {
  return iDBBackend.handleRequest(e, 'POST', {
    expectedToken: requiredScriptProperty_('AUTH_TOKEN'),
  });
}

function requiredScriptProperty_(name) {
  var value = PropertiesService.getScriptProperties().getProperty(name);
  var normalized = typeof value === 'string' ? value.trim() : '';
  if (!normalized) {
    throw new Error('Missing Script Property: ' + name);
  }
  return normalized;
}
