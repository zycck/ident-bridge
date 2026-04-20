# GAS Library Shim

Тонкий shim для клиентского Google Apps Script проекта.

Что делает:

- прокидывает `GET` и `POST` в общую backend library через `handleRequest(event, method)`;
- оставляет backend-логику централизованной в library;
- не требует дополнительных свойств скрипта для базового сценария.

Базовый сценарий:

1. Подключить backend library в Apps Script проект клиента.
2. Назвать alias библиотеки `iDBBackend`.
3. Скопировать `shim.gs` в клиентский проект.
4. Опубликовать проект как веб-приложение.

Этот ресурс пакуется в desktop build как reference-артефакт для окна подключения.