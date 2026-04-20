# Practical Backlog Fixes — после переаудита плана Опуса

## Принцип

Этот backlog отсортирован не по исторической драматургии плана Опуса, а по тому, что **реально важно на текущем HEAD**.

Каждый пункт ниже:

- подтверждён текущим кодом;
- имеет понятный эффект;
- может быть реализован отдельной следующей сессией.

## Critical now

### 1. Добавить auth для Google Apps Script backend

**Зачем**

- текущий `doGet/doPost` принимают запросы без собственной проверки токена/ключа;
- если endpoint развернут с широким доступом, это позволяет нежелательные записи и probing.

**Почему сейчас**

- это самый прямой security-gap в новом GAS направлении;
- он важнее library-mode, naming cleanup и modernity-косметики;
- при этом library-mode сохраняется как целевая схема rollout-обновлений для GAS backend и не выкидывается из дорожной карты.

**Примечание по архитектуре**

- Google Apps Script как библиотека остаётся целевой моделью распространения обновлений: thin shim у клиента + общий library backend;
- backlog не ставит под сомнение сам library pattern, а только опускает его ниже базового hardening, без которого rollout-модель небезопасна.

**Файлы**

- `google script back end/src/backend.js`
- `app/export/sinks/google_apps_script.py`
- `app/config.py`
- тесты GAS backend/sink

**Что проверить**

- backend отклоняет запрос без токена;
- sink умеет отправлять auth material;
- существующие happy-path тесты не регрессируют.

### 2. Добавить hash/digest verification в updater

**Зачем**

- сейчас updater доверяет скачанному бинарю по размеру файла, но не по криптографической целостности.

**Почему сейчас**

- это прямой integrity-risk для self-update потока;
- по важности стоит рядом с GAS auth.

**Файлы**

- `app/core/updater.py`
- `app/workers/update_worker.py`
- `tests/test_updater.py`

**Что проверить**

- release metadata с digest обрабатывается;
- digest mismatch останавливает update;
- happy-path загрузка и apply flow остаются рабочими.

### 3. Маскировать traceback перед записью в `errors.log` и clipboard

**Зачем**

- сейчас traceback может унести URL, токены, connection fragments вне обычного logging pipeline.

**Почему сейчас**

- это уже более реальный leak-path, чем старый тезис Опуса про обычные application logs.

**Файлы**

- `app/ui/error_dialog_helpers.py`
- `app/ui/error_dialog.py`
- возможно `app/core/log_sanitizer.py`

**Что проверить**

- traceback сохраняется и копируется в санитизированной форме;
- полезная диагностическая информация не пропадает полностью.

## High next

### 4. Проверять checksum payload на стороне GAS backend

**Зачем**

- checksum сейчас передаётся, но backend-side verify не подтверждён.

**Почему сейчас**

- это естественное продолжение auth/integrity hardening;
- даёт протоколу реальный смысл, а не декоративное поле.

**Файлы**

- `google script back end/src/backend.js`
- `tests/test_google_apps_script_backend_files.py`

**Что проверить**

- mismatch приводит к deterministic error;
- корректный payload остаётся зелёным.

### 5. Довести `database.factory` и DB protocol до production path

**Зачем**

- factory уже существует, но не участвует в сборке реального pipeline;
- это создаёт ложное ощущение завершённой extensibility.

**Почему сейчас**

- это самый важный архитектурный cleanup после security-hardening;
- он закрывает разрыв между декларативной и реальной архитектурой.

**Файлы**

- `app/database/factory.py`
- `app/export/pipeline.py`
- `app/workers/export_worker.py`
- связанные тесты pipeline/factory

**Что проверить**

- export path строит DB client через factory/composition root;
- старые тесты worker/pipeline не ломаются;
- можно подменять backend через controlled injection point.

### 6. Убрать layer leakage: перенести `format_duration_compact` из `ui`

**Зачем**

- `core/export` не должны зависеть от `ui` даже ради маленькой formatter-функции.

**Почему сейчас**

- это дешёвый и чистый архитектурный выигрыш;
- уменьшает связность и укрепляет границы слоёв.

**Файлы**

- `app/ui/formatters.py`
- `app/core/sql_client.py`
- `app/export/pipeline.py`
- возможно новый `app/core/formatters.py` или `app/domain/formatters.py`

**Что проверить**

- импорт-граф больше не тянет `ui` в `core/export`;
- форматирование duration остаётся прежним по тестам.

### 7. Починить lifecycle overlay frame в `ExportGoogleSheetsPanel`

**Зачем**

