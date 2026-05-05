/*
1. Добавьте библиотеку: 1gCHuAaNHvQmelAnG2bLBlCoiuj1EPx0uu8D0e3leBp1XQ6X6sukBm5iu
2. Имя библиотеки: iDBBackend
3. Выберите последнюю версию библиотеки
4. Опубликуйте проект как веб-приложение
*/

function doGet(e) {
  return iDBBackend.handleRequest(e, 'GET', idbBackendContext_());
}

function doPost(e) {
  return iDBBackend.handleRequest(e, 'POST', idbBackendContext_());
}

function idbBackendContext_() {
  const properties = PropertiesService.getScriptProperties();
  return {
    properties: {
      getProperty: function(key) {
        return properties.getProperty(key);
      }
    }
  };
}
