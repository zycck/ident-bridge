# Правила для Google Apps Script backend

1. Папка содержит библиотечный backend под Google Apps Script V8.
2. Публичный entrypoint только один: `handleRequest(event, method, context)`.
3. `doGet` и `doPost` в библиотеке запрещены. Они живут только в shim проекта таблицы.
4. Писать на modern GAS V8:
   - `const` по умолчанию;
   - `let` только при реальном reassignment;
   - template literals вместо склейки строк;
   - деструктуризация и стрелки только там, где это реально сокращает код.
5. `var` запрещён.
6. ES modules, Node APIs, browser APIs, private class fields, лишние классы и фабрики запрещены.
7. Один смысл — одна реализация. Нельзя плодить helpers, которые делают одно и то же под разными именами.
8. Нельзя дробить orchestration на микрофункции без прямой пользы для читаемости или тестируемости.
9. Любой вызов `Sheets`, `SpreadsheetApp`, `PropertiesService`, `LockService` считать дорогим.
10. В hot path запрещены:
    - повторный `getDataRange()` одного и того же листа;
    - полное `clearContents() + full rewrite`, кроме явного `replace_all` и редкой миграции схемы;
    - cleanup stale runs в `GET`;
    - reread staging sheet сразу после записи chunk.
11. Единственные write modes:
    - `append`
    - `replace_all`
    - `replace_by_date_source`
12. Single chunk всегда идёт без staging.
13. Multi-chunk всегда идёт через отдельный staging sheet на запуск.
14. Для строк приложения использовать только:
    - `__ДатаВыгрузки`
    - `__idb_source`
15. `__idb_source` хранит стабильный `job_id`, а не общее имя приложения.
16. Перед завершением backend-задачи обязательно проверить:
    - в `src` нет `var`;
    - библиотечный контракт не сломан;
    - нет дублирующих helper-ов;
    - нет лишних full-sheet reads/writes;
    - `ping`, `sheets`, single chunk и multi-chunk проходят тесты;
    - повтор chunk и повтор final chunk остаются идемпотентными.
