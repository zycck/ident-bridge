# Google Apps Script library backend

Эта папка содержит только код библиотеки Google Apps Script.

Что входит:
- библиотечный backend V2 для `gas-sheet.v2`;
- приём `GET action=ping` и `GET action=sheets`;
- приём `POST` чанков с staging-листом и заменой дневного среза;
- скрытый техстолбец `__ДатаВыгрузки`;
- минимальный `PropertiesService` state и один `LockService`.

Что не входит:
- `doGet` и `doPost` для клиентского проекта таблицы;
- шаблон подключения таблицы.

Шаблон подключения лежит отдельно:
- [resources/gas-shim/shim.gs](../resources/gas-shim/shim.gs)

Идея простая:
1. Эта папка публикуется как библиотека Apps Script.
2. В проекте конкретной таблицы пользователь вставляет код из `resources/gas-shim/shim.gs`.
3. Уже этот проект таблицы содержит `doGet/doPost` и вызывает `iDBBackend.handleRequest(...)`.

Так библиотека остаётся библиотекой и не тащит в себя бессмысленные entrypoint-функции.
