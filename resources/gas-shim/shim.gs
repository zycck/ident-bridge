/*
1. Добавьте библиотеку: 1gCHuAaNHvQmelAnG2bLBlCoiuj1EPx0uu8D0e3leBp1XQ6X6sukBm5iu
2. Имя библиотеки: iDBBackend
3. Выберите последнюю версию библиотеки
4. Создайте свойство AUTH_TOKEN
*/

function doGet(e) {
  return iDBBackend.handleRequest(e, 'GET', {
    expectedToken: requiredScriptProperty_('AUTH_TOKEN'),
  });
}

function doPost(e) {
  return iDBBackend.handleRequest(e, 'POST', {
    expectedToken: requiredScriptProperty_('AUTH_TOKEN'),
  });
}

function requiredScriptProperty_(name) {
  const value = PropertiesService.getScriptProperties().getProperty(name);
  const normalized = typeof value === 'string' ? value.trim() : '';
  if (!normalized) {
    throw new Error(`Missing Script Property: ${name}`);
  }
  return normalized;
}
