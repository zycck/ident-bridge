# GAS Library Shim

Тонкий shim для клиентского Google Apps Script проекта.

Что делает:

- читает `AUTH_TOKEN` и `SHEET_ID` из Script Properties клиента;
- прокидывает их в общий backend library через `handleRequest(event, method, context)`;
- оставляет backend-логику централизованной в library.

Базовый сценарий:

1. Подключить backend library в Apps Script проект клиента.
2. Назвать alias библиотеки `iDBBackend`.
3. Скопировать `shim.gs` в клиентский проект.
4. Добавить Script Properties:
   - `AUTH_TOKEN`
   - `SHEET_ID` (необязательно)

Этот ресурс пакуется в desktop build как reference-артефакт для setup flow.
