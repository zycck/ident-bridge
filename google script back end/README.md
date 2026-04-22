# Google Apps Script library backend

Эта папка содержит только код библиотеки Google Apps Script.

Что входит:
- библиотечный backend V2 для `gas-sheet.v2`;
- приём `GET action=ping` и `GET action=sheets`;
- приём `POST` чанков с прямой записью в основной лист;
- режимы `append`, `replace_all`, `replace_by_date_source`;
- скрытые техстолбцы `__ДатаВыгрузки` и `__idb_source`.

Семантика `POST`:
- `chunk_index == 1`:
  - `append` просто дописывает строки;
  - `replace_all` очищает все строки ниже заголовка и пишет chunk;
  - `replace_by_date_source` удаляет строки по паре `export_date + source_id` и пишет chunk.
- `chunk_index > 1` всегда только дописывает строки.
- `run_id` используется как телеметрия, а не как ключ backend-state.

Успешный ACK:
- `ok: true`
- `status: "accepted"`
- `rows_received`
- `rows_written`
- `retryable`
- `message`
- `api_version`

Backend не хранит состояние запуска и не обещает server-side resumability.

Что не входит:
- `doGet` и `doPost` для клиентского проекта таблицы;
- staging-листы;
- хранение состояния run в `PropertiesService`;
- логика promote, duplicate и stale cleanup;
- шаблон подключения таблицы.

Шаблон подключения лежит отдельно:
- [resources/gas-shim/shim.gs](../resources/gas-shim/shim.gs)

Идея простая:
1. Эта папка публикуется как библиотека Apps Script.
2. В проекте конкретной таблицы пользователь вставляет код из `resources/gas-shim/shim.gs`.
3. Уже этот проект таблицы содержит `doGet/doPost` и вызывает `iDBBackend.handleRequest(...)`.

Так библиотека остаётся библиотекой и не тащит в себя лишние entrypoint-функции.