- `_suggestions_frame` перепривязывается к top-level window и сейчас не имеет явного teardown path.

**Почему сейчас**

- это реальный, пусть и умеренный, lifecycle debt в новом GAS UI;
- проще закрыть сейчас, пока панель ещё свежая.

**Файлы**

- `app/ui/export_google_sheets_panel.py`
- соответствующие source/qt tests

**Что проверить**

- open/close/reopen панели не накапливает orphan overlay;
- popup behaviour не деградирует.

## Medium later

### 8. Пересмотреть full-result export model (`fetchall()` / non-streaming pipeline)

**Зачем**

- export pipeline по-прежнему материализует весь result set целиком;
- это реальный perf/RAM риск на больших выгрузках.

**Почему не выше**

- проблема важная, но требует аккуратного проектирования;
- сначала выгоднее закрыть security/integrity и сделать архитектурный cleanup.

**Файлы**

- `app/core/sql_client.py`
- `app/export/pipeline.py`
- `app/export/sinks/webhook.py`
- `app/export/sinks/google_apps_script.py`

**Что проверить**

- memory profile не ухудшается;
- существующие export semantics и tests остаются стабильны;
- для больших SQL results есть bounded/streaming strategy.

### 9. Снизить churn в dashboard activity rebuild

**Зачем**

- `refresh_dashboard_activity()` перестраивает список целиком после каждого `history_changed`.

**Почему не выше**

- это более мягкий UX/perf issue, чем auth/hash/integrity.

**Файлы**

- `app/ui/dashboard_activity.py`
- `app/ui/main_window_signal_router.py`
- связанные dashboard tests

**Что проверить**

- activity panel обновляется корректно;
- UI churn на repeated export completion уменьшается.

### 10. Разобрать GAS integration на более чёткие boundaries

**Зачем**

- sink и UI-панель Google Sheets уже стали тяжёлыми узлами;
- без границ они будут быстро разрастаться дальше.

**Почему не выше**

- это важнее для maintainability, чем для немедленного safety.

**Файлы**

- `app/export/sinks/google_apps_script.py`
- `app/ui/export_google_sheets_panel.py`

**Что проверить**

- структура стала проще читать;
- не появилось regressions в existing GAS tests.

## Cosmetic / modernity

### 11. Добить `@override` там, где сейчас `# type: ignore[override]`

**Файлы**

- `app/ui/dashboard_widget.py`
- `app/ui/debug_window.py`
- `app/ui/export_jobs_widget.py`
- `app/ui/main_window.py`

**Что проверить**

- type-ignore комментарии можно снять;
- tests остаются зелёными.

### 12. Заменить последний `typing.Callable`

**Файлы**

- `app/export/protocol.py`

**Что проверить**

- сигнатуры и imports не меняют поведение.

### 13. Убрать pytest warning от `TestRunDialog`

**Зачем**

- это уже не абстрактная ловушка, а реальный warning в текущем test run.

**Файлы**

- `app/ui/test_run_dialog.py`
- связанные imports/tests

**Что проверить**

- `python -m pytest -q` идёт без `PytestCollectionWarning`.

### 14. Пересмотреть `build.spec` шумовые legacy элементы

**Файлы**

- `build.spec`

**Что проверить**

- сборка продолжает проходить на текущем pinned stack.

Примеры кандидатов:

- `cipher=block_cipher`
- `block_cipher = None`
- возможно другие лишние skeleton remnants

### 15. Решить судьбу `from __future__ import annotations`

**Комментарий**

- не urgent;
- это вопрос консистентности и позиции команды для Python 3.14+, а не проблема стабильности.

## Suggested implementation order

1. GAS auth
2. updater digest/hash verification
3. traceback sanitization
4. backend checksum verification
5. wire `database.factory` into production path
6. move duration formatter out of `ui`
7. fix Google Sheets overlay lifecycle
8. address full-result export model
9. reduce dashboard activity rebuild churn
10. modernity/cosmetic cleanup

## Default verification bundle for future implementation sessions

Минимум после каждого meaningful batch:

- `python -m pytest -q`
- `python tools/perf_smoke.py --scenario all --cycles 3 --top 8`
- `python -m PyInstaller build.spec --clean --noconfirm`
- smoke run `dist/iDentSync.exe`

Если затронут GAS backend:

- дополнительно прогнать соответствующие backend/sink suites

Если затронут updater:

- отдельно прогнать `tests/test_updater.py`

Если затронут UI lifecycle:

- отдельно прогнать целевые pytest-qt или source-level tests для конкретной панели/виджета
