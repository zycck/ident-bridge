# Технический аудит iDentBridge — итоговый отчёт

## Контекст

Пользователь запросил полный технический аудит проекта. iDentBridge — десктоп-приложение для Windows (PySide6 6.11 + pyodbc 5.3 для MS SQL), ~8.5k строк Python, целевая среда Python 3.14.4, сборка PyInstaller 6.19 single-file. Цель аудита — дать картину по 7 срезам: архитектура, нейминг, утечки, производительность, соответствие Python 3.14, многопоточность, масштабируемость; каждую находку — с файлом, строкой и уровнем серьёзности.

Отчёт собран из трёх параллельных Explore-проходов и дополнительной верификации grep/чтениями. Код не меняли — это диагностика.

## Ре-верификация 2026-04-17 (второй проход)

Проведён повторный аудит четырьмя параллельными Explore-агентами + точечные чтения ключевых файлов. Репозиторий чистый (`git status` пусто), последние коммиты — продолжение плановой чистки:

| Коммит | Эффект на план |
|--------|---------------|
| `fa2beb0 refactor: finish leaf cleanup and export payload path` | **Частично закрывает C3**: в [export_worker.py:33-44](app/workers/export_worker.py:33) выделена `build_webhook_payload()`; двойная аллокация `[list(row) for row in result.rows]` исчезла, теперь просто `"data": result.rows`. `default=str` и отсутствие chunking остаются. Также появился [app/ui/lucide_icon_loader.py](app/ui/lucide_icon_loader.py) (с `@lru_cache(maxsize=128)` — чисто). |
| `8873067 refactor: centralize scheduler value validation` | **Частично закрывает E3/J4**: в [scheduler.py:11, 21-34](app/core/scheduler.py:11) `SUPPORTED_SCHEDULE_MODES` вынесен, добавлена `schedule_value_is_valid()`. Но `_schedule_next` всё ещё if/elif каскад (строки 106-133) — `match` не применён. `Literal[...]` дублируется на строках 46 и 50. |
| `4f9c3e4 perf: bound test dialog query results` | **Новое**: в [sql_client.py:109-138](app/core/sql_client.py:109) появился параметр `max_rows` с `fetchmany`-chunking и флагом `truncated`. Хороший паттерн — стоит применить и в webhook-пути (см. обновлённый C3). |
| `27ebafe test: support clean close smoke runs` | Повышает тестируемость `main_window_lifecycle`. Не меняет находок плана. |
| `853e6f7 refactor: extract export jobs navigation controller` | Новый [export_jobs_navigation_controller.py](app/ui/export_jobs_navigation_controller.py) (44 строки, чист). В [export_jobs_widget.py](app/ui/export_jobs_widget.py) раздутость немного снизилась. |

Повторные grep-счётчики:

- `# -*- coding: utf-8 -*-` — **138** файлов (было 134; +4 новых файла со старой шапкой).
- `from __future__ import annotations` — **0**.
- `Optional[.../Union[...]` — **0**.
- `match ...:` — **0**.
- `typing.Callable` — остался в **1** файле: [app/ui/threading.py:10](app/ui/threading.py:10) (остальные мигрированы на `collections.abc.Callable`). Финишный штрих — 1 строка.
- `app/**/*.py` — **94** (было ~88); `app/ui/*.py` на 1-м уровне — **78**, подпапок внутри `app/ui/` пока нет.
- `@override` — **0**.

**Статус каждой находки (после ре-проверки):**

| № | Статус | Примечание |
|---|--------|-----------|
| C1 (rebuild истории) | Актуальна | [export_history_panel.py:123-138](app/ui/export_history_panel.py:123) не менялся |
| C2 (webhook_url в логах) | **Актуальна** | [export_worker.py:118](app/workers/export_worker.py:118): `_log.info("Выгрузка '%s': %d строк → webhook %s", job_name, result.count, webhook_url)` — полный URL всё ещё пишется. Critical остаётся. |
| C3 (JSON payload) | Частично | Двойная аллокация ушла (fa2beb0). Остаётся `default=str` + отсутствие chunked serialization + отсутствие лимита памяти. Пересмотрен на Medium. |
| C4 (tmp-файл в finally) | Актуальна | [config.py:195-213](app/config.py:195) не менялся |
| C5 (chmod 0o600 на NTFS) | Актуальна | без изменений |
| C6 (repeated connect) | Чисто | Новый [navigation_controller.show_editor](app/ui/export_jobs_navigation_controller.py:26) только переключает индекс стека; переподключений сигналов нет. Снимаем с повестки. |
| C7 (DPAPI LocalFree) | Чисто | Без изменений, код корректен |
| C8 (new_exe в %TEMP%) | Актуальна | [updater.py:98](app/core/updater.py:98) не менялся |
| C9 (urlopen без ssl_context) | **Актуальна** | [export_worker.py:100](app/workers/export_worker.py:100): `urllib.request.urlopen(req, timeout=15)` — без явного контекста |
| D2 (fsync на каждое .update) | Актуальна | 5 call-sites. `main_window_lifecycle.py` сдвинулся с 110 на [124](app/ui/main_window_lifecycle.py:124) |
| D3 (лишний isinstance в sql_client) | Актуальна | [sql_client.py:119-120](app/core/sql_client.py:119) не тронут |
| D6 (двойной импорт QApplication) | Актуальна | [main.py:8, 59](main.py:59) |
| D7 (upx=True) | Актуальна | [build.spec:75](build.spec:75) |
| E1 (`from __future__`) | Актуальна | 0 файлов |
| E2 (`coding: utf-8`) | Актуальна, усилена | **138 файлов** (+4) |
| E3/J4 (match в scheduler) | Частично | Валидация вынесена, но каскад остался |
| E4 (`NotRequired`) | Актуальна | [config.py:51-77](app/config.py:51) `total=False` без изменений |
| E5 (`collections.abc.Callable`) | Почти закрыта | Остался **1** файл: [threading.py:10](app/ui/threading.py:10) — 1-строчный фикс |
| E7 (`@override`) | Актуальна | 0 использований |
| A1 (разбить SettingsSqlController) | Актуальна | 212 строк, 3 flow смешаны |
| A2 (микромодуль dashboard_activity_store) | Актуальна | 16 строк, 1 функция |
| A3 (дубль форматирования ts) | Актуальна | две похожие функции живут |
| A5 (имя `test_run_dialog.py`) | Смягчена | [pytest.ini:3](pytest.ini:3) ограничивает `testpaths = tests`, так что pytest НЕ собирает `app/ui/test_run_dialog.py` сейчас. Риск латентный — если кто-то поменяет testpaths или запустит `pytest app/`, сломается. Остаётся в Low «когнитивный шум + ловушка в будущем». |

**Итог ре-верификации:** плана-задачник актуален на 2026-04-17. C6 снимаем. E5 почти готова (1 строка). C3 и E3 помечены как «частично» — требуют завершения, а не нового анализа. Три коммита (`fa2beb0`, `8873067`, `4f9c3e4`) подтвердили, что проект движется по намеченной траектории.

## A. Архитектура папок и модулей — 7/10

**Сильные стороны.** Границы слоёв соблюдены: `app/core/` не импортирует `app/ui/`, воркеры обращаются к UI только через сигналы, pyodbc изолирован внутри [app/core/sql_client.py](app/core/sql_client.py) и [app/core/instance_scanner.py](app/core/instance_scanner.py), больше нигде не вызывается напрямую. [app/ui/threading.py](app/ui/threading.py) вынес boilerplate moveToThread в единый `run_worker`. ConfigManager централизует dataclass/TypedDict и DPAPI. 8.5k строк → 134 файла — ratio ОК для GUI-приложения.

**Проблемы.**

1. **Перегрузка `app/ui/`.** 70 модулей для одной GUI-панели выглядят как незавершённый расщеплённый рефакторинг. В семействе settings — 9 файлов (`settings_shell`, `settings_widget`, `settings_widget_controller`, `settings_form_controller`, `settings_sql_controller`, `settings_sql_view`, `settings_sql_presenters`, `settings_sql_flow`, `settings_sql_panel`), граница `SettingsWidget` vs `SettingsShell` vs контроллеров неочевидна — см. [app/ui/settings_sql_controller.py](app/ui/settings_sql_controller.py) (самый тяжёлый, ~212 строк, три смешанных flow: scan / list DB / test-connection).
2. **Микро-модуль** [app/ui/dashboard_activity_store.py](app/ui/dashboard_activity_store.py) — 16 строк, одна чистая функция `clear_job_histories`. Такой уровень дробления добавляет шума без пользы: логичнее inline либо в общий `dashboard_helpers`.
3. **Двойное форматирование времени.** [app/ui/export_job_tile_presenter.py](app/ui/export_job_tile_presenter.py) и [app/ui/history_row_presenter.py](app/ui/history_row_presenter.py) имеют свои, почти идентичные, `_format_short_ts` / `format_history_timestamp`. Нужен общий `app/ui/_formatters.py`.
4. **Смешение суффиксов.** `_shell` / `_panel` / `_widget` / `_page` / `_dialog` используются непоследовательно: `ExportEditorShell` и `ExportEditorHeader` оба по сути composite-views, но суффиксы разные; `SqlEditorDialogShell` vs `TestRunDialogShell` — одни зовут shell, другой widget-like. Нужно договорное правило (например: `_shell.py` = компоновка без логики, `_widget.py` = самодостаточный виджет, `_panel.py` = подвиджет внутри shell).
5. **Файл [app/ui/test_run_dialog.py](app/ui/test_run_dialog.py) выглядит как тест** из-за префикса `test_` — чтобы не ломал pytest-discovery, советую `dry_run_dialog.py` или `export_test_dialog.py`.

## B. Нейминг — 7.5/10

**Хорошо.** Модули snake_case, классы PascalCase, константы SCREAMING_SNAKE (см. [app/core/constants.py](app/core/constants.py) — аккуратная централизация таймингов/лимитов/размеров). TypedDict и dataclass разделены комментарными блоками. pyodbc / winreg / ctypes замещены безопасными сентинелями (`pyodbc = None` + ошибка импорта хранится, см. `_PYODBC_IMPORT_ERROR` в трёх местах).

**Плохо.**

1. **`SettingsWidgetController` vs `SettingsFormController` vs `SettingsSqlController` vs `SettingsAppController`** — четыре разных контроллера в одном модуле-семействе, без единого верхнеуровневого contract-документа. Легко путать.
2. **`Bridge` vs `Runtime` vs `Controller`** — [export_job_editor_bridge.py](app/ui/export_job_editor_bridge.py) (services-layer), [export_editor_runtime.py](app/ui/export_editor_runtime.py) (state machine), [export_editor_controller.py](app/ui/export_editor_controller.py) (lifecycle). Нет глоссария; новичку предстоит разобрать каждый.
3. **`EXE_NAME = LEGACY_RUNTIME_NAME = "iDentSync"`** ([constants.py:38-40](app/core/constants.py:38)) — артефакт старого бренда, задокументирован, но сама константа называется `LEGACY_RUNTIME_NAME` и одновременно используется как текущее имя exe и каталога конфига. Имя вводит в заблуждение.

## C. Утечки и ресурсы

| # | Место | Уровень | Суть |
|---|------|---------|------|
| C1 | [app/ui/export_history_panel.py:123-138](app/ui/export_history_panel.py:123) | **High** | `_rebuild()` на каждый prepend/delete разрушает и пересоздаёт все `HistoryRow` с новыми `delete_requested`-сигналами. При HISTORY_MAX=50 и частых выгрузках это поток `deleteLater` + реконнект слотов. Нужен инкрементальный `prepend_row` / `remove_row_at`. |
| C2 | [app/workers/export_worker.py:76-108](app/workers/export_worker.py:76) | **High** | Логируется полный `webhook_url` с query-string (строка 109) — если URL содержит токен (Slack/Discord/n8n style), он попадёт в Qt-лог-буфер и ring-buffer логгера. Нужно логировать только origin/path без query. |
| C3 | [app/workers/export_worker.py:76-81](app/workers/export_worker.py:76) | Medium | `[list(row) for row in result.rows]` + `json.dumps(..., default=str)` при `MAX_WEBHOOK_ROWS=50 000` (см. [constants.py:46](app/core/constants.py:46)) — двойная аллокация и медленный fallback через `repr`. Лучше custom `JSONEncoder` с явной обработкой `datetime/Decimal/bytes` + итеративная сериализация. |
| C4 | [app/config.py:195-213](app/config.py:195) | Medium | В `save()` файл переименовывается через `os.replace(tmp, CONFIG_PATH)`, но `finally` всё равно пытается удалить `tmp_path`: после успешного `replace` файла уже нет → `exists()` даёт False → unlink пропускается. ОК, но логика противоречит инварианту «tmp существует до replace». Safe-guard стоит оформить явно (`tmp_replaced = False`). |
| C5 | [app/config.py:216-219](app/config.py:216) | Low | `os.chmod(…, 0o600)` на Windows NTFS — no-op. Для реальной защиты нужен `SetNamedSecurityInfo` через ACL, иначе конфиг с DPAPI-шифрованными полями всё равно читаем любому процессу текущего пользователя (DPAPI сам по себе это и делает). |
| C6 | [app/ui/export_jobs_widget.py](app/ui/export_jobs_widget.py) + [export_jobs_pages.py](app/ui/export_jobs_pages.py) | Medium | При повторном `show_editor(job_id)` редактор переиспользуется через кэш `dict[str, QScrollArea]`. Нужно проверить, не накапливаются ли подключения сигналов `changed` / `run_requested` — характерный PySide6-анти-паттерн. |
| C7 | [app/core/dpapi.py:85-118](app/core/dpapi.py:85) | OK | `LocalFree` для `pbData` и `desc_ptr` в `finally` — корректно. Ctypes-ресурсы не текут. |
| C8 | [app/core/updater.py:96-113](app/core/updater.py:96) | Medium | `apply_downloaded_update` запускает `cmd.exe` со скриптом в `os.path.dirname(exe_path)`: отлично для TOCTOU защиты, но `new_exe` лежит в `tempfile.gettempdir()` (строка 98) — мировая директория. Атакующий с правом записи в %TEMP% мог бы подменить `_new.exe` между `download_update` и `apply_downloaded_update`. Минимум — переместить `new_exe` в `os.path.dirname(exe_path)` и хэшировать (GitHub Release asset хэша пока нет). |
| C9 | [app/workers/export_worker.py:91](app/workers/export_worker.py:91) | Low | `urllib.request.urlopen(req, timeout=15)` без явного `ssl_context` — фактически использует дефолт. В `updater.py` ssl-context создаётся явно (`ssl.create_default_context()`). Для консистентности и контроля (pinning, cert-пакет в PyInstaller) стоит унифицировать. |

**Log-хостинг.** [app/core/app_logger.py](app/core/app_logger.py) хранит `LOG_RING_BUFFER=500` строк в памяти — ОК. Но к этому буферу пишет webhook_url (см. C2) — утечка попадает туда же.

## D. Производительность

| # | Место | Уровень | Суть |
|---|------|---------|------|
| D1 | C1 выше | High | Полный rebuild истории. |
| D2 | [app/config.py:221-226](app/config.py:221) | Medium | `update(**changes)` → `load()` (с диска, пере-расшифровкой DPAPI) → merge → `save()` (tempfile + fsync + os.replace). 5 call-sites: [main_window_lifecycle.py:110](app/ui/main_window_lifecycle.py:110), [settings_form_controller.py:105](app/ui/settings_form_controller.py:105), [export_jobs_store.py:36](app/ui/export_jobs_store.py:36), [settings_form_controller.py:95](app/ui/settings_form_controller.py:95), [dashboard_activity_panel.py:116](app/ui/dashboard_activity_panel.py:116). Почти везде — от debounced UI-событий, так что трафик на диск умеренный, но DPAPI-цикл + fsync на каждое обновление расточителен. Варианты: batch-flush по таймеру (например, `CoalescingConfigWriter`), или `dirty_keys` с write-back только при закрытии. |
| D3 | [app/core/sql_client.py:113-118](app/core/sql_client.py:113) | Low | `if not isinstance(rows, list): rows = list(rows)` — pyodbc всегда возвращает `list`, предохранитель безопасен, но читатель путается. Можно заменить комментом или убрать — pyodbc API стабилен. |
| D4 | [app/core/instance_scanner.py:104-116](app/core/instance_scanner.py:104) | Low | `scan_all` делает `scan_local + scan_network` последовательно. `scan_network` может висеть до 3 с. При UI-cold-start это потенциально раздражает; можно параллелить (QThread или concurrent.futures), но сейчас уже в отдельном worker → приемлемо. |
| D5 | [app/ui/sql_highlighter.py](app/ui/sql_highlighter.py) / sqlglot | Low | sqlglot — тяжёлая библиотека. Проверь, что она не импортируется на главном пути старта (ленивая загрузка). В perf-baseline она в топе retained — ожидаемо. |
| D6 | [main.py:32, 59](main.py:32) | Low | Два `from PySide6.QtWidgets import QApplication` — один на модульном уровне, второй внутри `_load_fonts`. Избыточно. Также `_load_fonts()` вызывается после `QApplication(sys.argv)`, но использует `QApplication.instance()` — можно передать `app` аргументом. |
| D7 | [build.spec:75](build.spec:75) | Medium | `upx=True` + `onefile=True` — классический триггер ложного срабатывания Windows Defender / SmartScreen. Для 3.14 + PyInstaller 6.19 это часто приводит к VirusTotal red flags. Советую `upx=False` и подпись сертификатом (codesign_identity пусто). |

**Где выгоды нет (проверено, но чисто).** Scheduler — QTimer + singleShot, без busy-loops. App_logger — правильный ring-buffer (`collections.deque(maxlen=…)`). SqlClient retry — exponential backoff с jitter, корректный паттерн. `_pick_download_url` — two-pass, O(n), ок.

## E. Соответствие Python 3.14 — 7.5/10

**Уже правильно.** `list/dict/tuple`-генерики (0 мест со старым `List/Dict/Tuple`), `X | None` вместо `Optional` (0 мест с `Optional[…]`/`Union[…]`), `@dataclass(slots=True)` в [config.py:24-45](app/config.py:24), `collections.abc.Callable` в [threading.py](app/ui/threading.py) (заметьте: там же остался `typing.Callable` — нужно добить, файл смешанный). TypedDict с `total=False` — работает, но менее точно, чем `NotRequired[...]`.

**Упущено.**

1. **`from __future__ import annotations` — 0 файлов.** При `X | None` и forward-ссылках это всё равно работает (PEP 604 активен с 3.10), но для устойчивости к сложным типам и форвард-рефам-в-сигнатурах `future annotations` экономит время парсера и предотвращает `NameError` в типовых хинтах. Рекомендую добавить шапкой во все `app/**/*.py` (с учётом `main.py`).
2. **134 файла с `# -*- coding: utf-8 -*-`.** Совершенно не нужно с Python 3+ (дефолт UTF-8). Агент изначально сказал 67 — я проверил grep'ом: **реально 134** (включая тесты и `build.spec`). Массовое удаление = -134 строки шума.
3. **`scheduler._schedule_next` — каскад if/elif по `mode`** ([scheduler.py:85-114](app/core/scheduler.py:85)). Идеальный кандидат на `match self._mode: case "daily": …`. Заодно решит exhaustiveness (сейчас `_SUPPORTED_MODES` дублируется и в `Literal`, и в кортеже — см. [scheduler.py:10 и 29](app/core/scheduler.py:10)).
4. **`TypedDict(total=False)`** в `AppConfig`/`ExportJob` — лучше `NotRequired[T]` по каждому полю. Даёт IDE и mypy точечную проверку обязательности.
5. **`typing.Callable`** в [app/ui/threading.py:10](app/ui/threading.py:10), [error_dialog_controller.py](app/ui/error_dialog_controller.py), [main_window_bootstrap.py](app/ui/main_window_bootstrap.py) — мигрировать на `collections.abc.Callable` (уже частично начато).
6. **`Any`** в сигнатурах 6 файлов (`error_dialog_controller.py`, `export_execution_controller.py`, `export_jobs_collection_controller.py`, `export_job_editor_bridge.py`, `main_window_bootstrap.py`). Замена на более узкие типы (Protocol, TypeVar, или TypedDict) повысит безопасность.
7. **Нет `typing.override`** (3.12+) на переопределённых методах (`run`, `check`). Добавить косметически, mypy ловит лишнее ренейминг.
8. **PyInstaller 6.19 + Python 3.14.** PySide6 6.11 официально поддерживает Python ≤3.13; 3.14 пока неофициально. Стоит завести smoke-test в CI, проверяющий импорт всех модулей на 3.14.

## F. Многопоточность — 9/10

Корректная модель: QThread + `moveToThread`, сигналы кросс-тредовые через `QueuedConnection` (дефолт). `SqlClient` явно помечен как per-thread и создаётся внутри worker.run() ([export_worker.py:51](app/workers/export_worker.py:51)). ConfigManager защищён RLock-ом. pyodbc и urllib в C-extensions освобождают GIL, UI не фризит. `time.sleep` в UI-треде не найдено.

**Что поправить.**

1. **Worker читает `base_cfg` по ссылке** ([export_worker.py:45](app/workers/export_worker.py:45)). Сейчас не мутирует, но нет гарантии. Безопаснее передать snapshot `dict(base_cfg)` в конструкторе или задокументировать контракт.
2. **`run_worker` + `connect_signals`**: документ обещает окно для поздних connect'ов ([threading.py:46-50](app/ui/threading.py:46)), но `QTimer.singleShot(0, thread.start)` не даёт гарантии — если событийная петля занята, таймер может выстрелить раньше пользовательских connect'ов. Рекомендую всегда использовать `connect_signals` колбэк для критических сигналов, а про «окно» снять формулировку.
3. **FAST_TRIGGER режим** ([scheduler.py:41-59](app/core/scheduler.py:41)) переключает `setSingleShot(False)` и заменяет слот, но не хранит состояние → повторный `start()` без `FAST_TRIGGER` использует `try/except TypeError` на `disconnect()`. Работает, но хрупко. Стоит вынести в явный `_switch_mode(fast: bool)`.
4. **Free-threaded Python (PEP 779).** Готовность ~80%: блокировки есть, GIL-зависимых паттернов не видно. Но ConfigManager не документирует модель для читателей. Один-два комментария «safe under no-GIL when callers respect RLock» — и готово.

## G. Масштабируемость и поддержка

**Сильные места.** Воркеры унифицированы через `run_worker`. Сигналы — единственный канал UI↔worker. Константы централизованы. PyInstaller spec сгруппирован.

**Риски.**

1. **Только webhook-бэкенд экспорта.** [export_worker.py](app/workers/export_worker.py) хардкодит POST JSON. Добавление S3/Kafka/email потребует либо ветвления, либо redesign. Предлагаю `ExportSink` Protocol с реализациями `WebhookSink`, `S3Sink`, регистрацию через фабрику.
2. **Только MS SQL.** [sql_client.py](app/core/sql_client.py), [connection.py](app/core/connection.py), [odbc_utils.py](app/core/odbc_utils.py), [instance_scanner.py](app/core/instance_scanner.py) явно завязаны на pyodbc + ODBC + TrustServerCertificate + registry-скан. Если однажды понадобится PostgreSQL — понадобится `DatabaseClient` Protocol (`connect/query/test_connection`) с MSSQL-реализацией сейчас.
3. **Отсутствует Dependency Injection** для тестов. Тесты есть ([tests/test_export_worker.py](tests/test_export_worker.py) и т.д.), но DI делается аргументами конструктора с дефолтами (см. [ExportJobEditorBridge](app/ui/export_job_editor_bridge.py:16-23)). Масштабируемо, но хрупко — при росте стоит завести `AppContext` / `ServiceLocator`.
4. **Миграция `iDentSync → iDentBridge`.** Названия файлов, exe, dir — вперемешку. Завершить ребрендинг имеет смысл одним коммитом + миграционным хелпером для существующих %APPDATA%\iDentSync\config.json.

## H. Приоритизированный action-list

**Critical (сделать сейчас).**
- Санитизация `webhook_url` в логах — C2.

**High (в ближайший спринт).**
- Инкрементальное обновление истории, C1.
- Потоковая сериализация / чанкование webhook payload, C3.
- Унификация ssl_context в [export_worker.py](app/workers/export_worker.py) и [updater.py](app/core/updater.py), C9.
- `upx=False` в [build.spec](build.spec:75) + план по codesign, D7.

**Medium (в месяц).**
- Батч-flush ConfigManager, D2.
- Переместить downloaded exe в каталог текущего exe, C8.
- Добить смешанные `typing.Callable` → `collections.abc.Callable`, E5.
- `match` в [scheduler._schedule_next](app/core/scheduler.py:81), E3.
- Разбить `SettingsSqlController` на scan/list/test, A-1.
- Дедуп `format_short_ts` / `format_history_timestamp`, A-3.
- Завершить `iDentSync → iDentBridge` migration, B-3.

**Low (когда пойдёт плановая уборка).**
- Удалить 134 × `# -*- coding: utf-8 -*-`, E2.
- Добавить `from __future__ import annotations`, E1.
- `NotRequired[...]` в TypedDict, E4.
- `@override` на `run/check`, E7.
- Merge `dashboard_activity_store.py` в `dashboard_helpers`, A-2.
- Переименовать `test_run_dialog.py`, A-5.
- Safe-guard в `ConfigManager.save` finally, C4.
- ACL-защита config.json, C5.
- Smoke-тест PySide6 6.11 + Python 3.14, E8.

## Критичные файлы (референс для последующих правок)

- [main.py](main.py), [app/config.py](app/config.py)
- [app/core/scheduler.py](app/core/scheduler.py), [sql_client.py](app/core/sql_client.py), [connection.py](app/core/connection.py), [updater.py](app/core/updater.py), [dpapi.py](app/core/dpapi.py), [app_logger.py](app/core/app_logger.py), [constants.py](app/core/constants.py), [instance_scanner.py](app/core/instance_scanner.py), [odbc_utils.py](app/core/odbc_utils.py), [startup.py](app/core/startup.py)
- [app/workers/export_worker.py](app/workers/export_worker.py), [update_worker.py](app/workers/update_worker.py)
- [app/ui/threading.py](app/ui/threading.py), [export_history_panel.py](app/ui/export_history_panel.py), [settings_sql_controller.py](app/ui/settings_sql_controller.py), [export_jobs_widget.py](app/ui/export_jobs_widget.py), [export_jobs_pages.py](app/ui/export_jobs_pages.py), [dashboard_activity_store.py](app/ui/dashboard_activity_store.py)
- [build.spec](build.spec)

## Верификация (после правок)

- `pytest` (в `tests/` есть широкое покрытие, включая `test_perf_smoke.py`).
- `python tools/perf_smoke.py --scenario all --cycles 5` — сравнить `positive_retained_kib` с baseline 2400.5 KiB из [docs/PERFORMANCE.md](docs/PERFORMANCE.md).
- Ручная проверка: построить через `pyinstaller build.spec`, запустить на чистой Windows 11 VM, выгрузить 50k строк, проверить отсутствие утечки хэндлов (`Process Explorer` / handle count) и RAM.
- Секьюрити-чек логов: убедиться, что полный webhook_url не появляется в `QtLogHandler.history`.

## I. Предлагаемая целевая структура папок

### Текущая (проблема)

```
app/
├── __init__.py
├── config.py                        ← dataclasses + TypedDicts + ConfigManager в одном файле
├── core/                            ← 10 разнородных модулей в плоском виде
│   ├── app_logger.py
│   ├── connection.py
│   ├── constants.py
│   ├── dpapi.py
│   ├── instance_scanner.py
│   ├── odbc_utils.py
│   ├── scheduler.py
│   ├── sql_client.py
│   ├── startup.py
│   └── updater.py
├── workers/                         ← воркеры-сироты, тесно привязаны к core+UI
│   ├── export_worker.py
│   └── update_worker.py
└── ui/                              ← 70 файлов плоско
    ├── dashboard_*.py  (7 файлов)
    ├── export_editor_*.py (5)
    ├── export_jobs_*.py (5)
    ├── export_job_*.py (4)
    ├── export_history_panel.py
    ├── export_schedule_panel.py
    ├── export_sql*.py (2)
    ├── history_row*.py (2)
    ├── main_window_*.py (9)
    ├── settings_*.py (12)
    ├── settings_sql_*.py (5)
    ├── sql_editor*.py (4)
    ├── sql_highlight*.py + sql_highlighter.py
    ├── test_run_dialog*.py (3)
    ├── title_bar*.py (3)
    ├── debug_window*.py (3)
    ├── error_dialog*.py (3)
    ├── update_flow_coordinator.py
    ├── theme.py, widgets.py, threading.py, lucide_icons.py, icons_rc.py
    └── ...
```

Проблема: в `app/ui/` «всё вперемешку», семейства приходится вычислять префиксами. Навигация IDE-зависимая, у новичков рост кривой обучения.

### Целевая (рекомендуемая)

```
app/
├── __init__.py
├── bootstrap.py                       ← main() + load_fonts/icon/theme (из main.py)
├── domain/                            ← чистые типы данных, без Qt, без pyodbc
│   ├── __init__.py
│   ├── config_types.py                ← AppConfig, ExportJob, ExportHistoryEntry, TriggerType
│   ├── results.py                     ← QueryResult, SyncResult, SqlInstance, ResourceSample
│   └── constants.py                   ← из core/constants.py
├── platform/                          ← Windows-specific тонкие обёртки
│   ├── __init__.py
│   ├── dpapi.py                       ← без изменений
│   ├── startup.py                     ← autostart registry
│   ├── resource_monitor.py            ← НОВЫЙ: CPU/RAM/handles (psutil)
│   └── updater/
│       ├── __init__.py
│       ├── github_release.py          ← check_latest, _pick_download_url, is_newer
│       ├── download.py                ← download_update
│       └── apply.py                   ← apply_downloaded_update, cleanup_old_exe
├── database/                          ← замена app/core/sql_client + connection + odbc
│   ├── __init__.py
│   ├── protocol.py                    ← DatabaseClient Protocol (connect, query, test_connection)
│   ├── mssql/
│   │   ├── __init__.py
│   │   ├── client.py                  ← MssqlClient (pyodbc-based)
│   │   ├── connection.py              ← build_sql_connection_string
│   │   ├── odbc_utils.py              ← best_driver, _CANDIDATES
│   │   └── scanner.py                 ← scan_local, scan_network, list_databases
│   └── factory.py                     ← DatabaseClientFactory.create("mssql") — точка расширения
├── export/                            ← sinks + pipeline
│   ├── __init__.py
│   ├── protocol.py                    ← ExportSink Protocol
│   ├── sinks/
│   │   ├── __init__.py
│   │   └── webhook.py                 ← WebhookSink (POST JSON)
│   ├── pipeline.py                    ← ExportPipeline (SQL → sink → history)
│   └── worker.py                      ← ExportWorker (QObject), использует pipeline
├── update_flow/                       ← из app/workers/update_worker.py + update_flow_coordinator
│   ├── __init__.py
│   ├── check_worker.py
│   ├── download_worker.py
│   ├── apply_worker.py
│   └── coordinator.py
├── scheduling/
│   ├── __init__.py
│   └── scheduler.py                   ← SyncScheduler + match-based dispatch
├── config/
│   ├── __init__.py
│   ├── manager.py                     ← ConfigManager с batch/commit API
│   ├── migrations.py                  ← auto→scheduled + будущие миграции
│   └── paths.py                       ← _default_config_dir, CONFIG_PATH
├── logging/
│   ├── __init__.py
│   ├── qt_handler.py                  ← QtLogHandler из core/app_logger
│   └── sanitizer.py                   ← НОВЫЙ: SecretFilter (webhook_url, SQL creds)
└── ui/                                ← перекладка по фича-пакетам
    ├── __init__.py
    ├── app_window/                    ← ex main_window_*
    │   ├── shell.py, bootstrap.py, lifecycle.py, navigation.py,
    │   ├── chrome.py, pages.py, debug.py, signal_router.py
    │   └── window.py
    ├── dashboard/                     ← ex dashboard_*
    │   ├── shell.py, widget.py, status_cards.py, update_banner.py,
    │   ├── activity_panel.py, activity_store.py, ping_coordinator.py, ping_timer.py
    │   └── activity.py
    ├── export_jobs/                   ← ex export_jobs_*, export_job_*, history_row_*
    │   ├── widget.py, pages.py, store.py
    │   ├── collection_controller.py, delete_controller.py
    │   ├── job_tile.py, job_tile_presenter.py
    │   ├── history_row.py, history_row_presenter.py
    │   └── history_panel.py
    ├── export_editor/                 ← ex export_editor_*, export_job_editor*, test_run_dialog*, export_sql*
    │   ├── shell.py, controller.py, runtime.py, header.py
    │   ├── execution_controller.py, editor_bridge.py
    │   ├── sql_panel.py, schedule_panel.py
    │   ├── job_editor.py
    │   ├── sql_preview.py             ← ex export_sql.py (переименовать)
    │   └── test_run_dialog/           ← ex test_run_dialog*
    │       ├── dialog.py              ← ex test_run_dialog.py (уйдёт из test_-префикса)
    │       ├── controller.py, shell.py
    ├── settings/                      ← ex settings_* + settings_sql_*
    │   ├── shell.py, widget.py, widget_controller.py, form_controller.py
    │   ├── app_panel.py, app_controller.py
    │   ├── actions.py, persistence.py, workers.py
    │   └── sql/
    │       ├── panel.py, view.py, flow.py, presenters.py
    │       └── controllers/
    │           ├── scan.py            ← разбиение SettingsSqlController
    │           ├── list_db.py
    │           └── test_connection.py
    ├── sql_editor/                    ← ex sql_editor*, sql_highlight*, sql_highlighter
    │   ├── editor.py, controller.py, dialog_shell.py
    │   ├── highlighter.py
    │   └── highlight_helpers.py
    ├── dialogs/
    │   ├── error_dialog.py, error_dialog_controller.py, error_dialog_helpers.py
    │   └── debug_window/
    │       ├── window.py, log_controller.py, formatting.py
    │       └── resource_monitor_bar.py ← НОВЫЙ: CPU/RAM/handles footer
    ├── title_bar/
    │   └── bar.py, controller.py, helpers.py
    └── common/                         ← общее для всех UI-пакетов
        ├── theme.py, widgets.py, threading.py
        ├── icons/
        │   ├── lucide.py, qt_resources.py (ex icons_rc.py)
        └── formatters.py               ← НОВЫЙ: format_relative_timestamp, format_short_ts
```

**Миграционная карта** (показаны только ключевые переезды, остальное очевидно из префикса → папка):

| Сейчас | Станет |
|--------|--------|
| `app/config.py` | `app/domain/config_types.py` + `app/config/manager.py` + `app/config/paths.py` + `app/config/migrations.py` |
| `app/core/constants.py` | `app/domain/constants.py` |
| `app/core/sql_client.py` + `connection.py` + `odbc_utils.py` + `instance_scanner.py` | `app/database/mssql/*` + `app/database/protocol.py` + `app/database/factory.py` |
| `app/core/updater.py` | `app/platform/updater/{github_release,download,apply}.py` |
| `app/workers/export_worker.py` | `app/export/worker.py` + `app/export/pipeline.py` + `app/export/sinks/webhook.py` + `app/export/protocol.py` |
| `app/workers/update_worker.py` | `app/update_flow/{check_worker,download_worker,apply_worker}.py` |
| `app/ui/update_flow_coordinator.py` | `app/update_flow/coordinator.py` |
| `app/core/scheduler.py` | `app/scheduling/scheduler.py` |
| `app/core/dpapi.py` / `startup.py` | `app/platform/{dpapi,startup}.py` |
| `app/core/app_logger.py` | `app/logging/qt_handler.py` + `app/logging/sanitizer.py` (НОВЫЙ) |
| `main.py` (функции `_load_*`) | `app/bootstrap.py`; `main.py` остаётся тонким `python -m` wrapper'ом |
| `app/ui/*.py` (70 плоских) | фича-пакеты `app/ui/<feature>/` |

**Выгода.** Новому разработчику: «ищешь код dashboard — открываешь `app/ui/dashboard/`, готово». Навигация без опоры на IDE-поиск. Явные точки расширения: добавить Kafka-sink = новый файл в `app/export/sinks/`; добавить PostgreSQL = новый пакет в `app/database/postgres/`.

**Риски миграции.** Много import-путей меняется одновременно. Безопасный подход: два коммита — (1) создать новые пути-обёртки с re-exports из старых (shim-файлы), (2) перевести импорты и удалить shim'ы. Тестовая база ([tests/](tests)) покроет 80% регрессий автоматически.

## J. Конкретные API-правки по файлам

Ниже — каждая позиция из H-списка, переведённая в конкретное предложение кода. Код-фрагменты — скетч, не production.

### J1. ConfigManager: батч-commit (решает D2)

`app/config/manager.py` (ex `app/config.py`):

```python
class ConfigManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cfg: AppConfig = {}
        self._dirty: bool = False
        self._pending_flush: threading.Timer | None = None
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_PATH.exists():
            self._cfg = self.load()

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Собрать несколько update() в один fsync."""
        with self._lock:
            self._batching = True
            try:
                yield
            finally:
                self._batching = False
                if self._dirty:
                    self._flush_now()

    def update(self, **changes: object) -> None:
        with self._lock:
            self._cfg.update(changes)  # type: ignore[typeddict-item]
            self._dirty = True
            if not getattr(self, "_batching", False):
                self._schedule_flush(delay_ms=200)

    def _schedule_flush(self, delay_ms: int) -> None:
        if self._pending_flush is not None:
            self._pending_flush.cancel()
        self._pending_flush = threading.Timer(
            delay_ms / 1000, self._flush_now,
        )
        self._pending_flush.daemon = True
        self._pending_flush.start()

    def _flush_now(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            self.save(self._cfg)  # существующая atomic-запись
            self._dirty = False
```

Call-site изменения — минимальны: большинство мест продолжают вызывать `config.update(...)`. Там, где точно идёт серия изменений (например, пересохранение всего settings-экрана), оборачиваем в `with config.batch(): ...`.

**Оценка:** до — 1 fsync на каждое `.update()`, после — 1 fsync на пакет (или через 200 мс debounce).

### J2. ExportSink Protocol + WebhookSink (решает G-1, C3)

`app/export/protocol.py`:

```python
from typing import Protocol
from app.domain.results import QueryResult

class ExportSink(Protocol):
    name: str                                  # "webhook", "s3", "kafka"
    def push(self, job_name: str, result: QueryResult) -> None: ...
```

`app/export/sinks/webhook.py`:

```python
class WebhookSink:
    name = "webhook"

    def __init__(self, url: str, *, max_rows: int = MAX_WEBHOOK_ROWS,
                 retries: int = 3, base_delay: float = 2.0,
                 ssl_context: ssl.SSLContext | None = None,
                 timeout: float = 15.0) -> None:
        self._url = url
        self._max_rows = max_rows
        self._retries = retries
        self._base_delay = base_delay
        self._ssl = ssl_context or ssl.create_default_context()
        self._timeout = timeout

    def push(self, job_name: str, result: QueryResult) -> None:
        if result.count > self._max_rows:
            raise ValueError(f"Слишком много строк ({result.count} > {self._max_rows})")
        payload = self._serialize(job_name, result)
        self._post_with_retries(payload)

    def _serialize(self, job_name: str, result: QueryResult) -> bytes:
        # Итеративный writer: избежать двойной аллокации
        # Используем orjson (если доступен) или custom JSONEncoder
        encoder = _SqlJSONEncoder(ensure_ascii=False)
        return encoder.encode({
            "job": job_name, "rows": result.count,
            "columns": result.columns, "data": result.rows,
        }).encode("utf-8")
```

`app/export/pipeline.py`:

```python
@dataclass(slots=True)
class ExportPipeline:
    db: DatabaseClient
    sink: ExportSink | None
    logger: logging.Logger

    def run(self, job: ExportJob, progress: ProgressCallback) -> SyncResult:
        progress(0, "Подключение к БД...")
        self.db.connect()
        try:
            progress(1, "Выполнение запроса...")
            result = self.db.query(job["sql_query"].strip())
            progress(2, "Отправка данных...")
            if self.sink:
                self.sink.push(job["name"], result)
            progress(3, "Готово")
            return SyncResult(success=True, rows_synced=result.count,
                              error=None, timestamp=datetime.now(timezone.utc))
        finally:
            self.db.disconnect()
```

`app/export/worker.py` становится тонкой QObject-обёрткой:

```python
class ExportWorker(QObject):
    progress: Signal = Signal(int, str)
    finished: Signal = Signal(object)
    error: Signal = Signal(str)

    def __init__(self, pipeline: ExportPipeline, job: ExportJob) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._job = job

    @Slot()
    def run(self) -> None:
        try:
            result = self._pipeline.run(self._job, self.progress.emit)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit(SyncResult(success=False, ...))
```

**Выгода:** воркер перестаёт зависеть от `pyodbc`/`urllib`; добавить S3Sink = 1 файл; тесты pipeline'а пишутся с `FakeDb + InMemorySink`.

### J3. SecretFilter для логов (решает C2)

`app/logging/sanitizer.py`:

```python
class SecretFilter(logging.Filter):
    """Маскирует webhook-URL-ы и SQL credentials в сообщениях логов."""

    _URL_RE = re.compile(r"https?://[^\s]+")
    _PWD_RE = re.compile(r"(PWD=)[^;]+", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._mask(a) for a in record.args)
        record.msg = self._mask(record.msg)
        return True

    @classmethod
    def _mask(cls, value):
        if not isinstance(value, str):
            return value
        value = cls._URL_RE.sub(cls._mask_url, value)
        value = cls._PWD_RE.sub(r"\1***", value)
        return value

    @staticmethod
    def _mask_url(m: re.Match) -> str:
        url = m.group(0)
        parsed = urllib.parse.urlsplit(url)
        # Показываем схему+host+path, обрезаем query (там токены)
        safe = urllib.parse.urlunsplit((
            parsed.scheme, parsed.netloc, parsed.path, "", ""
        ))
        return f"{safe}?***" if parsed.query else safe
```

Подключается в `app/logging/qt_handler.py:setup`:

```python
root.addFilter(SecretFilter())
```

**Тест:** «webhook https://hooks.slack.com/services/T123/B456/XYZ» → «webhook https://hooks.slack.com/services/T123/B456/XYZ» уже мало (содержит secret-path), но query/PWD — точно скрываются. Дополнительно можно внести regex для путей `/services/*/*/[A-Za-z0-9]{20,}` — опционально.

### J4. Scheduler: `match` + единый источник режимов (решает E3, F3)

`app/scheduling/scheduler.py`:

```python
from enum import StrEnum

class ScheduleMode(StrEnum):
    DAILY = "daily"
    HOURLY = "hourly"
    MINUTELY = "minutely"
    SECONDLY = "secondly"

class SyncScheduler(QObject):
    # ...
    def configure(self, mode: ScheduleMode, value: str) -> None:
        self._mode = mode  # type-checker гарантирует валидность
        self._value = value

    def _compute_delay(self, now: datetime) -> float:
        match self._mode:
            case ScheduleMode.SECONDLY:
                n = int(self._value); return float(n) if n >= 1 else 0
            case ScheduleMode.MINUTELY:
                n = int(self._value); return n * 60.0 if n >= 1 else 0
            case ScheduleMode.HOURLY:
                n = int(self._value); return n * 3600.0 if n >= 1 else 0
            case ScheduleMode.DAILY:
                hour, minute = map(int, self._value.split(":"))
                candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if candidate <= now:
                    candidate += timedelta(days=1)
                return (candidate - now).total_seconds()
```

**Выгода:** `Literal` + tuple слились в StrEnum; pattern matching exhaustive; новый режим = одна `case` ветка.

Также **FAST_TRIGGER** выделяется в отдельный метод `_start_fast_trigger(seconds: int)`, основной `start()` — в `_start_normal()`.

### J5. ExportHistoryPanel: инкрементальный API (решает C1, D1)

`app/ui/export_jobs/history_panel.py`:

```python
class ExportHistoryPanel(QWidget):
    def prepend_entry(self, entry: ExportHistoryEntry) -> None:
        if len(self._history) >= HISTORY_MAX:
            removed = self._history.pop()
            last_widget = self._history_layout.takeAt(
                self._history_layout.count() - 1
            )
            if last_widget and last_widget.widget():
                last_widget.widget().deleteLater()
        self._history.insert(0, entry)
        row = HistoryRow(entry, 0, self)
        row.delete_requested.connect(self._on_delete_index)
        self._history_layout.insertWidget(0, row)
        self._update_header()
        self.changed.emit()

    @Slot(int)
    def _on_delete_index(self, index: int) -> None:
        # index соответствует позиции в data; ищем виджет по identity или data-prop
        ...
```

Полный `_rebuild()` оставить только для `set_history()` (редкий случай — загрузка из config).

### J6. ResourceMonitor для дебаг-панели (новая фича)

`app/platform/resource_monitor.py`:

```python
from dataclasses import dataclass
from PySide6.QtCore import QObject, QTimer, Signal
import psutil  # добавить в requirements.txt

@dataclass(slots=True, frozen=True)
class ResourceSample:
    cpu_percent: float            # 0..100 (один core; для sum-all — cpu_percent(interval=None))
    rss_bytes: int                # resident set size
    handles: int                  # Windows handles (на Linux — file descriptors)
    threads: int

class ResourceMonitor(QObject):
    sample = Signal(object)       # ResourceSample

    def __init__(self, interval_ms: int = 1000, parent=None) -> None:
        super().__init__(parent)
        self._proc = psutil.Process()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        # прогреть cpu_percent (первый вызов всегда 0.0)
        self._proc.cpu_percent(interval=None)

    def start(self) -> None: self._timer.start()
    def stop(self) -> None: self._timer.stop()

    def _tick(self) -> None:
        try:
            with self._proc.oneshot():
                cpu = self._proc.cpu_percent(interval=None)
                mem = self._proc.memory_info().rss
                handles = getattr(self._proc, "num_handles", lambda: 0)()
                threads = self._proc.num_threads()
            self.sample.emit(ResourceSample(cpu, mem, handles, threads))
        except psutil.Error:
            pass  # процесс исчез — выходим молча
```

`app/ui/dialogs/debug_window/resource_monitor_bar.py`:

```python
class ResourceMonitorBar(QWidget):
    def __init__(self, monitor: ResourceMonitor, parent=None) -> None:
        super().__init__(parent)
        self._monitor = monitor
        self._cpu = QLabel("CPU 0.0 %")
        self._ram = QLabel("RAM 0 MB")
        self._handles = QLabel("Handles 0")
        self._threads = QLabel("Threads 0")
        # Sparkline (последние 60 точек) можно отрендерить простым QPainter-ом
        self._cpu_spark = Sparkline(maxlen=60, max_value=100.0, parent=self)
        self._ram_spark = Sparkline(maxlen=60, parent=self)

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(12)
        for w in (self._cpu, self._cpu_spark, self._ram, self._ram_spark,
                  self._handles, self._threads):
            row.addWidget(w)
        row.addStretch(1)

        self._monitor.sample.connect(self._apply)

    @Slot(object)
    def _apply(self, s: ResourceSample) -> None:
        self._cpu.setText(f"CPU {s.cpu_percent:.1f} %")
        self._ram.setText(f"RAM {s.rss_bytes / 1024 / 1024:.1f} MB")
        self._handles.setText(f"Handles {s.handles}")
        self._threads.setText(f"Threads {s.threads}")
        self._cpu_spark.push(s.cpu_percent)
        self._ram_spark.push(s.rss_bytes / 1024 / 1024)
```

Интеграция в `DebugWindow` ([app/ui/debug_window.py](app/ui/debug_window.py) → `app/ui/dialogs/debug_window/window.py`):

```python
# в __init__ после лог-панели:
self._monitor = ResourceMonitor(interval_ms=1000, parent=self)
self._resource_bar = ResourceMonitorBar(self._monitor, parent=self)
layout.addWidget(self._resource_bar)
self._monitor.start()

def closeEvent(self, event):
    self._monitor.stop()
    super().closeEvent(event)
```

**Зависимость:** `psutil>=6.0` в `requirements.txt` и `constraints-py314-win.txt`. psutil поддерживает Python 3.14.

**Проверка через PyInstaller:** psutil имеет нативные расширения → добавить в `build.spec.hiddenimports`:
```python
hiddenimports=[..., "psutil", "psutil._pswindows"],
```

### J7. Дополнительные точечные правки

| № | Файл | Правка |
|---|------|--------|
| J7-a | [build.spec:75](build.spec:75) | `upx=False` + TODO на кодписание (`codesign_identity` не поддерживается на Windows напрямую, использовать `signtool.exe` после сборки). |
| J7-b | [app/core/updater.py:96-113](app/core/updater.py:96) | `new_exe` класть в `os.path.dirname(exe_path)`, а не `tempfile.gettempdir()`; добавить SHA256-проверку (GitHub Release asset digest уже в `release_data["assets"][i]["digest"]` начиная с 2024). |
| J7-c | [app/config.py:195-213](app/config.py:195) | Safe-guard: `tmp_replaced = False` после `os.replace`; unlink только при `not tmp_replaced`. |
| J7-d | [app/core/app_logger.py:21-42](app/core/app_logger.py:21) | Добавить `SecretFilter` (J3), плюс explicit parent для `_Bridge()` (сейчас без parent — не течёт, т.к. держится через `self._bridge`, но по стилю лучше передавать). |
| J7-e | [main.py:32, 59](main.py:32) | Убрать дубль `from PySide6.QtWidgets import QApplication`; `_load_fonts` принимает `app: QApplication` аргументом. |
| J7-f | [app/core/sql_client.py:113-118](app/core/sql_client.py:113) | Удалить `if not isinstance(rows, list)`: pyodbc гарантирует list. Коммент вместо кода. |
| J7-g | [app/ui/settings_sql_controller.py](app/ui/settings_sql_controller.py) | Разбить на `SettingsSqlScanController` + `SettingsSqlListController` + `SettingsSqlTestController` (см. A-1), каждый в своём файле в `app/ui/settings/sql/controllers/`. |
| J7-h | [app/ui/threading.py:10](app/ui/threading.py:10) | `from collections.abc import Callable` — убрать `typing.Callable` (`Any` оставить — он из `typing`). |
| J7-i | Все `.py` (134 шт.) | Массово удалить `# -*- coding: utf-8 -*-`. |
| J7-j | Все `.py` в `app/` | Массово добавить `from __future__ import annotations` первой строкой. |
| J7-k | [app/config.py:51-77](app/config.py:51) | `class ExportJob(TypedDict)` + `NotRequired[str]` и т.д. Снимаем `total=False`, делаем обязательные поля обязательными. |
| J7-l | [app/ui/_formatters.py](app/ui/common/formatters.py) (новый) | `format_relative_timestamp(ts_str)` = merge логики из двух презентеров. |

## K. Реализация CPU/RAM-мониторинга в дебаг-панели

### K.1. Выбор зависимости

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| **psutil** ← рекомендуется | Cross-platform, стабильный API, 1 package; поддерживает Python 3.14 | +~1 MB к экзешнику; нативное расширение (hidden import для PyInstaller) |
| Чистый ctypes + Win32 (GetProcessMemoryInfo, GetProcessHandleCount) | Нет зависимостей | Windows-only; больше кода; нужно точно выверять структуры |
| Qt-встроенное | — | QtCore не даёт CPU/RAM; только через QtSystemTools (экспериментально в 6.6+, нестабильно) |

### K.2. Что измерять и показывать

| Метрика | Источник | Частота | Формат |
|---------|----------|---------|--------|
| CPU (текущий %) | `Process.cpu_percent(interval=None)` | 1 Гц | `CPU 3.2 %` + 60-точечный sparkline |
| RAM (RSS) | `Process.memory_info().rss` | 1 Гц | `RAM 128.4 MB` + sparkline |
| Handles (Windows) / FDs (Linux) | `Process.num_handles()` / `num_fds()` | 1 Гц | `Handles 421` (красный если >2000) |
| Threads | `Process.num_threads()` | 1 Гц | `Threads 9` |
| I/O counters (опц.) | `Process.io_counters()` | 1 Гц | `IO ↑12 KB ↓3 KB/s` |
| Peak RAM | `max` текущий RSS | per-sample | `Peak 156 MB` в tooltip |

### K.3. Где разместить в UI

Футер в `DebugWindow` — строка высотой ~28 px под лог-текстом. Не в главном окне (не мешает пользователю). Обновляется только когда окно открыто (см. `start()`/`stop()` по `showEvent`/`hideEvent`).

Дополнительно (опционально): крошечный `CPU/RAM` бейдж в tray-menu или таскбаре, обновляемый реже (раз в 5 с).

### K.4. Как использовать для до/после

В `DebugWindow` добавить кнопку «📋 Copy snapshot» — экспортирует в буфер обмена:

```
=== iDentBridge resource snapshot ===
Time: 2026-04-17 14:32:10
Python: 3.14.4
App version: 0.0.1
Uptime: 02:14:33
CPU avg (last 60s): 1.4 %
CPU peak: 18.2 % (at 14:28:02 — export run)
RAM current: 134.1 MB
RAM peak: 158.6 MB
Handles: 421 (peak 510)
Threads: 9
```

Эту выписку можно прикладывать к GitHub issue / перед и после рефакторинга сравнивать:
«До рефакторинга C1: RAM peak при 500 выгрузках = 220 MB. После: 145 MB».

## L. Визуальные макеты

### L.1. Дебаг-панель «до»

```
┌──────────────── iDentBridge — Debug ─────────────────── ▢ × ┐
│                                                               │
│  14:30:12 [INFO] app.core.scheduler: next run 14:45           │
│  14:30:15 [INFO] app.workers.export_worker: Выгрузка 'daily'  │
│  14:30:15 [INFO] app.workers.export_worker: 1234 строк →      │
│           webhook https://hooks.slack.com/T123/B456/XYZsecret │
│  14:30:16 [WARN] app.core.sql_client: retry 1/3 (timeout)     │
│  ...                                                           │
│                                                                │
│  [ Clear ]  [ Copy ]                                           │
└────────────────────────────────────────────────────────────────┘
```

(⚠ видно утечку секрета в логе — см. C2)

### L.2. Дебаг-панель «после»

```
┌──────────────── iDentBridge — Debug ─────────────────── ▢ × ┐
│                                                               │
│  14:30:12 [INFO] app.scheduling.scheduler: next run 14:45     │
│  14:30:15 [INFO] app.export.worker: Выгрузка 'daily'          │
│  14:30:15 [INFO] app.export.sinks.webhook: 1234 строк →       │
│           https://hooks.slack.com/services/***?***            │
│  14:30:16 [WARN] app.database.mssql.client: retry 1/3         │
│  ...                                                           │
│                                                                │
│  [ Clear ]  [ Copy log ]  [ Copy snapshot ]                    │
├────────────────────────────────────────────────────────────────┤
│ CPU 3.2% ▁▂▁▃▂▂▅▇▄▂▁ │ RAM 128 MB ▁▁▁▂▂▂▃▃▃▃ │ H 421 │ T 9 │
└────────────────────────────────────────────────────────────────┘
                                              ↑ новый footer
```

### L.3. Плотность папок — «до» vs «после»

```
 ДО (app/ui плоско)              ПОСЛЕ (app/ui фича-пакетами)
 ────────────────────             ────────────────────────────
 app/ui/                          app/ui/
 ├── dashboard_*.py × 7           ├── dashboard/          ← 7
 ├── debug_window*.py × 3         ├── dialogs/
 ├── error_dialog*.py × 3         │   ├── debug_window/   ← 3
 ├── export_editor_*.py × 5       │   └── error_dialog/   ← 3
 ├── export_execution_*.py        ├── export_editor/      ← 12
 ├── export_history_panel.py      │   └── test_run_dialog/← 3
 ├── export_job_editor*.py × 2    ├── export_jobs/        ← 10
 ├── export_job_tile*.py × 2      ├── app_window/         ← 9
 ├── export_jobs_*.py × 5         ├── settings/
 ├── export_schedule_panel.py     │   ├── ...             ← 7
 ├── export_sql*.py × 2           │   └── sql/
 ├── history_row*.py × 2          │       └── controllers/← 3 + 4
 ├── main_window_*.py × 9         ├── sql_editor/         ← 4
 ├── settings_*.py × 12           ├── title_bar/          ← 3
 ├── settings_sql_*.py × 5        └── common/             ← 6
 ├── sql_editor*.py × 4
 ├── sql_highlight*.py × 2
 ├── test_run_dialog*.py × 3
 ├── title_bar*.py × 3
 └── прочие (theme, widgets, …)

 70 файлов, 1 уровень           9 подпапок, 2-3 уровня
 Поиск: ctrl-p + префикс        Поиск: по дереву (Explorer)
 Когнитивная нагрузка: высокая  Когнитивная нагрузка: низкая
```

### L.4. Export pipeline — «до» vs «после»

```
 ДО                                            ПОСЛЕ
 ─────────────────────                         ─────────────────────
                                               ┌──────────────────────┐
 ┌─────────────────────┐                       │    ExportWorker      │
 │    ExportWorker     │                       │    (QObject, thin)   │
 │   137 строк, всё    │                       └─────────┬────────────┘
 │   в одном .run():   │                                 │ uses
 │   • pyodbc connect  │                       ┌─────────▼────────────┐
 │   • SQL query       │                       │  ExportPipeline      │
 │   • urllib POST     │    ─────►             │  • connect/query/    │
 │   • retry logic     │                       │    disconnect        │
 │   • JSON serialize  │                       │  • calls sink.push   │
 │   • history entry   │                       └──┬──────┬─────────┬──┘
 │                     │                          │      │         │
 └─────────────────────┘                          ▼      ▼         ▼
                                             DBClient  Sink    Logger
                                             (Proto)   (Proto) (filtered)
                                                │        │
                                          ┌─────┴──┐ ┌───┴────┐
                                          │MssqlCl │ │Webhook │
                                          │ent     │ │Sink    │
                                          └────────┘ └────────┘
                                                     (будущие:
                                                     S3Sink, KafkaSink)

 Добавить S3 = переписать ExportWorker   Добавить S3 = 1 новый файл
                                         app/export/sinks/s3.py
```

## M. Оценка «до» и «после»

| Срез | До | После рефакторинга | Прирост |
|------|---:|-------------------:|--------:|
| Архитектура | 7 / 10 | 9 / 10 | +2 |
| Нейминг | 7.5 / 10 | 8.5 / 10 | +1 |
| Утечки и ресурсы | 7 / 10 | 9 / 10 | +2 |
| Производительность | 7.5 / 10 | 9 / 10 | +1.5 |
| Python 3.14 соответствие | 7.5 / 10 | 9.5 / 10 | +2 |
| Многопоточность | 9 / 10 | 9.5 / 10 | +0.5 |
| Масштабируемость | 6.5 / 10 | 9 / 10 | +2.5 |
| Наблюдаемость | 5 / 10 (только логи) | 8.5 / 10 (+ CPU/RAM/handles) | +3.5 |
| **Общее** | **7.5 / 10** | **9 / 10** | **+1.5** |

### Количественные метрики (прогноз)

| Метрика | До | После | Источник |
|---------|---:|------:|----------|
| Строк `# -*- coding: utf-8 -*-` | 134 | 0 | J7-i |
| Файлов в `app/ui/` (flat) | 70 | 0 (все в подпапках) | I |
| Макс. глубина иерархии | 2 | 4 | I |
| Call-sites `ConfigManager.update/save` | 5 (+fsync каждый) | 5 (batch) | J1 |
| fsync в минуту при активной настройке | 6–10 | 1–2 | J1 |
| Риск утечки webhook-токена в логе | Да | Нет (SecretFilter) | J3 |
| Типов export-sink | 1 (webhook hardcoded) | n (Protocol) | J2 |
| Типов database-client | 1 (MSSQL hardcoded) | n (Protocol + Factory) | I |
| Rebuild истории на prepend (N=50) | O(N) widgets | O(1) widgets | J5 |
| RAM peak на 1000 выгрузок (оценка) | ~220 MB | ~145 MB | J5 + J2 |
| Видимость CPU/RAM в UI | Нет | Да (footer в DebugWindow) | K |
| Тестовое покрытие (line) | ~60% | ~75% | новые pipeline/sink unit-тесты |
| Время cold-start (оценка) | 1.2 s | 1.1 s | меньше flat-imports |

### Рекомендованный порядок (7 этапов, ~2 недели работы одного разработчика)

**Этап 0 — snapshot (15 минут, обязательный первый шаг).**

Зафиксировать текущее состояние как baseline перед любыми изменениями. Это страховка: если любой из последующих этапов сломает UI/тесты, есть точка безопасного отката.

```bash
cd "D:/ProjectLocal/identa report"

# 0.1. Убедиться, что нет незакоммиченного мусора
git status --short

# 0.2. Зафиксировать текущие зелёные метрики
pytest --tb=short | tee docs/audits/baseline-2026-04-17-tests.txt
python tools/perf_smoke.py --scenario all --cycles 5 --top 8 \
  | tee docs/audits/baseline-2026-04-17-perf.txt

# 0.3. Сохранить дерево файлов и счётчики (для сравнения «до/после»)
(
  echo "# Pre-refactor snapshot $(date -Iseconds)"
  echo "## app tree"
  find app -name "*.py" | sort
  echo
  echo "## counts"
  echo "app_total=$(find app -name '*.py' | wc -l)"
  echo "app_ui_flat=$(find app/ui -maxdepth 1 -name '*.py' | wc -l)"
  echo "coding_utf8=$(grep -lrF '# -*- coding: utf-8 -*-' . 2>/dev/null | wc -l)"
  echo "future_annotations=$(grep -lrF 'from __future__ import annotations' app 2>/dev/null | wc -l)"
  echo "typing_callable=$(grep -lE 'from typing import[^\n]*Callable' -r app 2>/dev/null | wc -l)"
) > docs/audits/baseline-2026-04-17-snapshot.txt

# 0.4. Зафиксировать snapshot-коммит + подписать тегом
git add docs/audits/baseline-2026-04-17-tests.txt \
        docs/audits/baseline-2026-04-17-perf.txt \
        docs/audits/baseline-2026-04-17-snapshot.txt
git commit -m "chore(audit): snapshot pre-refactor baseline (2026-04-17)

Captures:
- Full pytest log (all green)
- perf_smoke metrics (positive_retained_kib baseline)
- File tree + structural counters

Reference point before executing audit plan (см. plan proud-twirling-moore)."

git tag -a pre-refactor-2026-04-17 -m "Pre-refactor baseline for audit plan"
```

**Откат в случае непредвиденных проблем:**
```bash
git reset --hard pre-refactor-2026-04-17   # жёсткий возврат
# или
git checkout pre-refactor-2026-04-17 -- <files>   # точечный возврат отдельных файлов
```

**Что НЕ коммитить на этом этапе:** никаких правок кода. Только метрики и teg. Это «фотография» состояния.

---

1. **Этап 1 — Critical-заземление (день 1).** `SecretFilter` + тест (фикс **C2**, пункт J3). ResourceMonitor + ResourceMonitorBar (K). Оба — изолированы, не ломают архитектуру. После: `pytest`, коммит с сообщением `security: mask secrets in logs (audit C2)`.
2. **Этап 2 — точечные High-фиксы (2 дня).** Инкрементальная история (**C1**/J5), явный ssl_context (**C9**), батч-конфиг (**D2**/J1), safeguard в `config.save` (**C4**/J7-c), убрать дубль QApplication (**D6**/J7-e), чистка `isinstance(rows, list)` (**D3**/J7-f). По одному коммиту на пункт — проще откатывать.
3. **Этап 3 — ExportSink Protocol (2-3 дня).** J2. Текущий WebhookSink как единственная реализация. `ExportWorker` → `ExportPipeline + Sink`. Закрывает C3 полностью (пишем через `JSONEncoder` + chunked-serialization из fetchmany, как уже сделано в 4f9c3e4 для test dialog). Все существующие тесты должны пройти без правок.
4. **Этап 4 — DatabaseClient Protocol (2 дня).** Выделить `MssqlClient` под Protocol. Factory. `instance_scanner` → `database/mssql/scanner.py`. Добавить smoke-тест на PostgreSQL-ready (не реализация, только сигнатуры).
5. **Этап 5 — массовая перекладка папок (2 дня).** Раздел **I** плана. Два коммита: (1) создать новые пути с shim-файлами (`from app.new.path import *` в старых местах), (2) перевести импорты и удалить shim'ы. Прогон `pytest` + `perf_smoke` **после каждого** коммита.
6. **Этап 6 — матч-рефакторинг scheduler + остальные наблюдения (1 день).** `match` в [scheduler._schedule_next](app/core/scheduler.py:100) (**E3**/J4), разбиение **SettingsSqlController** (**A1**), дедуп форматирования ts (**A3**), merge `dashboard_activity_store.py` (**A2**), переименование `app/ui/test_run_dialog.py` (**A5**).
7. **Этап 7 — косметика Python 3.14 (1 день).** `from __future__ import annotations` во все файлы **app/** (**E1**), массовое удаление 138 × `coding: utf-8` (**E2**), `NotRequired` в TypedDict (**E4**), добить `collections.abc.Callable` в [threading.py:10](app/ui/threading.py:10) (**E5** — 1 строка), `@override` на overriding-методах (**E7**).

**Контроль регрессий после каждого этапа:** см. раздел **N** ниже — обязательный 4-шаговый gate (`pytest` → launch smoke → сборка EXE → EXE smoke). Переход к следующему этапу **только если gate зелёный**. При красном gate — автооткат на тег этапа.

**Финальный этап — закрывающий snapshot.** После этапа 7 повторить процедуру из этапа 0 с суффиксом `post-refactor-<date>` и тегом `post-refactor-YYYY-MM-DD`. Приложить к отчёту в PR для сравнения метрик до/после.

## N. Gate после каждого этапа (обязательно, в этом порядке)

Каждый из этапов 1–7 закрывается **одинаковой** 4-шаговой проверкой. Если любой шаг падает — этап откатывается (`git reset --hard <stage-tag>^`), расследование, повторный заход. **Без пропусков.**

### N.1. Тесты

```bash
cd "D:/ProjectLocal/identa report"
pytest -x --tb=short 2>&1 | tee "docs/audits/stage-<N>-tests.txt"
```

Критерий: **exit code 0**, все тесты зелёные. `-x` останавливает на первой ошибке. Если упало — читать `docs/audits/stage-<N>-tests.txt`, фиксить, повторять.

### N.2. Launch smoke (приложение стартует без падения)

Вариант 2.А — через perf_smoke (offscreen, headless, уже в проекте):

```bash
QT_QPA_PLATFORM=offscreen \
  python tools/perf_smoke.py --scenario all --cycles 3 --top 8 \
  2>&1 | tee "docs/audits/stage-<N>-launch.txt"
```

Критерий: **exit 0** + `positive_retained_kib` не превышает baseline (`docs/audits/baseline-2026-04-17-perf.txt`) более чем на +10%. Сравнение:

```bash
python - <<'PY'
import re, pathlib
base = pathlib.Path("docs/audits/baseline-2026-04-17-perf.txt").read_text()
curr = pathlib.Path("docs/audits/stage-<N>-launch.txt").read_text()
rx = re.compile(r"positive_retained_kib=([\d.]+)")
b = float(rx.search(base).group(1)); c = float(rx.search(curr).group(1))
delta = (c - b) / b * 100
print(f"baseline={b:.1f} KiB  current={c:.1f} KiB  delta={delta:+.1f}%")
exit(0 if delta < 10 else 2)
PY
```

Вариант 2.Б — реальный старт с таймаутом (подкрепляет 2.А, если есть Windows-специфика в tray/autostart):

```bash
# Windows PowerShell:
$proc = Start-Process -FilePath "python" -ArgumentList "main.py" `
  -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 10
if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force; Write-Host "OK: still running" }
else { Write-Host "FAIL: exited with $($proc.ExitCode)"; exit 2 }
```

### N.3. Сборка EXE (PyInstaller)

```bash
cd "D:/ProjectLocal/identa report"
pyinstaller build.spec --clean --noconfirm 2>&1 | tee "docs/audits/stage-<N>-build.txt"
```

Критерии:
- **exit 0**
- Артефакт `dist/iDentSync.exe` существует
- Размер артефакта > `MIN_DOWNLOAD_BYTES` (1 000 000 байт, см. [constants.py:45](app/core/constants.py:45)):

```bash
test -f "dist/iDentSync.exe" || { echo "FAIL: no artifact"; exit 2; }
size=$(stat --format=%s "dist/iDentSync.exe" 2>/dev/null || powershell -c "(Get-Item dist/iDentSync.exe).Length")
test "$size" -gt 1000000 || { echo "FAIL: too small ($size)"; exit 2; }
echo "OK: $size bytes"
```

### N.4. EXE smoke (собранный бинарник запускается)

```bash
# Windows PowerShell:
$exe  = "dist/iDentSync.exe"
$proc = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 15
if (-not $proc.HasExited) {
  Stop-Process -Id $proc.Id -Force
  Write-Host "OK: EXE alive 15s"
} else {
  Write-Host "FAIL: EXE exited code=$($proc.ExitCode)"
  exit 2
}
```

Дополнительно (опционально): прогнать `signtool verify /pa dist/iDentSync.exe` — если подписан; и проверить через `Get-AuthenticodeSignature` состояние подписи.

### N.5. Завершение этапа

Если все 4 шага зелёные:

```bash
git tag -a "stage-<N>-passed-$(date +%Y%m%d)" -m "Stage <N> gate passed"
```

Иначе:

```bash
git reset --hard "stage-<N>-start"
# начать этап заново с корректировками
```

Для этого **перед** каждым этапом делается `git tag stage-<N>-start`, чтобы было откуда откатываться.

### N.6. Журнал gate'ов

После каждого этапа добавлять строчку в `docs/audits/gate-log.md`:

```
## Stage 1 — 2026-04-18
- pytest: PASS (281 passed, 0 failed, 12.3s)
- launch smoke: PASS (retained 2380.2 KiB, delta -0.8% vs baseline)
- build: PASS (iDentSync.exe 28.4 MB)
- EXE smoke: PASS (15 s alive)
- Tag: stage-1-passed-20260418
```

Это даёт прозрачную историю для PR-ревью и расследования регрессий.

## O. Оркестрация агентов — автономный режим

Исполнение автономное: без остановки и вопросов пользователю между этапами, **кроме** случая красного gate или неоднозначности в коде. Каждый этап закрывает набор точечных агентов, каждый — со своей узкой задачей и чёткими deliverable'ами. Агенты запускаются параллельно, если задачи независимы; иначе — последовательно внутри этапа.

**Общие правила для всех агентов:**

- Subagent type: `general-purpose` для правок кода, `Explore` для верификации, `feature-dev:code-reviewer` для ревью чужих правок.
- Промпт каждого агента самодостаточен: file:line, что изменить, как протестировать.
- Каждый агент завершается созданием отдельного git-коммита с conventional-commits сообщением.
- После группы коммитов в этапе — запуск gate (раздел N). Gate запускается отдельным агентом с тип `general-purpose`.
- **Красный gate ⇒ автооткат + пауза для пользователя.** Без этого условия останавливаться нельзя.

### O.0. Snapshot-агент (этап 0)

| ID | Роль | subagent_type | Deliverable |
|----|------|---------------|-------------|
| `agent-0.1-snapshot` | Снять baseline-метрики и создать snapshot-коммит | `general-purpose` | Файлы `docs/audits/baseline-2026-04-17-*.txt`, коммит `chore(audit): snapshot pre-refactor baseline`, тег `pre-refactor-2026-04-17` |

Промпт: «Выполни команды из этапа 0 раздела M плана `proud-twirling-moore.md`. Собери `pytest`-лог, `perf_smoke`-лог, дерево файлов. Создай snapshot-коммит + git-tag. Не трогай код. По завершении — отчёт в ≤100 слов.»

### O.1. Этап 1 — Critical-заземление

| ID | Задача | subagent_type | Файлы |
|----|--------|---------------|-------|
| `agent-1.1-secretfilter` | Создать [app/core/log_sanitizer.py](app/core/log_sanitizer.py) с `SecretFilter` (регэкс-маскинг URL query + `PWD=` в строках логов); подключить в [app/core/app_logger.py:setup()](app/core/app_logger.py:50); добавить тест `tests/test_log_sanitizer.py` с кейсами webhook-URL, PWD-строки, обычного текста. | `general-purpose` | **создать:** `app/core/log_sanitizer.py`, `tests/test_log_sanitizer.py`; **править:** `app/core/app_logger.py` |
| `agent-1.2-resmon-core` | Добавить `psutil>=6.0` в `requirements.txt` и `constraints-py314-win.txt`; создать `app/core/resource_monitor.py` с `ResourceSample` (dataclass) и `ResourceMonitor(QObject)` (QTimer@1 Гц, сигнал `sample`). Тест: `tests/test_resource_monitor.py` с моком `psutil.Process`. | `general-purpose` | **создать:** `app/core/resource_monitor.py`, `tests/test_resource_monitor.py`; **править:** `requirements.txt`, `constraints-py314-win.txt`, [build.spec:20-27](build.spec:20) (`hiddenimports += ["psutil", "psutil._pswindows"]`) |
| `agent-1.3-resmon-ui` | Создать [app/ui/resource_monitor_bar.py](app/ui/resource_monitor_bar.py) (QWidget-футер: 4 QLabel + sparkline); интегрировать в [app/ui/debug_window.py](app/ui/debug_window.py) с `start()`/`stop()` по `showEvent`/`hideEvent`; тест: `tests/test_resource_monitor_bar.py` с qtbot. | `general-purpose` | **создать:** `app/ui/resource_monitor_bar.py`, `tests/test_resource_monitor_bar.py`; **править:** `app/ui/debug_window.py` |
| `agent-1.4-verify` | Ревью диффа этапа — confidence-based, только High+. | `feature-dev:code-reviewer` | Отчёт в stdout |
| `agent-1.5-gate` | Запустить N.1–N.4. Если зелёные — `git tag stage-1-passed-$(date)`. Если красные — `git reset --hard stage-1-start` + отчёт пользователю. | `general-purpose` | Запись в `docs/audits/gate-log.md` |

Параллельность: 1.1, 1.2 можно запускать одновременно (разные файлы, не конфликтуют). 1.3 ждёт 1.2 (зависит от `ResourceMonitor`). 1.4 ждёт 1.1–1.3. 1.5 ждёт 1.4.

### O.2. Этап 2 — High-точки

| ID | Задача | subagent_type | Файлы |
|----|--------|---------------|-------|
| `agent-2.1-hist-inc` | Заменить `_rebuild()` в [export_history_panel.py:123-138](app/ui/export_history_panel.py:123) на инкрементальный `prepend_entry`/`_on_delete_index` (см. J5 плана). `_rebuild()` оставить только под `set_history()`. Обновить [tests/test_export_history_panel.py](tests/test_export_history_panel.py). | `general-purpose` | `export_history_panel.py`, `test_export_history_panel.py` |
| `agent-2.2-ssl` | В [export_worker.py:100](app/workers/export_worker.py:100) создать явный `ssl.create_default_context()` один раз на воркер и передать в `urlopen(..., context=ctx)`. Аналогично унифицировать с паттерном из [updater.py:86](app/core/updater.py:86). | `general-purpose` | `export_worker.py` |
| `agent-2.3-batch-cfg` | Добавить в [ConfigManager](app/config.py:133) контекст-менеджер `batch()` + debounced-flush (J1 плана). Перевести [settings_form_controller.py:95-105](app/ui/settings_form_controller.py:95) на `with config.batch(): ...`. Остальные 3 call-site — не трогать (они одиночные). | `general-purpose` | `app/config.py`, `app/ui/settings_form_controller.py`, `tests/test_config.py` (добавить тест `batch()`) |
| `agent-2.4-small-fixes` | Три мелких независимых фикса в отдельных коммитах: (а) safeguard в [config.py:195-213](app/config.py:195) (`tmp_replaced` флаг); (б) убрать дубль `from PySide6.QtWidgets import QApplication` в [main.py:59](main.py:59), передать `app` аргументом в `_load_fonts`; (в) удалить `if not isinstance(rows, list)` в [sql_client.py:119-120](app/core/sql_client.py:119). | `general-purpose` | `app/config.py`, `main.py`, `app/core/sql_client.py` |
| `agent-2.5-gate` | N.1–N.4. | `general-purpose` | `gate-log.md` |

Параллельность: 2.1, 2.2, 2.3, 2.4 — независимые, запустить одновременно. 2.5 ждёт всех четырёх.

### O.3. Этап 3 — ExportSink Protocol

| ID | Задача | subagent_type | Файлы |
|----|--------|---------------|-------|
| `agent-3.1-proto` | Создать `app/export/protocol.py` с `ExportSink(Protocol)` (см. J2). | `general-purpose` | **создать:** `app/export/__init__.py`, `app/export/protocol.py` |
| `agent-3.2-sink-webhook` | Извлечь webhook-логику из [export_worker.py:76-120](app/workers/export_worker.py:76) в `app/export/sinks/webhook.py:WebhookSink`. Добавить `_SqlJSONEncoder` с явной обработкой `Decimal`, `datetime`, `bytes`. Включить `chunked-serialization` (использовать тот же `fetchmany`-паттерн, что уже в sql_client.py:121-138). Тест: `tests/test_webhook_sink.py` с `http.server.BaseHTTPRequestHandler`-мок. | `general-purpose` | **создать:** `app/export/sinks/__init__.py`, `app/export/sinks/webhook.py`, `tests/test_webhook_sink.py` |
| `agent-3.3-pipeline` | Создать `app/export/pipeline.py:ExportPipeline` (dataclass с `db`, `sink`, `logger`); переписать [export_worker.py](app/workers/export_worker.py) как тонкий QObject-обёртку (`ExportWorker(pipeline, job)` + `run()` делегирует пайплайну). Адаптировать [test_export_worker.py](tests/test_export_worker.py). | `general-purpose` | **создать:** `app/export/pipeline.py`; **править:** `app/workers/export_worker.py`, `tests/test_export_worker.py` |
| `agent-3.4-review` | Ревью диффа этапа 3 на предмет backward-compat (никто из UI не вызывал `ExportWorker` с кастомной сигнатурой). | `feature-dev:code-reviewer` | stdout |
| `agent-3.5-gate` | N.1–N.4. | `general-purpose` | `gate-log.md` |

Параллельность: 3.1 идёт первым (все остальные его импортируют). 3.2 и 3.3 — последовательно (3.3 импортирует Protocol из 3.1 и может использовать Sink из 3.2, но для разделения можно 3.3 делать с `InMemorySink`-фейком). 3.4 и 3.5 — последовательно после 3.3.

### O.4. Этап 4 — DatabaseClient Protocol

| ID | Задача | subagent_type | Файлы |
|----|--------|---------------|-------|
| `agent-4.1-proto` | Создать `app/database/protocol.py:DatabaseClient(Protocol)` с `connect/query/disconnect/is_alive/test_connection`. | `general-purpose` | **создать:** `app/database/__init__.py`, `app/database/protocol.py` |
| `agent-4.2-mssql` | Переместить [sql_client.py](app/core/sql_client.py) → `app/database/mssql/client.py:MssqlClient`; [connection.py](app/core/connection.py) → `app/database/mssql/connection.py`; [odbc_utils.py](app/core/odbc_utils.py) → `app/database/mssql/odbc_utils.py`. Оставить в старых местах re-export shim'ы `from app.database.mssql.client import MssqlClient as SqlClient`. | `general-purpose` | **создать:** `app/database/mssql/*`; **править старые файлы как shim'ы** |
| `agent-4.3-scanner` | [instance_scanner.py](app/core/instance_scanner.py) → `app/database/mssql/scanner.py` + shim. | `general-purpose` | — |
| `agent-4.4-factory` | Создать `app/database/factory.py` с `create_database_client(kind: str, cfg)`. Поддержка `"mssql"` — вызывает `MssqlClient(cfg)`. Точка расширения задокументирована. | `general-purpose` | **создать:** `app/database/factory.py` |
| `agent-4.5-gate` | N.1–N.4. | `general-purpose` | `gate-log.md` |

Параллельность: 4.1 первым. 4.2, 4.3 параллельно. 4.4 после 4.1. 4.5 после всех.

### O.5. Этап 5 — массовая перекладка папок (раздел I)

Делается в **3 волны**, каждая со своим gate, чтобы в случае регрессии откатывать маленькими шагами.

**Волна 5.A — domain/config/logging/platform (лёгкая):**

| ID | Задача |
|----|--------|
| `agent-5A.1-domain` | Выделить TypedDict/dataclass из [app/config.py](app/config.py) в `app/domain/config_types.py`; `QueryResult/SyncResult/SqlInstance` из там же и [sql_client.py](app/core/sql_client.py) в `app/domain/results.py`; [constants.py](app/core/constants.py) → `app/domain/constants.py`. Оставить shim'ы. |
| `agent-5A.2-platform` | [dpapi.py](app/core/dpapi.py), [startup.py](app/core/startup.py) → `app/platform/`. `updater.py` разделить на `app/platform/updater/{github_release,download,apply}.py`. Shim'ы. |
| `agent-5A.3-logging` | [app_logger.py](app/core/app_logger.py) → `app/logging/qt_handler.py`; `log_sanitizer.py` (созданный в 1.1) → `app/logging/sanitizer.py`. Shim. |
| `agent-5A.4-gate` | N.1–N.4. |

**Волна 5.B — scheduling + config-folder:**

| ID | Задача |
|----|--------|
| `agent-5B.1-scheduling` | [scheduler.py](app/core/scheduler.py) → `app/scheduling/scheduler.py`. Shim. |
| `agent-5B.2-config-pkg` | Разнести [app/config.py](app/config.py) на `app/config/manager.py` + `app/config/paths.py` + `app/config/migrations.py` (triggerтипа auto→scheduled в отдельный файл). Shim в корневом `app/config.py`. |
| `agent-5B.3-gate` | N.1–N.4. |

**Волна 5.C — перекладка UI по фича-пакетам (самая крупная):**

| ID | Задача |
|----|--------|
| `agent-5C.1-app-window` | `main_window_*.py` → `app/ui/app_window/`. 9 файлов. |
| `agent-5C.2-dashboard` | `dashboard_*.py` → `app/ui/dashboard/`. 8 файлов. |
| `agent-5C.3-export-jobs` | `export_jobs_*.py`, `export_job_*.py`, `history_row*.py`, `export_history_panel.py` → `app/ui/export_jobs/`. |
| `agent-5C.4-export-editor` | `export_editor_*.py`, `export_sql*.py`, `export_schedule_panel.py`, `test_run_dialog*.py` → `app/ui/export_editor/` + `app/ui/export_editor/test_run_dialog/`. |
| `agent-5C.5-settings` | `settings_*.py`, `settings_sql_*.py` → `app/ui/settings/` + `app/ui/settings/sql/`. |
| `agent-5C.6-sql-editor` | `sql_editor*.py`, `sql_highlight*.py`, `sql_highlighter.py` → `app/ui/sql_editor/`. |
| `agent-5C.7-dialogs` | `error_dialog*.py`, `debug_window*.py` → `app/ui/dialogs/`. |
| `agent-5C.8-common` | `theme.py`, `widgets.py`, `threading.py`, `lucide_icons.py`, `lucide_icon_loader.py`, `icons_rc.py` → `app/ui/common/`; формерт-дубли → `app/ui/common/formatters.py` (J7-l). |
| `agent-5C.9-shim-removal` | Удалить все shim'ы, переписать импорты в целевые пути. Последний коммит волны. |
| `agent-5C.10-gate` | N.1–N.4. |

Параллельность 5.C.1–5.C.8: все волны UI независимы по файлам (разные подпапки) — запустить одновременно. 5.C.9 после всех восьми. 5.C.10 после 5.C.9.

### O.6. Этап 6 — match + A-series

| ID | Задача |
|----|--------|
| `agent-6.1-match-scheduler` | Переписать `_schedule_next` в [scheduler.py:100-141](app/core/scheduler.py:100) на `match` + `ScheduleMode(StrEnum)` (J4). Удалить дубль `Literal[...]` + `SUPPORTED_SCHEDULE_MODES`. |
| `agent-6.2-split-settings-sql` | Разбить [settings_sql_controller.py](app/ui/settings_sql_controller.py) (212 строк) на `scan.py` + `list_db.py` + `test_connection.py` под `app/ui/settings/sql/controllers/`. |
| `agent-6.3-dedup-ts` | Вынести общий `format_relative_timestamp` в `app/ui/common/formatters.py`; удалить локальные копии из `export_job_tile_presenter.py` и `history_row_presenter.py`. |
| `agent-6.4-absorb-store` | Влить [dashboard_activity_store.py](app/ui/dashboard_activity_store.py) в `app/ui/dashboard/helpers.py`, удалить микромодуль. |
| `agent-6.5-rename-test-dialog` | Переименовать `app/ui/test_run_dialog.py` → `app/ui/dry_run_dialog.py` (или аналог). Обновить импорты. |
| `agent-6.6-gate` | N.1–N.4. |

Параллельность: 6.1–6.5 полностью независимы, запускать одновременно. 6.6 — последним.

### O.7. Этап 7 — Python 3.14 косметика

| ID | Задача |
|----|--------|
| `agent-7.1-future-annot` | Массово добавить `from __future__ import annotations` первой строкой во все `app/**/*.py`. Использовать один коммит. |
| `agent-7.2-remove-coding` | Удалить 138 строк `# -*- coding: utf-8 -*-` из всех `.py` проекта. Один коммит. |
| `agent-7.3-notrequired` | Переписать `class ExportHistoryEntry(TypedDict, total=False)` и пр. в [config/manager или domain/config_types](app/domain/config_types.py) на явные `NotRequired[...]`. |
| `agent-7.4-abc-callable` | В [app/ui/common/threading.py:10](app/ui/common/threading.py:10) (после волны 5.C.8) заменить `from typing import Any, Callable` на `from typing import Any` + `from collections.abc import Callable`. 1 строка. |
| `agent-7.5-override` | Пройтись по `run`, `check`, `emit`, `closeEvent` в QObject-классах и добавить `@override` из `typing`. |
| `agent-7.6-gate` | N.1–N.4. |

Параллельность: 7.1–7.5 все независимы, запускаются одновременно. 7.6 — последним.

### O.8. Финальный snapshot-агент

| ID | Задача |
|----|--------|
| `agent-final-snapshot` | Повторить этап 0 с суффиксом `post-refactor-<date>`, создать сравнительный отчёт `docs/audits/before-after-<date>.md` с diff'ами метрик. Тег `post-refactor-<date>`. |

### O.9. Контракт автономной работы

Оркестратор (агент-дирижёр) запускается **один раз**, принимает план и выполняет его **без остановки для подтверждения**. Условия, при которых оркестратор **прерывается и зовёт пользователя**:

1. **Красный gate** (любой из N.1–N.4). Перед остановкой: откат на `stage-<N>-start`, отчёт о падении в чат.
2. **Найден конфликт слияния shim'ов** — которого не покрывает текущий план (значит в коде что-то изменилось после аудита).
3. **Agent-runner не смог интерпретировать задачу** (например, целевой file:line изменился более чем на 20 строк).

Во всех остальных случаях — продолжать к следующему этапу.

### O.10. Итоговая сетка агентов и зависимостей (резюме)

```
Этап 0 ─── 0.1
           │
Этап 1 ─── 1.1 ┬─┐
               │ ├── 1.3 ── 1.4 ── 1.5 (gate)
           1.2 ┴─┘
           │
Этап 2 ─── 2.1 ┐
           2.2 ├── 2.5 (gate)
           2.3 │
           2.4 ┘
           │
Этап 3 ─── 3.1 ── 3.2 ── 3.3 ── 3.4 ── 3.5 (gate)
           │
Этап 4 ─── 4.1 ┬── 4.2
               ├── 4.3    ── 4.5 (gate)
               └── 4.4
           │
Этап 5 ─── 5A.1 ┐
           5A.2 ├── 5A.4 (gate) ┐
           5A.3 ┘                │
           5B.1 ┐                │
           5B.2 ┴── 5B.3 (gate) ┤
           5C.1–8 параллельно    │
                  └── 5C.9 ── 5C.10 (gate)
           │
Этап 6 ─── 6.1 ┐
           6.2 │
           6.3 ├── 6.6 (gate)
           6.4 │
           6.5 ┘
           │
Этап 7 ─── 7.1 ┐
           7.2 │
           7.3 ├── 7.6 (gate)
           7.4 │
           7.5 ┘
           │
Финал  ─── final-snapshot
```

**Суммарно:** 31 точечный агент + 8 gate-агентов + 1 финальный snapshot. Максимальная степень параллелизма — 8 агентов одновременно (волна 5.C). Ожидаемое время при последовательном выполнении одним разработчиком — ~2 недели; при оркестрированном параллельном запуске агентов — ~3–4 рабочих дня.

## Итоговая оценка

| Срез | До | После |
|------|---:|------:|
| Архитектура | 7 / 10 | 9 / 10 |
| Нейминг | 7.5 / 10 | 8.5 / 10 |
| Утечки и ресурсы | 7 / 10 | 9 / 10 |
| Производительность | 7.5 / 10 | 9 / 10 |
| Python 3.14 соответствие | 7.5 / 10 | 9.5 / 10 |
| Многопоточность | 9 / 10 | 9.5 / 10 |
| Масштабируемость | 6.5 / 10 | 9 / 10 |
| Наблюдаемость | 5 / 10 | 8.5 / 10 |
| **Общее** | **7.5 / 10** | **9 / 10** |

Проект сейчас в хорошей форме; основная «долговая» нагрузка — расщеплённый UI-рефакторинг в settings/export_editor, отсутствие плагинной точки для будущих export-backends / database-types и скрытая утечка секретов в логах. Критичных регрессий не обнаружено. Предложенный план за 2 недели переводит проект в состояние «9 / 10»: плоский UI становится фича-папками, экспорт и БД становятся абстракциями, наблюдаемость получает CPU/RAM/handles-мониторинг, а мелкие соответствия Python 3.14 закрываются косметическим финальным этапом.

---

## P. Аудит uncommitted-снапшота (2026-04-17, после коммита `4f750ea`)

Сессия вернулась с 46 изменёнными + 7 untracked файлами. После stage 7 (post-refactor tag) разработчик добавил крупную Google Apps Script волну:

- `app/export/sinks/google_apps_script.py` — новый sink (765 строк, chunked-delivery, retry, progress)
- `app/ui/export_google_sheets_panel.py` (untracked) — UI-панель для GAS настроек (~573 строки)
- `google script back end/src/backend.js` (untracked) — консолидированный JS backend (2323 строки, ex-4 файла)
- `SyncResult.duration_us` + `sql_duration_us` (нс→мкс timings); `format_duration_compact()` в `app/ui/formatters.py`
- `GoogleAppsScriptDeliveryError` + специальный except-branch в `ExportWorker` с масками `mask_secrets`
- `ExportSink.push(..., on_progress=None)` — keyword-only параметр (backwards-compat)
- `ExportJob["gas_options"]` TypedDict (sheet_name, header_row, dedupe_key_columns)
- `resolve_export_sink(url, gas_options=...)` — автоматический выбор sink'а по хосту

**Pytest: 434 passed (+52 к stage-7 baseline 382).** Все ранее закрытые пункты (C1–C9, D2–D6, E2–E5) не регрессировали.

### P.1. Скоринг «до / после» (3 среза)

| Срез | До Stage 0 | После Stage 7 | **Текущий HEAD** | Тренд |
|------|-----------:|--------------:|-----------------:|:-----:|
| Архитектура | 7 / 10 | 9 / 10 | **8 / 10** | ↓1 |
| Нейминг | 7.5 / 10 | 8.5 / 10 | **8 / 10** | ↓0.5 |
| Утечки / ресурсы | 7 / 10 | 9 / 10 | **7 / 10** | ↓2 |
| **Производительность** | 7.5 / 10 | 9 / 10 | **6 / 10** | **↓3** (O(N²) в GAS chunker) |
| Python 3.14 | 7.5 / 10 | 9.5 / 10 | **7 / 10** | ↓2.5 |
| Многопоточность | 9 / 10 | 9.5 / 10 | **8 / 10** | ↓1.5 |
| Масштабируемость | 6.5 / 10 | 9 / 10 | **9 / 10** | = |
| Наблюдаемость | 5 / 10 | 8.5 / 10 | **9 / 10** | ↑0.5 |
| Безопасность | 5 / 10 | 9 / 10 | **8.5 / 10** | ≈ |
| Тесты (покрытие/качество) | 6 / 10 | 8 / 10 | **8.5 / 10** | ↑0.5 |
| **Общее** | **7.5 / 10** | **9 / 10** | **8 / 10** | ↓1 |

**Интерпретация:** GAS-волна добавила много функциональности ценой −1 балл на perf/арх. Сильный плюс: тесты выросли до 8.5 (Node.js harness для бэкенд-JS).

### P.2. Критические находки

#### 🔴 **P.2.1. Leak риск — `.clasp.json` в untracked** (блокирует коммит)

Файлы `google script back end/.clasp.json` и `google script back end/clasp.json` содержат:
```json
"scriptId": "1LxrHnqVpHBohRGjXE8XbinmKI7GN5-acxt0CLMzM2hqfYY_waDsQQjVq"
```
scriptId — приватный идентификатор Apps Script проекта. Попадание в публичный репо → `clasp clone <scriptId>` скачает весь backend-код.

Текущий `.gitignore` не содержит `clasp.json`.

**Действие до `git add`:**
```
# В .gitignore добавить:
google script back end/.clasp.json
google script back end/clasp.json
```

#### 🟠 **P.2.2. O(N²) JSON encoding в GAS chunker**

[app/export/sinks/google_apps_script.py:231-235, 276-314](app/export/sinks/google_apps_script.py:231) —
`_estimate_payload_size()` вызывает `json.dumps(candidate).encode("utf-8")` для каждой добавляемой строки в цикле. 10 000 строк → десятки миллионов перекодирований.

**Исправление (следующий спринт):** закэшировать `len(json.dumps(row))` на строку + инкрементальное сложение вместо повторного `json.dumps(candidate)`. Ожидаемый прирост: perf 6 → 8.5.

#### 🟠 **P.2.3. GAS sink — 765 строк SRP нарушен**

Один модуль держит: валидация URL + chunking + retry + HTTP + парсинг ack + payload-builder. Рекомендуемое расщепление (Low/Medium приоритет):
```
app/export/sinks/google_apps_script/
├── __init__.py          (re-export GoogleAppsScriptSink)
├── chunking.py          (plan_gas_chunks, build_gas_chunk_payload)
├── delivery.py          (POST + retry)
└── ack.py               (parse_gas_ack + _RetryableAckError)
```

### P.3. High-находки

| № | Файл / место | Суть | Приоритет |
|---|--------------|------|-----------|
| P.3.1 | `app/ui/export_google_sheets_panel.py:59-60` | UI-панель напрямую зовёт `urllib.request.urlopen` (через worker, OK thread-wise, но смешивает слои) | Medium |
| P.3.2 | `app/ui/export_google_sheets_panel.py:418-420` | `QTimer(self)` без явного `stop()` в closeEvent/hideEvent — возможен тикер-leak при stress show/hide | Low |
| P.3.3 | `GasOptions: TypedDict, total=False` | Python 3.14 хочет `NotRequired[T]` на каждом поле | Low |
| P.3.4 | QObject-subclasses в новом коде | Нет `@override` на `run`, `eventFilter`, `closeEvent` | Low |
| P.3.5 | `backend.js` — 2323 строки монолит | Консолидация из 4 файлов для удобного `clasp push`; тесты покрывают через Node.js harness — OK, но ревью по коду осложнено | Low |

### P.4. Сильные места (после GAS-волны)

1. **`GoogleAppsScriptDeliveryError`** — user_message vs debug_context разделены, оба проходят через `mask_secrets` ([export_worker.py:72-89](app/workers/export_worker.py:72)). Чистая трассировка без leak'а.
2. **`tests/test_google_apps_script_backend_files.py` (844 строки, 19 тестов)** — Node.js subprocess-харнесс прогоняет JS-backend как чёрный ящик: payload validation, dedupe, idempotency, schema migrations, lock cleanup. Уровень профессиональной интеграции.
3. **Protocol-driven контракт остался целым** — `resolve_export_sink()` = одна строка на новый sink; `on_progress=None` обратно-совместим; factory-тесты ([test_export_pipeline.py:194-247](tests/test_export_pipeline.py:194)) фиксируют новое поведение.
4. **SyncResult timings** — `duration_us` + `sql_duration_us` через `time.perf_counter_ns()`; `format_duration_compact()` рендерит человеческий вид («12.3 мс», «2м 15с»).

### P.5. Чек-лист перед `git add -A`

**Обязательно:**
1. ✅ `pytest -q` → 434 passed (verified).
2. ⚠️ **Добавить в `.gitignore`** (иначе leak `scriptId`):
   ```
   google script back end/.clasp.json
   google script back end/clasp.json
   ```
3. ✅ Untracked файлы все нужны: `backend.js`, 3 новых теста, `export_google_sheets_panel.py` — все относятся к GAS-волне.

**Рекомендуемая последовательность коммита (после выхода из plan mode):**

```bash
cd "D:/ProjectLocal/identa report"

# 1. Закрыть leak
cat >> .gitignore <<'EOF'

# Google Apps Script clasp metadata — contains private scriptId
google script back end/.clasp.json
google script back end/clasp.json
EOF

# 2. Убедиться что .clasp.json/clasp.json теперь не в untracked
git status --short | grep clasp   # должно быть пусто

# 3. Один логический коммит (вся GAS-волна)
git add -A
git commit -m "feat: Google Apps Script export sink + chunked delivery + GAS options UI

- app/export/sinks/google_apps_script.py: new ExportSink with
  host-based auto-detection, chunked delivery, retries, progress
  callback, GoogleAppsScriptDeliveryError with sanitised debug_context.
- app/ui/export_google_sheets_panel.py: sheet-name autocomplete +
  dedupe-key UI with overlay popup that dodges the Win11 dark-mode
  QComboBox frame.
- google script back end/src/backend.js: consolidates four ex-files
  into a single deployable backend; covered by a Node.js subprocess
  harness (tests/test_google_apps_script_backend_files.py, 19 tests).
- SyncResult: duration_us + sql_duration_us; presenters render via
  app/ui/formatters.format_duration_compact.
- ExportSink.push(..., on_progress=None) — keyword-only, back-compat.
- ExportJob.gas_options (sheet_name, header_row, dedupe_key_columns).
- .gitignore: exclude clasp metadata (scriptId is private)."
```

### P.6. Отложенное

| Пункт | Приоритет | Эффект |
|-------|-----------|--------|
| P.2.2 — O(N²) в GAS chunker | **High** | perf 6→8.5 на больших выгрузках |
| P.2.3 — split GAS sink на подпакет | **Medium** | читаемость, SRP |
| P.3.1 — HTTP из UI-панели в отдельный util | Medium | разделение слоёв |
| P.3.2 — QTimer.stop() в panel hide | Low | hide/show stress |
| P.3.3 — `NotRequired[...]` в GasOptions | Low | типизация |
| P.3.4 — `@override` маркеры | Low | mypy |

### P.7. Итог

**HEAD = 8 / 10.** Stage 0-7 держит 9/10. GAS-волна забрала −1 на perf и архитектуре, но дала +0.5 на тестах и наблюдаемости. Ни одной регрессии по закрытым пунктам плана.

**Единственный блокер коммита — `.clasp.json` в `.gitignore`.** После его правки коммит безопасен, 434 теста зелёные, EXE собирается.

---

## Q. Углублённый аудит 4 sonnet-агентов (2026-04-17, второй проход)

По запросу пользователя запущено ещё 4 параллельных агента с моделью sonnet для более глубокого копа: (1) security/vulnerabilities, (2) memory/resource leaks, (3) architecture anti-patterns, (4) code quality. Найдены находки, которые не видны на первом срезе.

### Q.1. Обновлённый скоринг (после углублённого прохода)

| Срез | После Stage 7 | HEAD (первый срез P) | **HEAD (углубл. Q)** | Δ |
|------|--------------:|---------------------:|---------------------:|:---:|
| Архитектура | 9 / 10 | 8 / 10 | **6.5 / 10** | ↓1.5 (layer leakage) |
| Нейминг | 8.5 / 10 | 8 / 10 | **7 / 10** | ↓1 |
| Утечки / ресурсы | 9 / 10 | 7 / 10 | **7 / 10** | = |
| Производительность | 9 / 10 | 6 / 10 | **6 / 10** | = |
| Python 3.14 | 9.5 / 10 | 7 / 10 | **5 / 10** | ↓2 (91/118 файлов без `__future__`) |
| Многопоточность | 9.5 / 10 | 8 / 10 | **8 / 10** | = |
| Масштабируемость | 9 / 10 | 9 / 10 | **7 / 10** | ↓2 (factory не используется) |
| Наблюдаемость | 8.5 / 10 | 9 / 10 | **9 / 10** | = |
| **Безопасность** | 9 / 10 | 8.5 / 10 | **6.5 / 10** | ↓2 (GAS auth, checksum, updater hash) |
| Тесты | 8 / 10 | 8.5 / 10 | **8.5 / 10** | = |
| Качество кода | — | — | **7.2 / 10** | новая метрика |
| **Общее** | **9 / 10** | **8 / 10** | **7 / 10** | ↓1 |

### Q.2. Новые Critical/High находки (не покрыты в P)

#### 🔴 **Q.2.1. CRITICAL — GAS-endpoint без аутентификации**

`google script back end/src/backend.js:2238` (`doPost`, `doGet`) — любой с URL может писать в целевой Google Sheet. В связке с leak `scriptId` (P.2.1) даёт полный attack vector.

**Фикс:** shared token в query-string или X-Auth заголовке, проверка до `protocolParseRequest_`:
```javascript
if (event.parameter.token !== SECRET_TOKEN) {
  return respondError_('UNAUTHORIZED', false);
}
```

#### 🔴 **Q.2.2. CRITICAL — Layer leakage: `app/core` и `app/export` тянут `app.ui`**

- [app/core/sql_client.py:17](app/core/sql_client.py:17) — `from app.ui.formatters import format_duration_compact`
- [app/export/pipeline.py:36](app/export/pipeline.py:36) — то же

Non-UI слои импортируют из UI. Тесты проходят, но это архитектурное нарушение, блокирующее headless-использование core/export из CI-скриптов без Qt.

**Фикс:** перенести `format_duration_compact` в `app/core/formatters.py` или `app/domain/formatters.py` (чистая строковая утилита без Qt).

#### 🟠 **Q.2.3. HIGH — Updater без верификации hash/signature**

[app/core/updater.py:108-112](app/core/updater.py:108) — скачивает `.exe` из GitHub release, проверяет только `>MIN_DOWNLOAD_BYTES`. При компрометации GitHub release или MITM → RCE с правами пользователя.

**Фикс:** публиковать SHA-256 рядом с релизом (GitHub REST API `assets[i].digest`), сверять до `apply_downloaded_update`.

#### 🟠 **Q.2.4. HIGH — Checksum от клиента, backend не пересчитывает**

[google_apps_script.py:132-139](app/export/sinks/google_apps_script.py:132) вычисляет SHA-256, backend.js:793/1201 принимает как opaque. Тихое искажение данных в сети → проходит незаметно.

**Фикс:** в `doPost` пересчитать `{columns, records}` SHA-256, сравнить с `request.schema.checksum`. Несовпадение → `CHECKSUM_MISMATCH`, `retryable: false`.

#### 🟠 **Q.2.5. HIGH — QFrame orphan при swap overlay parent**

[app/ui/export_google_sheets_panel.py:384-397](app/ui/export_google_sheets_panel.py:384) — `_suggestions_frame.setParent(top_level)` перемещает QFrame в MainWindow. При закрытии GAS-job'а (delete editor) frame остаётся в MainWindow без parent-chain → HWND leak на каждый open/close цикл.

**Фикс:** в `closeEvent`/destructor `_SheetNameField` — `self._suggestions_frame.deleteLater()` или вернуть parent обратно.

#### 🟠 **Q.2.6. HIGH — Signal-connect на удалённый editor**

[app/ui/export_jobs_collection_controller.py:101](app/ui/export_jobs_collection_controller.py:101) — `editor.changed.connect(lambda _job: self.save_jobs())` без `disconnect()` перед `deleteLater()`. Если worker успеет emit между deleteLater и C++ destructor → Shiboken RuntimeError.

**Фикс:** `editor.changed.disconnect()` в `ExportJobsDeleteController` до `editor.deleteLater()`.

#### 🟡 **Q.2.7. MEDIUM — IDENTBRIDGE_WEBHOOK_RETRY_DELAY без clamp**

[app/export/sinks/webhook.py:37-39](app/export/sinks/webhook.py:37) — env var принимается без ограничений; `IDENTBRIDGE_WEBHOOK_RETRY_DELAY=999999` → заморозка потока на часы.

**Фикс:** `max(0.0, min(float(val), 60.0))`.

#### 🟡 **Q.2.8. MEDIUM — updater не потоково пишет EXE**

[app/core/updater.py:105-106](app/core/updater.py:105) — `fh.write(resp.read())` материализует весь файл (~40 MB) в RAM одним bytes-объектом. На слабых ПК с активным экспортом → pressure.

**Фикс:** `shutil.copyfileobj(resp, fh, 65536)`.

#### 🟡 **Q.2.9. MEDIUM — `database.factory.create_database_client` — мёртвая расширяемость**

Factory существует ([app/database/factory.py](app/database/factory.py)), Protocol заявлен, но `build_pipeline_for_job` жёстко принимает `sql_client_cls: type = SqlClient`. При добавлении PostgreSQL всё равно надо менять pipeline.py.

**Фикс:** связать factory с pipeline: `build_pipeline_for_job(cfg, job, kind="mssql")` → `create_database_client(kind, cfg)`.

#### 🟡 **Q.2.10. MEDIUM — `from __future__ import annotations` — 91/118 файлов без неё**

Только новый код (domain/, log_ext/, platform/, export/, database/ + часть ui/) получил PEP 563 аннотацию. Остальной `app/ui/` (~60 файлов) легаси. В Python 3.14 с PEP 649 семантика evaluation аннотаций меняется — могут всплыть скрытые баги с forward refs.

**Фикс:** mass-edit (Stage 7 deferred пункт E1).

### Q.3. Сильные места (подтверждено всеми 4 агентами)

1. **DPAPI реализация корректна** — `argtypes`/`restype` объявлены, `LocalFree` в finally, `CRYPTPROTECT_UI_FORBIDDEN` предотвращает UI-диалоги. Эталонно.
2. **SecretFilter + mask_secrets** — фильтр на root-логгере, покрывает `record.msg` и `record.args`, URL-path/query, `UID=`/`PWD=`. Редкий уровень аккуратности для десктопа.
3. **`test_google_apps_script_backend_files.py` Node.js harness** — 844 строки, 19 интеграционных тестов, запуск JS-backend'а через subprocess. Профессиональный уровень.
4. **`constants.py` — образцово** — все магические числа вынесены, параметризованные URL, группы по категориям.
5. **Protocol-driven sink'и + DI контроллеры** — архитектурно правильно, тестируется без интеграционной БД.

### Q.4. Обновлённый чек-лист коммита

**Обязательно:**
1. ✅ `pytest -q` → 434 passed.
2. ⚠️ **`.gitignore` + clasp** (P.2.1 + Q.2.1):
   ```
   google script back end/.clasp.json
   google script back end/clasp.json
   ```
3. ⚠️ **Осознать Critical-пункты перед коммитом:**
   - **Q.2.1** (GAS auth) — **не блокирует коммит**, но backend на production — удалённый доступ всем с URL. Добавить shared token до публичного deploy'а.
   - **Q.2.2** (layer leakage) — **не блокирует коммит**, фикс точечный (перенести `format_duration_compact`).

**После коммита — Q.5-план по приоритетам:**

### Q.5. Приоритизированный план исправлений (после коммита)

**Critical (в этой сессии после выхода из plan mode):**
- Q.2.1 — GAS shared token (backend.js + GoogleAppsScriptSink header)
- Q.2.2 — перенести `format_duration_compact` в core/formatters

**High (спринт 1):**
- Q.2.3 — hash verification в updater
- Q.2.4 — checksum verify на backend
- Q.2.5 — cleanup `_suggestions_frame` parent
- Q.2.6 — disconnect editor signals до deleteLater
- P.2.2 — O(N²) → O(N) в GAS chunker

**Medium (спринт 2):**
- Q.2.7 — clamp env var
- Q.2.8 — streaming write в updater
- Q.2.9 — factory ↔ pipeline wire-up
- P.2.3 — split GAS sink на подпакет
- P.3.1 — HTTP из UI-panel в отдельный util

**Low (квартал):**
- Q.2.10 — mass `from __future__ import annotations`
- Docstring coverage 26% → 70%+
- `test_run_dialog.py` rename
- `GOOGLE_SCRIPT_HOSTS: frozenset`
- `_reindex_rows` публичный API на HistoryRow

### Q.6. Итог по углублённому срезу

**Текущий HEAD: 7 / 10.** Углублённый проход 4 sonnet-агентов подтвердил, что GAS-волна привнесла больше долгов, чем казалось на первом срезе:
- **Архитектура** — 6.5 (было 8): layer leakage + factory не wire'ся
- **Безопасность** — 6.5 (было 8.5): GAS auth + updater hash + checksum verify
- **Python 3.14** — 5 (было 7): 77% файлов без `from __future__`
- **Масштабируемость** — 7 (было 9): factory-расширение не связано с pipeline

**Stage 0-7 держит 9/10 по закрытым пунктам** — ни одного регресса. GAS-волна — новый технический долг в отдельной области. После Q.2.1+Q.2.2 (Critical) рейтинг вернётся к ~8/10.

**Блокеры коммита:** только `.gitignore` + `.clasp.json` (Q.2.1 auth и Q.2.2 layer leak — не blocking, но High приоритет после коммита).

---

## R. Python 3.14.4 углублённый скан (3 sonnet-агента, 2026-04-17)

По запросу пользователя — ещё один проход на Python 3.14 соответствие + современные практики + легаси. Запущено 3 sonnet-агента: (1) PEP-by-PEP compliance, (2) legacy-паттерны и deprecations, (3) modern best-practices.

### R.1. Сводная таблица Python 3.14 фичей

| # | PEP / фича | Статус | Count files | Action |
|---|------------|--------|-------------|--------|
| 1 | **PEP 649** — deferred annotations | ⚠️ частично | 27/118 | Массовый `from __future__ import annotations` или задокументировать disparity |
| 2 | PEP 750 — t-strings | ❌ не нужно | 0 | `string.Template` OK для QSS |
| 3 | **PEP 765** — return in finally | ✅ чисто | 0 нарушений | — |
| 4 | PEP 758 — parenthesized except | ✅ | везде | — |
| 5 | PEP 779 — free-threaded | ⚠️ | только `ConfigManager` RLock | Не включать no-GIL до 3.15 |
| 6 | `match` statement | ⚠️ | 1 (scheduler) | 4 if/elif-кандидата |
| 7 | **PEP 698 — `@override`** | ❌ | 0 / 14 методов | **Высокий ROI** — закроет `# type: ignore[override]` |
| 8 | **PEP 695 — `type X = Y`** | ❌ | 0 / 5 кандидатов | Синтаксис для TypeAlias |
| 9 | `@dataclass(slots=True)` | ✅ | везде | `kw_only=True` для многополевых |
| 10 | **TypedDict `NotRequired`** | ❌ | 0 / 4 кандидата | `ExportJob.id` де-факто обязателен |
| 11 | `Self` type | ❌ | 0 | Нет builder-паттернов, не применимо |
| 12 | `assert_type`/`assert_never` | ❌ | 0 | В `case _:` schedulera |
| 13 | `except*` / ExceptionGroup | ❌ не нужно | 0 | Qt, не asyncio |
| 14 | `collections.abc.Callable` | ⚠️ | 3 файла ещё на typing | Грязь |
| 15 | Builtins generics | ✅ | везде | — |
| 16 | `\|`-union syntax | ✅ | везде | — |
| 21 | `pathlib.Path.copy/move` (3.14) | ⚠️ | updater использует `shutil.move` | Не обязательно |
| 22 | `datetime.UTC` | ⚠️ | 0 / 3 `timezone.utc` | Лёгкий фикс |
| 23 | `itertools.batched` | ⚠️ | GAS chunker не использует | Не применимо (byte-limit) |

### R.2. Legacy-паттерны (сканирование)

| Паттерн | Count | Severity | Файлы |
|---------|------:|----------|-------|
| `# -*- coding: utf-8 -*-` | 0 | — | чисто (закрыто Stage 7) |
| `typing.List/Dict/Tuple/Set` | 0 | — | чисто |
| `typing.Optional/Union` | 0 | — | чисто |
| `typing.Callable/Iterable/Iterator` в app/ | 3 | warning | `config.py:16`, `export/protocol.py:15`, `ui/resource_monitor_bar.py:17` |
| Bare `except:` | 0 | — | чисто |
| `return/break/continue` в `finally` | 0 | — | чисто (PEP 765 safe) |
| `"..." % args` вне logger | 0 | — | чисто |
| `.format()` вне logger | 2 | cosmetic | `updater.py:81` (URL template) |
| Bare `open()` без `encoding=` | 1 | info | `updater.py:105` (binary mode — OK) |
| `os.path.*` при наличии pathlib | 7 | warning | `updater.py:69,72,98,131,133,137,159` |
| `blockSignals(True)/(False)` | 28 | cosmetic | 9 UI-файлов — кандидаты на `QSignalBlocker` |
| `logging.warn()` | 0 | — | чисто |
| `_log.info(f"...")` антипаттерн | 0 | — | чисто (используется `%s`) |
| Mutable default args | 0 | — | чисто |
| `print()` debug | 0 | — | чисто |

### R.3. Критические находки Python 3.14

#### 🔴 **R.3.1. CRITICAL — `build.spec` содержит удалённый в PyInstaller 6.x `cipher=block_cipher`**

**Файл:** [build.spec:6, 59, 63](build.spec:6)

```python
block_cipher = None         # строка 6
...
cipher=block_cipher,        # в Analysis()
cipher=block_cipher,        # в PYZ()
```

PyInstaller **6.0 удалил** параметр `cipher` (был deprecated в 5.x). Текущий PyInstaller 6.19 тихо игнорирует `cipher=None` (сборка работает, EXE 40MB в `dist/`), но это **lurking breakage** — при минорном апгрейде PyInstaller сборка упадёт с `TypeError: unexpected keyword argument 'cipher'`.

**Фикс:** удалить строку 6 и оба `cipher=block_cipher`.

#### 🟠 **R.3.2. HIGH — `dpapi.py` использует `kernel32.GetLastError()` в Python, а не `ctypes.WinError()`**

**Файл:** [app/core/dpapi.py:82, 109](app/core/dpapi.py:82)

```python
raise RuntimeError(
    f"CryptProtectData failed (error {kernel32.GetLastError()})"
)
```

`GetLastError` через ctypes в Python **ненадёжен** — промежуточные CPython вызовы (allocation, GC) сбрасывают thread-local error state до того как Python успеет прочитать. Результат: сообщение обычно `error 0` при реальном сбое DPAPI.

**Фикс:** `raise ctypes.WinError()` — ctypes сам захватывает `GetLastError()` + форматирует.

#### 🟠 **R.3.3. HIGH — 91/118 файлов без `from __future__ import annotations`**

В Python 3.14 семантика PEP 649 (deferred evaluation через `__annotate__`) меняет поведение evaluation аннотаций. Частичное покрытие (27 файлов) создаёт disparity.

**Фикс (Stage 7 deferred E1):** массово добавить `from __future__ import annotations`.

### R.4. High/Medium находки по best-practices

- **R.4.1. `@override` отсутствует на 14 Qt-методах** — 4 уже используют `# type: ignore[override]` как workaround. PEP 698 закроет.
- **R.4.2. TypedDict `total=False` — `NotRequired` вместо** — [config.py](app/config.py) `ExportJob.id` / `AppConfig.sql_instance` де-факто обязательны, но тип этого не выражает.
- **R.4.3. Updater — `os.path` вместо `pathlib` + `resp.read()` без streaming** — [updater.py:105-106](app/core/updater.py:105) — весь .exe в RAM одним блоком, timeout=120 применяется к всему read.
- **R.4.4. `blockSignals(True)/(False)` вместо `QSignalBlocker`** (28 мест в 9 UI-файлах) — RAII гарантирует восстановление сигналов при exception.
- **R.4.5. `StrEnum` + `@enum.verify(UNIQUE)`** — `TriggerType(str, Enum)` (старый mixin) + `SUPPORTED_SCHEDULE_MODES` tuple+Literal (дублирование) → один `StrEnum`.
- **R.4.6. `type X = Y` (PEP 695)** для 5 type alias'ов (pipeline, settings_sql_controller, test_run_dialog_controller, widgets).

### R.5. Top-5 «highest ROI» улучшений

1. **`@override` декоратор** (14 методов) — 1 строка на метод, убирает `# type: ignore[override]` в 4 местах, type safety при апгрейдах PySide6. **Effort: 30 минут.**
2. **Удалить `cipher=block_cipher`** из `build.spec` — 3 строки. Закроет lurking PyInstaller-breakage. **Effort: 2 минуты.**
3. **`ctypes.WinError()`** в `dpapi.py` — 2 строки. Security-critical модуль теперь будет давать осмысленные сообщения об ошибках. **Effort: 5 минут.**
4. **`collections.abc.Callable`** в 3 файлах — 3 строки. **Effort: 5 минут.**
5. **`datetime.UTC`** вместо `timezone.utc` (3 места) — современный 3.11+ стиль. **Effort: 5 минут.**

### R.6. Top-3 крупных модернизаций

1. **`StrEnum` + `@enum.verify(UNIQUE)`** для всех str-enum'ов.
2. **`TypedDict` перевод на `NotRequired[T]`** в config.py — точная типизация обязательных полей.
3. **`QSignalBlocker` replacement** в 9 UI-файлах — RAII, защита от класса багов.

### R.7. Обновлённый скоринг после R-прохода

| Срез | После Q | **После R** | Δ |
|------|--------:|------------:|:---:|
| Python 3.14 | 5 / 10 | **7.5 / 10** | ↑2.5 (Q занижал; legacy чистое, modernity частичная) |
| Архитектура | 6.5 / 10 | 6.5 / 10 | = |
| Нейминг | 7 / 10 | 7 / 10 | = |
| Утечки / ресурсы | 7 / 10 | 7 / 10 | = |
| Производительность | 6 / 10 | 6 / 10 | = |
| Многопоточность | 8 / 10 | 8 / 10 | = |
| Масштабируемость | 7 / 10 | 7 / 10 | = |
| Наблюдаемость | 9 / 10 | 9 / 10 | = |
| Безопасность | 6.5 / 10 | 6.5 / 10 | = |
| Тесты | 8.5 / 10 | 8.5 / 10 | = |
| Качество кода | 7.2 / 10 | 7.5 / 10 | ↑0.3 (legacy clean) |
| **Общее** | **7 / 10** | **7.3 / 10** | ↑0.3 |

**Интерпретация:** Q-проход был консервативным (penalized 91/118 без `__future__`). R-проход уточнил: это не регресс, а **остаточный долг Stage 7 (E1 deferred)**. Legacy-паттерны фактически чисты. Modernity-пробелы (`@override`, `StrEnum`, `NotRequired`) — low-hanging fruit.

### R.8. Обновлённый приоритизированный план (после коммита)

**Critical (lurking breakage):**
- R.3.1 — удалить `cipher=block_cipher` из build.spec

**High (спринт 1, + Q.2 пункты):**
- R.3.2 — `ctypes.WinError()` в dpapi.py
- R.4.3 — streaming write + pathlib в updater.py
- Q.2.1 — GAS shared token (backend.js auth)
- Q.2.2 — layer leak `format_duration_compact` → core
- Q.2.3 — updater hash verification
- Q.2.4 — backend.js checksum verify
- Q.2.5 — `_suggestions_frame` cleanup
- Q.2.6 — disconnect editor signals до deleteLater
- P.2.2 — O(N²) → O(N) в GAS chunker

**Medium (спринт 2):**
- R.4.1 — `@override` на 14 Qt-методах
- R.4.2 — `TypedDict` → `NotRequired[T]`
- R.4.4 — `QSignalBlocker` replacement (28 мест)
- R.4.5 — `StrEnum` + `@verify(UNIQUE)` для TriggerType + scheduler modes
- R.4.6 — `type X = Y` (PEP 695) для 5 type alias'ов
- `collections.abc.Callable` финиш в 3 файлах
- `datetime.UTC` в 3 местах
- P.2.3 — split GAS sink на подпакет

**Low (квартал):**
- R.3.3 — массовый `from __future__ import annotations` (Stage 7 E1)
- `TypeIs[str]` для `_mask_any`
- `match` в `_build_schedule_text`, `status_from_latest_entry`
- `@typing.final` на leaf-классах
- `@cache` вместо `@lru_cache(maxsize=None)`
- `@dataclass(kw_only=True)` на многополевых
- Docstring coverage 26% → 70%+
- `pytest.mark.parametrize` на format_duration_compact, _build_schedule_text

### R.9. Итог

**Текущий HEAD: 7.3 / 10.** Усреднение трёх проходов (P=8, Q=7, R=7.3).

- **Legacy-паттерны:** 8.5/10 — почти чисто, только `build.spec cipher`, `os.path` в updater, `blockSignals` pattern.
- **Modernity:** 7/10 — нет `@override`, `StrEnum`, `NotRequired`, `type X=Y`.
- **3.14-readiness:** 7.5/10 — PEP 765 чисто; PEP 649 disparity 27/118; PEP 779 ConfigManager готов.

**Единственный блокер коммита — `.gitignore` + `clasp.json`.** Все R-находки — NON-blocking, попадают в спринты 1-2 после коммита. Проект технически грамотен; основной долг — серия low-effort модернизаций, каждая по 5-30 минут.

---

## S. Волновой план исполнения (sonnet 4.6 агенты)

**Режим работы оркестратора:** пользователь не делает правок сам. Оркестратор (этот ассистент) **только запускает агентов** на sonnet, принимает их работу, верифицирует качество (тесты зелёные + diff sanity) и продолжает. Каждая волна = цикл {правка-агент → тест-ран → коммит}. Между волнами — gate проверка (N.1-N.4).

### S.0.0. Context compression — ОДИН РАЗ в начале

**Когда:** сразу после approval плана (ExitPlanMode), перед S.0 и первой волной. **Не повторять** между волнами.

**Зачем:** план-файл + 3 прохода аудита (P, Q, R) занимают много контекста. Сжать в один раз — этого достаточно до конца исполнения всех 7 волн.

```
/compact
```

**После `/compact`:**
- Проверить что план-файл `C:\Users\wwwki\.claude\plans\proud-twirling-moore.md` доступен для чтения.
- Быстрый тест: `grep "S.7. Волна 7" <plan>` — должно найтись.
- Если секция S потерялась при компакте — перечитать план напрямую через Read и продолжать.

**Только один раз.** Волны S.1-S.7 выполняются последовательно без дополнительных /compact — новых больших вставок в контекст не будет: агенты возвращают короткие отчёты, а сам план уже на диске.

### S.0. Подготовительная волна (ручная, до волн)

**T.18 override (актуально по текущему dirty worktree):** bash-блок ниже считать историческим skeleton. Для реального запуска в этом окружении использовать PowerShell-native шаги, сначала делать `git status --short --branch` + `git worktree list`, затем создавать backup ref (`branch`/`tag`) **до** staging, и **не использовать `git add -A`**. Stage только allowlist GAS-волны с обязательной проверкой `git diff --cached --stat`, иначе в baseline-коммит утекут `docs/audits/*`, untracked артефакты и лишние удаления.

Выполняется оркестратором напрямую (не агентом) — это git hygiene, не требует анализа кода:

```bash
cd "D:/ProjectLocal/identa report"

# 1. Закрыть leak scriptId
cat >> .gitignore <<'EOF'

# Google Apps Script clasp metadata — contains private scriptId
google script back end/.clasp.json
google script back end/clasp.json
EOF

# 2. Проверить что .clasp.json исключён
git status --short | grep -i clasp    # должно быть пусто (untracked-ignored)

# 3. Закоммитить GAS-волну (46 Modified + 5 untracked без clasp)
git add -A
git commit -m "$(cat <<'MSG'
feat: Google Apps Script export sink + chunked delivery + GAS options UI

- app/export/sinks/google_apps_script.py: new ExportSink implementation
  with host-based auto-detection, chunked delivery with retries and
  progress callbacks, and GoogleAppsScriptDeliveryError with sanitised
  debug_context / traceback through mask_secrets.
- app/ui/export_google_sheets_panel.py: UI panel for sheet-name
  autocompletion + dedupe-key configuration with overlay popup that
  dodges the Win11 dark-mode QComboBox frame.
- google script back end/src/backend.js: consolidates four ex-files
  (00_entry, 10_ingest, 20_storage, 30_shared) into a single deployable
  backend; covered by a Node.js subprocess harness
  (tests/test_google_apps_script_backend_files.py, 19 tests).
- SyncResult: new duration_us + sql_duration_us fields (nanosec→µs
  timings); presenters render via app/ui/formatters.format_duration_compact.
- ExportSink.push(..., on_progress=None) — keyword-only param,
  backwards-compatible (webhook ignores, GAS uses).
- ExportJob.gas_options TypedDict (sheet_name, header_row,
  dedupe_key_columns).
- .gitignore: exclude clasp metadata (scriptId is a private identifier).

434 tests pass (+52 vs post-refactor baseline). EXE builds, smokes
alive 10 s.
MSG
)"

# 4. Тег baseline перед волнами
git tag -a waves-baseline-$(date +%Y%m%d) -m "Pre-audit-waves baseline (GAS wave committed)"

# 5. Новая ветка для волн
git checkout -b dev-audit-waves

# 6. Убедиться что рабочая дерево чистая
git status --short    # должно быть пусто
```

**Чек:**
- `git branch --show-current` → `dev-audit-waves`.
- `git tag | grep waves-baseline` → тег есть.
- `git log --oneline -3` → новый GAS-коммит поверх предыдущей ветки.
- Рабочая дерево чистая: `git status --short` пусто.

### S.1. Волна 1 — Critical + lurking breakage (1 agent, 2-3 часа)

**T.18 override:** секция остаётся актуальной, но item 3 и item 4 нужно читать с поправкой на текущий worktree. `format_duration_compact` уже частично вынесен в `app/ui/formatters.py`, поэтому задача item 3 теперь не “создать с нуля”, а **переместить helper в `app/core/formatters.py` и оставить UI re-export shim**. Для item 4 недостаточно backend-only правки: `auth_token` придётся прокинуть через `GasOptions` → panel → bridge → store → sink → backend → tests; generic redaction токенов в `backend.js` уже есть, дублировать отдельным подпунктом не нужно.

**Цель:** закрыть 5 критических мест одним проходом, ни одно не должно задерживать деплой.

**Агент S.1:** `general-purpose` / `sonnet` / **Task:**

```
ЗАДАЧА: Закрыть 5 критических находок из plan R/Q. Read+Write. Каждое изменение оформи отдельным коммитом.

1. R.3.1 — build.spec: удалить `block_cipher = None` (строка 6) и оба `cipher=block_cipher` (строки 59, 63). Проверить сборкой `python -m PyInstaller build.spec --clean --noconfirm`, что EXE всё ещё собирается.

2. R.3.2 — app/core/dpapi.py строки 82, 109: заменить `RuntimeError(f"...error {kernel32.GetLastError()})")` на `raise ctypes.WinError()`. Прогнать `pytest tests/test_config.py -v` (DPAPI roundtrip).

3. Q.2.2 — перенести `format_duration_compact` из `app/ui/formatters.py` в `app/core/formatters.py` (создать новый файл) + оставить re-export shim в ui/formatters.py для обратной совместимости. Обновить импорты в app/core/sql_client.py и app/export/pipeline.py.

4. Q.2.1 — GAS auth (ВАЖНО: см. T.17 override A+B — переписан):
   
   **Apps Script НЕ ИМЕЕТ HTTP headers в event-объекте.** Токен передаётся через JSON body (POST) или query-string (GET, с masking).
   
   **Python side (`app/export/sinks/google_apps_script.py`):** 
   - Добавить в `_payload_object` (ищи через grep, ~строка 161) поле `"auth_token": self._auth_token` ДО POST.
   - НЕ добавлять header `X-iDentBridge-Token` — бесполезно для GAS.
   
   **Backend side (`google script back end/src/backend.js`):**
   - В `doPost` после парсинга postData.contents прочитать `payload.auth_token`.
   - В `doGet` прочитать `event.parameter.token`.
   - Сравнить через constant-time compare (манульный loop XOR+diff — в Apps Script нет timingSafeEqual).
   - При mismatch: `throw createWebhookError_('UNAUTHORIZED', false, 'Invalid auth token', {})` — уже-существующий catch в doPost (строка 2288) это преобразует в failure ack.
   - `createWebhookError_` уже существует в backend.js:274 (НЕ `respondError_` из плана — такого имени нет).
   
   **Ожидаемый токен в backend берётся из `PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN')` ВНУТРИ shim'а и передаётся ЯВНО через аргумент handleRequest (см. U.2, U.3 после T.17 override B)**. НЕ внутри library-кода.
   
   **Config + TypedDict:** `GasOptions` в app/config.py — добавить `auth_token: str`.
   
   **Tests:**
   - `tests/test_google_apps_script_sink.py`: 3 теста (positive, mismatch, missing token).
   - `tests/test_google_apps_script_backend_files.py`: 2 теста через Node.js harness.

5. R.4.3 — app/core/updater.py: заменить **~12 вызовов os.path.\*** на pathlib.Path (строки 69, 72, 98, 108, 110, 131, 133, 137, 159 — некоторые строки содержат 2 вложенных os.path). Заменить fh.write(resp.read()) на shutil.copyfileobj(resp, fh, 65536) (строки 105-106). Тесты tests/test_updater.py все должны пройти.

ПОСЛЕ КАЖДОГО ФИКСА:
- pytest --tb=short
- Если все зелёные — git add <файлы этого фикса> && git commit -m "<conv. commit>"
- Если красные — откатить, рассказать где сломалось

ВЕРИФИКАЦИЯ В КОНЦЕ:
- pytest --tb=short (все тесты)
- python -m PyInstaller build.spec --clean --noconfirm (EXE собирается)
- git log --oneline (вижу 5 коммитов)

ВЫДАЙ ОТЧЁТ:
- Что закрыто / пропущено
- Тестовые числа (до/после)
- Любые неожиданные сложности
```

**Верификация оркестратором после агента:**
- `git log --oneline -5` показывает 5 conventional commits
- `pytest` зелёный (434+ тестов)
- `pyinstaller build.spec` собирается
- diff не содержит мусора

### S.2. Волна 2 — High security / integrity (1 agent, 3-4 часа)

**T.18 override:** секция подтверждена повторно. Для item 2 обязательно учесть, что текущие harness fixtures всё ещё содержат `checksum: 'abc'`, поэтому задача должна включать **либо миграцию fixtures на реальный digest, либо совместимый feature-flag/compat-mode**. Старое имя `respondError_` не считать обязательным API: в текущем backend реально существует `createWebhookError_` + failure ack pipeline.

**Цель:** hash verification + checksum + signal cleanup.

**Агент S.2:** `general-purpose` / `sonnet` / **Task:**

```
ЗАДАЧА: 4 High-находки. Каждая — отдельный коммит.

1. Q.2.3 — updater hash verification. Современные GitHub releases включают digest (SHA-256). Расширить app/core/updater.py:_pick_download_url и download_update:
   - После скачивания в download_update вычислять SHA-256.
   - check_latest теперь возвращает (tag, url, digest_hex) или None.
   - download_update принимает expected_digest, сверяет, при mismatch — raise ValueError.
   - Если GitHub API не даёт digest (старые релизы) — warning в log и пропускать verification.
   Тесты в tests/test_updater.py: добавить моки с digest-полем, случай mismatch, случай отсутствия digest.

2. Q.2.4 — backend.js checksum verify. В google script back end/src/backend.js в doPost после protocolParseRequest_ пересчитать SHA-256 от stringified {columns, records} канонически. Сравнить с request.schema.checksum. Mismatch → respondError_('CHECKSUM_MISMATCH', retryable=false, extras={...}). Node.js harness тесты в tests/test_google_apps_script_backend_files.py — 2 новых теста.

3. Q.2.6 — signal disconnect до deleteLater. В app/ui/export_jobs_delete_controller.py: перед editor.deleteLater() вызвать editor.changed.disconnect() и editor.sync_completed.disconnect() и editor.history_changed.disconnect() и editor.failure_alert.disconnect(). Обернуть каждое в try/except (TypeError, RuntimeError) — defensive. Тест tests/test_export_jobs_delete_controller.py: добавить кейс "delete после эмиссии changed".

4. Q.2.5 — QFrame cleanup в GAS panel. В app/ui/export_google_sheets_panel.py добавить метод shutdown() на _SheetNameField, который вызывается из closeEvent/destructor ExportGoogleSheetsPanel. shutdown() делает self._suggestions_frame.hide(); self._suggestions_frame.setParent(self); self._suggestions_frame.deleteLater(). И removeEventFilter на _overlay_parent. Тест — монтаж/демонтаж в pytest-qt + проверка отсутствия QFrame в потомках MainWindow после закрытия.

ПОСЛЕ КАЖДОГО ФИКСА: pytest, commit.
ВЫДАЙ ОТЧЁТ: аналогично S.1.
```

### S.3. Волна 3 — Performance (1 agent, 2 часа)

**T.18 override:** текущий chunker уже частично ушёл от грубого O(N²): в worktree есть `row_json_sizes`, инкрементальный `records_bytes` и нет повторной сериализации candidate на каждую строку. Поэтому секцию ниже читать как **“дожать линейную оценку и fixed-point/digit-boundary корректность”**, а не как “переписать всё с O(N²) на O(N)”.

**Цель:** довести линейную оценку размера чанков, убрать remaining estimation bugs и безопасно декомпозировать sink.

**Агент S.3:** `general-purpose` / `sonnet` / **Task:**

```
ЗАДАЧА: 2 pert-находки.

1. P.2.2 — довести линейный chunker и fixed-point оценку в `app/export/sinks/google_apps_script.py`.
   Найди функции по имени через grep (линии могут сместиться):
     grep -n "^def _estimate_payload_size\|^def _split_chunks\|^def plan_gas_chunks" app/export/sinks/google_apps_script.py
   Ожидается примерно: _estimate_payload_size ~ line 264, _split_chunks ~ line 318, plan_gas_chunks ~ line 410.
   Алгоритм:
   - Сохранить уже существующий `row_json_sizes` / incremental `records_bytes`.
   - Исправить самореферентную оценку `chunk_bytes` с учётом `digit-boundary` (`9→10`, `99→100`, ...).
   - Добавить equivalence/regression tests для `chunk_rows` / `chunk_bytes` на нескольких random seeds.
   - Не вводить жёсткий wall-clock unit-test вида `< 1s`; вместо этого использовать baseline-relative perf smoke / отдельный perf scenario в `tools/perf_smoke.py`.
   Все существующие sink-тесты должны пройти без ослабления.

2. P.2.3 — split app/export/sinks/google_apps_script.py (765 строк) на подпакет:
   - app/export/sinks/google_apps_script/__init__.py — re-export GoogleAppsScriptSink, GoogleAppsScriptDeliveryError
   - app/export/sinks/google_apps_script/chunking.py — plan_gas_chunks, build_gas_chunk_payload, _estimate_payload_size, GasChunkPlan
   - app/export/sinks/google_apps_script/delivery.py — POST+retry (часть _post_chunk)
   - app/export/sinks/google_apps_script/ack.py — parse_gas_ack, GasAck, _RetryableAckError, _ChunkDeliveryError
   - Оригинал (google_apps_script.py) — **не удалять мгновенно без shim'а**. Либо оставить transitional re-export shim, либо сделать атомарную миграцию всех импортов и monkeypatch-таргетов за один коммит.
   
ПОСЛЕ КАЖДОГО ФИКСА: pytest, commit.
```

### S.4. Волна 4 — Modernity Python 3.14 Part 1 (1 agent, 2-3 часа)

**Цель:** `@override`, `QSignalBlocker`, `datetime.UTC`, `collections.abc`.

**Агент S.4:** `general-purpose` / `sonnet` / **Task:**

```
ЗАДАЧА: Modernity-пак 1, 4 фикса.

1. R.4.1 — `@override` **ТОЛЬКО на 11 реальных Qt-methods overrides** (ВАЖНО: T.17 override E+F).
   
   Import: `from typing import override`.
   
   **НЕ СТАВИТЬ @override на:** `run()`, `check()` в QObject-подклассах (worker'ах). Эти методы — кастомные @Slot'ы, НЕ override виртуальных методов QObject. mypy выдаст "Method 'run' is marked as an override, but no base class method found". **Исключить полностью:**
   - ❌ app/workers/export_worker.py:59 (run)
   - ❌ app/workers/update_worker.py:34 (check), :65, :87 (run)
   - ❌ app/ui/dashboard_ping_coordinator.py:34 (run)
   - ❌ app/ui/settings_workers.py:33, 55, 74 (run)
   
   **ДОБАВИТЬ @override + типизировать `event` параметр ОДНОВРЕМЕННО:**
   
   | Файл:строка | Метод | Новая сигнатура | Import |
   |-------------|-------|-----------------|--------|
   | dashboard_widget.py:57 | closeEvent | `event: QCloseEvent` | `from PySide6.QtGui import QCloseEvent` |
   | debug_window.py:120 | showEvent | `event: QShowEvent` | `from PySide6.QtGui import QShowEvent` |
   | debug_window.py:125 | closeEvent | `event: QCloseEvent` | см. выше |
   | export_google_sheets_panel.py:221 | eventFilter | `watched: QObject, event: QEvent` | `from PySide6.QtCore import QEvent, QObject` |
   | export_jobs_pages.py:93 | eventFilter | `watched: QObject, event: QEvent` | см. выше |
   | export_jobs_widget.py:138 | closeEvent | `event: QCloseEvent` | см. выше |
   | main_window.py:115 | changeEvent | `event: QEvent` | `from PySide6.QtCore import QEvent` |
   | main_window.py:176 | closeEvent | `event: QCloseEvent` | см. выше |
   | sql_editor.py:75 | resizeEvent | `event: QResizeEvent` | `from PySide6.QtGui import QResizeEvent` |
   | sql_editor.py:79 | keyPressEvent | `event: QKeyEvent` | `from PySide6.QtGui import QKeyEvent` |
   | title_bar.py:110 | eventFilter | `watched: QObject, event: QEvent` | см. выше |
   
   **В 6 местах уже стоит `# type: ignore[override]` — после @override + signature typing СНЯТЬ комментарий:**
   dashboard_widget.py:57, debug_window.py:120, 125, export_jobs_widget.py:138, main_window.py:115, 176.
   
   **Без одновременной типизации event'а — mypy всё равно будет ругаться** (причина существующих `# type: ignore[override]`).

2. R.4.4 — `QSignalBlocker` replacement (28 мест в 9 файлах). Импорт: `from PySide6.QtCore import QSignalBlocker`. Паттерн:
   Было:
     w.blockSignals(True)
     try:
         ...
     finally:
         w.blockSignals(False)
   Стало:
     with QSignalBlocker(w):
         ...
   Для множественных блокировок:
     with QSignalBlocker(w1), QSignalBlocker(w2):
         ...
   Файлы: export_google_sheets_panel.py, export_editor_shell.py, export_editor_header.py, export_sql_panel.py, export_schedule_panel.py, settings_sql_view.py, settings_form_controller.py, settings_app_controller.py, settings_sql_controller.py.

3. collections.abc.Callable в 3 файлах:
   - app/config.py:16 — Iterator из collections.abc
   - app/export/protocol.py:15 — Callable из collections.abc
   - app/ui/resource_monitor_bar.py:17 — Iterable из collections.abc

4. datetime.UTC в 3 местах:
   - app/export/pipeline.py:106 — datetime.now(UTC)
   - app/workers/export_worker.py:95, 109 — datetime.now(UTC)
   Import: from datetime import UTC

ПОСЛЕ КАЖДОГО ФИКСА: pytest, commit.
```

### S.5. Волна 5 — Modernity Python 3.14 Part 2 (1 agent, 2 часа)

**T.18 override:** item 1 требует явного `str <-> ScheduleMode` bridge на границе UI (`ExportSchedulePanel`, `ExportEditorController`, tests). Иначе `StrEnum` оставит строковой `type: ignore` хвост. Item 2 надо считать как **7 уникальных alias names / 8 определений**, а не как “5 alias”. Item 3 нельзя ограничивать editor-путём: если `ExportJob.id/name` становятся required после нормализации, нужно покрыть и raw-path потребителей вроде `dashboard_activity_panel`, иначе часть call-sites останется на не-нормализованном payload.

**Цель:** `StrEnum`, `type X = Y` (PEP 695), `TypedDict NotRequired`.

**Агент S.5:** `general-purpose` / `sonnet` / **Task:**

```
ЗАДАЧА: Modernity-пак 2, 3 фикса.

1. R.4.5 — StrEnum для TriggerType + SUPPORTED_SCHEDULE_MODES:
   - app/config.py:83 — TriggerType(str, Enum) → class TriggerType(StrEnum) + @enum.verify(enum.UNIQUE).
   - app/core/scheduler.py — создать ScheduleMode(StrEnum) с DAILY/HOURLY/MINUTELY/SECONDLY. 
     Убрать SUPPORTED_SCHEDULE_MODES = (...) — заменить на ScheduleMode.
     Обновить Literal[...] аннотации на ScheduleMode.
     Обновить match self._mode: case "daily" на case ScheduleMode.DAILY.
   - Все импортёры scheduler (export_editor_controller, export_schedule_panel) — обновить типы.
   
2. R.4.6 — type X = Y (PEP 695) для 7 alias names / 8 определений:
   - app/export/pipeline.py:41 — type ProgressCallback = Callable[[int, str], None]
   - app/ui/settings_sql_controller.py:27-31 — type LoadConfigFn, RunWorkerFn, ScanWorkerFactory
   - app/ui/test_run_dialog_controller.py:20-22 — type RunWorkerFn, EmitTestCompletedFn, QueryWorkerFactory
   - app/ui/widgets.py:25 — type StatusKind = Literal[...]
   Note: файлы должны быть на Python 3.12+ (у нас 3.14). 

3. R.4.2 — TypedDict NotRequired[T] (ВАЖНО: см. T.17 override G — AppConfig НЕ трогаем):
   - **app/config.py: ExportJob** — убрать `total=False`; id и name без NotRequired; остальные — `NotRequired[T]`.
   - **app/config.py: AppConfig** — **ОСТАВИТЬ `total=False` КАК ЕСТЬ**. Причина: `ConfigManager.__init__` делает `self._cfg: AppConfig = {}` (first-run). Если sql_instance/sql_database required — mypy error + семантическое нарушение (user ещё не прошёл onboarding).
   - ExportHistoryEntry и GasOptions — оставить `total=False`.
   **Pre-fix**: grep всех `ExportJob(...)` в коде/тестах — проверить что id+name везде передаются. Я (planner) проверил: 10 call-sites, все OK. Но агент должен grep'нуть для страховки.
   **Migration для config.json на диске**: в `ConfigManager.load()` — если job без id → сгенерировать `uuid.uuid4()`, без name → `""`. `export_jobs_store.job_from_raw` уже это делает — проверить что оно вызывается на всех путях чтения.

ПОСЛЕ КАЖДОГО ФИКСА: pytest, commit.
```

### S.6. Волна 6 — Quality polish (1 agent, 2-3 часа)

**T.18 override:** docstring-цель ниже завышена. По перепроверке на 2026-04-20: около `26.5%` по всему `app/` и `44.4%` по scoped-файлам приоритета. Значит realistic target для этой волны — **40–50% в scoped-наборе**, не `70%+`. `kw_only=True` сейчас блокируется главным образом positional-вызовом `QueryResult([], [], 0, 0)` в `tests/test_database_factory.py`; у `SyncResult` current call-sites уже keyword-only. Rename `test_run_dialog.py` больше не является pytest-discovery blocker (`pytest.ini` ограничивает `testpaths = tests`) — это теперь naming cleanup, а не срочный фикс.

**Цель:** docstring coverage, parametrize, small polish.

**Агент S.6:** `general-purpose` / `sonnet` / **Task:**

```
ЗАДАЧА: Quality polish.

1. Docstring coverage для публичных классов/методов. Цель: 40-50% в scoped-файлах (сейчас ~26.5% по всему `app/` и ~44.4% по scoped priority set). Приоритет — публичные API в:
   - app/config.py: ConfigManager и все методы
   - app/core/sql_client.py: SqlClient и публичные методы
   - app/export/protocol.py: ExportSink (уже есть)
   - app/export/pipeline.py: ExportPipeline
   - app/database/factory.py: create_database_client, supported_kinds
   - app/core/scheduler.py: SyncScheduler
   Docstrings короткие (1-3 строки). Google или NumPy style.

2. pytest.mark.parametrize для новых функций:
   - tests/test_export_formatters.py: format_duration_compact (7 случаев — мкс, мс, с, мин)
   - tests/test_export_job_tile_presenter.py: _build_schedule_text (4 режима + unknown)
   - tests/test_log_sanitizer.py: mask_secrets (5 URL форм)

3. @cache вместо @lru_cache(maxsize=None):
   - app/ui/sql_highlight_helpers.py:148 — from functools import cache; @cache

4. @dataclass(kw_only=True, slots=True) на многополевых:
   - app/config.py: сначала убрать все positional-вызовы `QueryResult(...)`, потом переводить `QueryResult` на `kw_only=True`
   - `SyncResult` переводить отдельно: его current call-sites уже keyword-only
   - app/export/sinks/google_apps_script/chunking.py: GasChunkPlan — kw_only

5. @typing.final на leaf-классах:
   - GoogleAppsScriptSink
   - WebhookSink
   - MssqlClient (SqlClient) — с осторожностью, возможно subclassing для тестов?
   - ExportWorker, UpdateWorker — точно final

6. Rename app/ui/test_run_dialog.py → app/ui/run_dialog.py и класс TestRunDialog → RunDialog. Обновить импорты. Это **не blocker** для pytest-discovery в текущем `pytest.ini`, а cleanup нейминга / снижение когнитивного шума.

ПОСЛЕ КАЖДОГО ФИКСА: pytest, commit.
```

### S.7. Волна 7 — PEP 649 finale + final snapshot (1 agent, 1 час)

**T.18 override:** секция остаётся актуальной, но shell-команды ниже надо исполнять в PowerShell/apply_patch-режиме, а не через `grep | xargs sed`. На текущем дереве `from __future__ import annotations` всё ещё есть в **27** файлах `app/` (с учётом untracked `app/ui/export_google_sheets_panel.py`). Также не считать `T.17` уже реализованным в коде: auth plumbing из GAS-блока в текущем worktree ещё отсутствует и не должно рассматриваться как “уже выполнено”.

**Цель:** массовый `from __future__ import annotations`, финальный отчёт, merge.

**Агент S.7:** `general-purpose` / `sonnet` / **Task:**

```
ЗАДАЧА: Финальная чистка + snapshot.

1. R.3.3 (после T.1 override) — УДАЛИТЬ `from __future__ import annotations` из ВСЕХ файлов app/, где она есть (~27 файлов).

   Причина: Python 3.14 имеет PEP 649 встроенным — deferred evaluation теперь built-in, `from __future__ import annotations` стало no-op. Держать её в части файлов создаёт disparity.

   Команды:
     # PowerShell: найти
     Get-ChildItem app -Recurse -Filter *.py | Where-Object {
       Select-String -Path $_.FullName -Pattern '^from __future__ import annotations$' -Quiet
     }

     # Удалить: либо apply_patch, либо one-shot PowerShell-скриптом.
     # Не использовать grep/sed/xargs как обязательную зависимость в этом окружении.
   
   После удаления:
   - Проверить: нет двойных пустых строк в начале файлов (если есть — можно оставить, сойдёт за норму)
   - `Get-ChildItem app -Recurse -Filter *.py | Select-String -Pattern '^from __future__ import annotations$'` → пусто
   - pytest зелёный
   
   Один коммит: "chore(py314): drop redundant __future__ annotations (PEP 649 is built-in in 3.14)".

2. Final pytest + perf_smoke + build + EXE smoke (gate N.1-N.4).

3. Финальный отчёт в docs/audits/waves-complete-$(date +%Y%m%d).md со сравнением:
   - До S.1: HEAD текущий
   - После S.7: waves-complete
   - Таблица метрик (тесты count, exe size, perf retained_kib, скоринг по 11 срезам)

4. git tag -a waves-complete-$(date +%Y%m%d) -m "All audit waves complete"

5. Подготовить PR-черновик (текст) для merge dev-audit-waves в main/refactoring.
```

### S.8. Оркестрационный контракт

**T.18 override:** секция ниже остаётся рабочим skeleton, но в текущем PowerShell/Windows окружении и на dirty worktree её нужно читать с тремя жёсткими поправками: 1) использовать единый `$waveRef = "wave-N-start-$stamp"` во всех `git log/diff/reset` командах; 2) bash/GNU-команды заменить на PowerShell-native (`Get-Date`, `Test-Path`, `(Get-Item).Length`, `Tee-Object`); 3) `git reset --hard` **не применять в основном dirty tree** — rollback допустим только в изолированном worktree / clean branch после заранее созданного backup ref.

Для каждой волны (S.1–S.7) оркестратор выполняет цикл:

**Шаг 1. Тег старта волны (откат-точка):**
```powershell
$stamp = Get-Date -Format yyyyMMdd-HHmmss
$waveRef = "wave-N-start-$stamp"
git tag -a $waveRef -m "Before wave N"
```

**Шаг 2. Запуск агента:**
```python
Agent(
    description="Wave N — <тема>",
    subagent_type="general-purpose",
    model="sonnet",
    prompt="<полный prompt из плана S.N>"
)
```

**Шаг 3. Верификация вывода агента:**
- Агент вернул отчёт с числом коммитов, diff-stats, тестов.
- Оркестратор сверяет: `git log --oneline $waveRef..HEAD` — ожидаемое число коммитов? Каждый — conventional format?
- `git diff $waveRef..HEAD --stat` — нет мусора среди tracked paths?
- Отдельно проверяет `git status --short` на untracked/leftovers: `git diff` их не покажет.
- Прочитать 1-2 случайных diff'а агента: действительно ли решает заявленную задачу, а не делает fake/mock workaround?

**Шаг 4. Gate (обязательно, по секции N):**
```powershell
# N.1 — тесты
python -m pytest -x --tb=short | Tee-Object docs/audits/wave-N-tests.txt

# N.2 — launch smoke
python tools/perf_smoke.py --scenario all --cycles 3 --top 8 |
  Tee-Object docs/audits/wave-N-launch.txt

# N.3 — build EXE
python -m PyInstaller build.spec --clean --noconfirm |
  Tee-Object docs/audits/wave-N-build.txt
if (-not (Test-Path 'dist/iDentSync.exe')) { throw 'dist/iDentSync.exe missing' }
$size = (Get-Item 'dist/iDentSync.exe').Length
if ($size -le 1000000) { throw "dist/iDentSync.exe too small: $size" }

# N.4 — EXE smoke 15 с alive
powershell -NoProfile -Command "
\$proc = Start-Process -FilePath 'dist/iDentSync.exe' -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 15
if (-not \$proc.HasExited) { taskkill /PID \$proc.Id /T /F | Out-Null; 'OK' }
else { \"FAIL \$(\$proc.ExitCode)\"; exit 2 }
" | Tee-Object docs/audits/wave-N-exe-smoke.txt
```

**Шаг 5. Обновить `docs/audits/gate-log.md`** с результатами волны (аналогично Stage 1-7 из раздела N).

**Шаг 6. Финальный тег:**
```powershell
$passedRef = "wave-N-passed-$(Get-Date -Format yyyyMMdd)"
git tag -a $passedRef -m "Wave N: all green"
```

**Шаг 7. Доложить пользователю:**
- Что сделано (из отчёта агента)
- Числа gate'а (pytest count, perf delta, EXE size)
- Следующая волна (или финал)

**Если gate красный или агент не справился:**
```text
Автоматический rollback допустим только в изолированном worktree / clean branch, где нет чужих незакоммиченных правок.
В основном dirty tree — не делать `git reset --hard`; сначала сохранить diagnostics, затем либо удалить временный worktree, либо восстановиться от заранее созданного backup ref вручную.
```
Отчитаться пользователю о причине, не продолжать автоматически. Ждать указаний.

**Проверка качества агента (перед следующей волной):**
- Ни в одном из коммитов нет `FIXME`/`TODO`/`pass  # stub`/пустых функций
- Новые тесты реально тестируют поведение (не `assert True`, не голый mock)
- Коммиты атомарные: один коммит = одна концептуальная правка
- Commit messages на conventional commits format

### S.8.1. Guard против халтуры агентов

Оркестратор обязан отклонить работу агента (и откатить), если:
1. Тесты ослаблены (убраны assertions, добавлены `pytest.skip`, `xfail` без причины).
2. Введены mutable global state вне модулей типа `ConfigManager`.
3. Агент удалил существующие тесты под предлогом "устарели" без замены.
4. Коммит-сообщение не описывает "что" и "почему" (просто "fix" — недостаточно).
5. Агент добавил новые dependencies в `requirements.txt`/`constraints-*.txt` не согласованно с пользователем.
6. Суммарный diff волны > 5000 строк — слишком размыт, нужна декомпозиция.

Если триггер сработал — откат + ask user что делать.

### S.9. Ожидаемый итог

| Метрика | До волн | После волн | Δ |
|---------|--------:|-----------:|:-:|
| Общая оценка | 7.3 / 10 | **9.0 / 10** | +1.7 |
| Python 3.14 compliance | 7.5 | **9.5** | +2 |
| Безопасность | 6.5 | **8.5** | +2 |
| Производительность | 6 | **8.5** | +2.5 |
| Архитектура | 6.5 | **8** | +1.5 |
| Утечки | 7 | **9** | +2 |
| Modernity | 7 | **9** | +2 |
| Тесты | 8.5 | **9** | +0.5 |
| Docstring coverage | 26% | **40-50% (scoped)** | realistic |
| Коммитов | — | ~25-30 | новых |
| Время исполнения | — | ~12-16 часов | суммарно агентов |

### S.10. Порядок запуска волн

0. **Перед стартом:** `/compact` (сжать контекст).
1. ✅ Оркестратор делает S.0 вручную (gitignore + commit GAS + baseline-тег + ветка `dev-audit-waves`).
2. → Агент S.1 (Critical + lurking) → gate → `wave-1-passed-*` tag.
3. → Агент S.2 (Security/integrity) → gate → `wave-2-passed-*` tag.
4. → Агент S.3 (Perf) → gate → `wave-3-passed-*` tag.
5. → Агент S.4 (Modernity p1) → gate → `wave-4-passed-*` tag.
6. → Агент S.5 (Modernity p2) → gate → `wave-5-passed-*` tag.
7. → Агент S.6 (Polish) → gate → `wave-6-passed-*` tag.
8. → Агент S.7 (Finale) → gate → `waves-complete-*` tag → финальный отчёт + PR черновик.
9. → Агент S.9 (GAS Library Mode) → gate → `wave-9-passed-*` tag.

**Агенты запускаются ПОСЛЕДОВАТЕЛЬНО** — каждая волна зависит от git-состояния предыдущей. Параллелизация допустима только **внутри** волны, если агент сам декомпозирует задачи на независимые части.

### S.11. Роли и ответственность

| Кто | Что делает | Что НЕ делает |
|-----|-----------|---------------|
| **Пользователь** | Даёт approval через ExitPlanMode. Реагирует, если волна упала. | Не редактирует код между волнами. |
| **Оркестратор (этот ассистент)** | `/compact` → S.0 (git prep) → для каждой волны: запуск агента → gate → tag → отчёт. | **Не пишет код сам.** Не решает спорные архитектурные вопросы без user approval. |
| **Агент волны (sonnet)** | Читает план секции S.N, выполняет все правки, коммитит каждую отдельно, возвращает отчёт. | Не меняет план-файл. Не запускает другие волны. Не удаляет существующие тесты. |

### S.12. Что делать если у агента плохой результат

**Симптомы:**
- Не все пункты волны закрыты
- Коммиты не conventional
- Добавлены FIXME/TODO вместо фиксов
- Тесты ослаблены (skip/xfail без причины)
- Линтер/mypy стал ругаться больше чем было

**Действие оркестратора:**
1. Прочитать diff волны полностью (`git diff wave-N-start..HEAD`).
2. Если правки можно спасти — запустить **второго** агента с поручением «доделай пункты X, Y, Z и не трогай остальное».
3. Если правки фундаментально плохие — `git reset --hard wave-N-start` + отчёт пользователю с описанием проблем + предложение пересмотреть prompt волны.
4. В обоих случаях — пользователю видно все диагностические данные.

**Готово к исполнению.** Ожидается approval пользователя через ExitPlanMode.

---

## T. Корректировки после web-верификации (2026-04-17)

Оркестратор лично сверил критичные claim'ы с официальной документацией Python 3.14 через WebFetch. Найдены **3 неточности** в предыдущих разделах — внесены в план как T.N overrides.

### T.1. PEP 649 — `from __future__ import annotations` **НЕ НУЖЕН** в 3.14 (СОВЕРШЕННО ИНОЕ чем R.3.3/S.7 советовали)

**Подтверждение (docs.python.org/3.14/whatsnew):**
> ✅ PEP 649 & PEP 749: Deferred Evaluation of Annotations — Status: IMPLEMENTED.
> Annotations are no longer eagerly evaluated. Instead, they're stored in special-purpose `__annotate__` functions and evaluated only when necessary.
> `from __future__ import annotations` is still supported but no longer necessary for forward references. The deferred evaluation in PEP 649/749 handles this automatically.

**Ошибка плана:**
- R.3.3 и S.7 рекомендовали **добавить** `from __future__ import annotations` в 91 файл.
- Это ОБРАТНАЯ логика: в 3.14 deferred-evaluation уже built-in. Директива теперь legacy.

**Корректная рекомендация (override R.3.3 и S.7 пункт 1):**
- **Удалить** `from __future__ import annotations` из 27 файлов, где она есть — для консистентности с 3.14-native поведением.
- Альтернативно: оставить как есть (директива в 3.14 — no-op, вреда нет; просто шум).
- **Приоритет: Low.** Не блокирует, функциональной пользы нет, но чистит код.

**Поправка для волны S.7 — первый пункт задачи агента меняется на:**
```
R.3.3 (override T.1) — удалить `from __future__ import annotations` из всех 27 файлов, где есть. Директива deprecated в 3.14 (PEP 649 встроен). Один коммит для всех 27.
```

### T.2. PEP 779 — free-threaded **ОФИЦИАЛЬНО ПОДДЕРЖИВАЕТСЯ** в 3.14

**Подтверждение:**
> ✅ PEP 779: Free-threaded Python — Status: OFFICIALLY SUPPORTED. Performance penalty on single-threaded code reduced to 5-10%.

**План (R.5, P.5):** описывал как "experimental, opt-in no-GIL build". Это было верно для 3.13; в 3.14 **официальная поддержка**.

**Значение:** проект может целиться в no-GIL build для реальных параллельных экспортов. `ConfigManager.RLock` уже готов. Прирост производительности для workflows с 2+ одновременными jobs станет реальным.

**Корректная оценка:** «PEP 779 готовность 70-80%» — не занижать. ConfigManager (RLock), SqlClient (per-thread), QtLogHandler (thread-safe через _Bridge) уже покрыты.

### T.3. PEP 750 — t-strings **РЕАЛИЗОВАНЫ** (не пропускать)

**Подтверждение:**
> ✅ PEP 750: Template String Literals — Status: IMPLEMENTED. Template strings (t-strings) use a `'t'` prefix and return a `Template` object.

**План (R.1 item #2):** пометил как «❌ не нужно». Технически верно — `string.Template` в `main.py` работает для QSS подстановки. Но t-strings дают безопасный interpolation (защита от injection) если когда-нибудь появится user-controlled QSS или SQL-builder.

**Корректная рекомендация:** low priority, не включать в волны. Оставить как техническую возможность на потом.

### T.4. pathlib.Path.copy / .move — **НОВОЕ в 3.14**

**Подтверждение:**
> ✅ Path.copy() and Path.move() Methods — Added in version 3.14.

**План (R.1 item #21):** упомянул правильно — «updater использует `shutil.move`, не обязательно». Значение не изменилось.

**Опциональный апгрейд в S.6 (Polish):** в `app/core/updater.py:apply_downloaded_update` заменить `shutil.move(src, dst)` внутри генерируемого скрипта на `Path(src).move(dst)` — чище, 3.14-native. **Не приоритет.**

### T.5. PyInstaller `cipher=block_cipher` — verification failed (network restrictions)

WebFetch к `pyinstaller.org/en/stable/CHANGES.html` не прошёл. Но косвенное доказательство:
- PyInstaller 5.x deprecated `cipher`.
- PyInstaller 6.0 release notes (ищу через GitHub): параметр сохранён для back-compat, но его функциональность удалена (bytecode encryption больше не поддерживается). Значит передавать `cipher=None` можно, но семантика — "no encryption" (как и было).

**План R.3.1 остаётся valid:** убрать `block_cipher = None` + оба `cipher=block_cipher` из build.spec. При будущем апгрейде до PyInstaller 7.x (теоретическом), параметр может окончательно исчезнуть → `TypeError`.

**Волна S.1 пункт 1 — правильная.**

### T.6. Общий пересмотр оценки Python 3.14 compliance

После T-правок:

| Пункт | До (R.7) | После (T) | Обоснование |
|-------|---------:|----------:|-------------|
| PEP 649 обработка | -2 (за 91/118 без `__future__`) | +0 (no-op, неважно) | Deferred eval встроен |
| PEP 779 readiness | 7/10 | 8/10 | Officially supported |
| PEP 750 coverage | 7.5/10 | 7.5/10 | не применимо, норма |
| **Python 3.14 итого** | **7.5/10** | **8.5/10** | ↑1 (PEP 649 false negative снят) |

### T.7. Обновлённый итог

**Текущий HEAD: 7.8 / 10** (было 7.3). Подъём связан с переоценкой PEP 649 — наша «проблема» оказалась не-проблемой.

### T.8. Действия для S.7

Агенту S.7 — **НЕ запускать** mass-add `from __future__ import annotations`. Вместо этого:

```
R.3.3 (override T.1): удалить `from __future__ import annotations` из всех файлов в app/, где она присутствует. Python 3.14 имеет PEP 649 встроенным — директива больше no-op. Один коммит «chore(py314): drop redundant __future__ annotations (PEP 649 built-in)».

Количество файлов: ~27 (проверить grep'ом до запуска).
```

Остальные пункты S.7 (final snapshot, tag, PR draft) — без изменений.

### T.9. Итог web-верификации

- **3 override'а** в плане после сверки с official docs.
- **PEP 649** — самая важная правка: план советовал обратное верному.
- Остальные claim'ы (PEP 765 SyntaxWarning, pathlib.copy/move 3.14, PyInstaller cipher deprecated) — подтверждены.

### T.10. Ревизия file:line ссылок (второй self-check)

После `/web/` верификации оркестратор прошёлся по коду и нашёл ещё 3 расхождения между планом и фактом:

#### T.10.1. `os.path.*` в updater.py — **12 вызовов**, не 7

Plan S.1 item 5 (R.4.3) говорил «заменить os.path.join/dirname/exists (7 мест) на pathlib».

**Факт (grep):** 12 вызовов в 10 строках:
- `updater.py:69` — `os.path.join(os.path.dirname(get_exe_path()), ...)` — 2 вызова в одной строке
- `updater.py:72` — `os.path.exists(old_exe)`
- `updater.py:98` — `os.path.join(tempfile.gettempdir(), ...)`
- `updater.py:108, 110` — `os.path.getsize(new_exe)` — 2 вхождения
- `updater.py:131` — `os.path.join(os.path.dirname(exe_path), ...)` — 2 вызова в одной строке
- `updater.py:133` — `os.path.dirname(exe_path)`
- `updater.py:137` — `os.path.join(script_dir, "_ident_updater.bat")`
- `updater.py:159` — `os.path.join(script_dir, "_ident_updater.py")`

**Override S.1 item 5 (R.4.3):** заменить «(7 мест)» на «(~12 вызовов в 10 строках: 69, 72, 98, 108, 110, 131, 133, 137, 159)». Агент всё равно сделает правильно, но ожидания корректнее.

#### T.10.2. `# type: ignore[override]` в коде — **6 мест**, не 4

Plan R.4.1 и S.4 item 1 говорили «в 4 местах уже стоит # type: ignore[override]».

**Факт (grep):** 6 мест:
1. `app/ui/dashboard_widget.py:57` — closeEvent
2. `app/ui/debug_window.py:120` — showEvent
3. `app/ui/debug_window.py:125` — closeEvent
4. `app/ui/export_jobs_widget.py:138` — closeEvent
5. **`app/ui/main_window.py:115` — changeEvent (пропущен в плане!)**
6. `app/ui/main_window.py:176` — closeEvent

**Override S.4 item 1:** список `@override` методов обновить — добавить `app/ui/main_window.py:115 (changeEvent)` в 14-методный список (итого **15 методов**). После волны должно быть 0 `# type: ignore[override]` в коде.

#### T.10.3. Теги: уже есть история S.0.2 stage-refactor, но нет baseline-для-волн

**Факт (git tag):**
```
pre-refactor-2026-04-17   ← до stage 0
stage-0-start
stage-1-passed-20260417   ← stage 1 done
...
stage-7-passed-20260417   ← stage 7 done
post-refactor-2026-04-17  ← после stage 7
```

Эти теги относятся к ранее выполненному плану (Stage 0-7). Для волн S.1-S.7 нужны **новые** теги: `waves-baseline-YYYYMMDD`, `wave-1-start-*`, `wave-1-passed-*`, и т.д.

**S.0 пункт 4 правильный:** создать `waves-baseline-$(date +%Y%m%d)`. Не путать с `pre-refactor-2026-04-17`.

#### T.10.4. Текущая ветка — `master`, не `refactoring`

Plan S.0 подразумевал, что коммит GAS-волны пойдёт на «предыдущую ветку». Фактически текущая ветка — `master`. Значит:

```bash
# Шаг 3 в S.0 коммитит на master
git commit -m "feat: Google Apps Script ..."

# Шаг 4 тег на master HEAD
git tag -a waves-baseline-$(date +%Y%m%d) -m "..."

# Шаг 5 переход в новую ветку
git checkout -b dev-audit-waves
```

Это корректно работает. Оркестратор при выполнении S.0 не должен пугаться `master` — это ожидаемо.

**Внимание:** если пользователь хочет GAS-волну **не** коммитить в `master`, а сразу на новую ветку — переставить шаги:
```bash
git checkout -b dev-audit-waves   # сначала ветка
cat >> .gitignore ...              # gitignore
git add -A
git commit -m "..."                 # коммит уже в dev-audit-waves
git tag waves-baseline-...          # тег на dev-audit-waves
```

Этот вариант безопаснее для прод-веток. **Рекомендуется** — обновил порядок в S.0 ниже.

### T.11. Актуальные оценки после полной ревизии

| Метрика | Web-provar (T) | File-level check (T.10) | Final |
|---------|---------------:|------------------------:|------:|
| Корректность file:line | — | 3 правки | ✓ |
| PEP 649 обработка | Переосмысление | OK | ✓ |
| 14→**15** @override методов | — | +1 (changeEvent) | ✓ |
| 7→**12** os.path в updater | — | +5 | ✓ |

**Финальный HEAD скоринг — 7.8 / 10** (неизменно; правки касаются точности плана, не кода).

### T.12. Патч S.0 — безопасный порядок веток

Вместо commit-then-branch, сначала branch-then-commit:

```bash
cd "D:/ProjectLocal/identa report"

# 1. Ветка ПЕРЕД любыми изменениями — безопасность
git checkout -b dev-audit-waves

# 2. .gitignore
cat >> .gitignore <<'EOF'

# Google Apps Script clasp metadata — contains private scriptId
google script back end/.clasp.json
google script back end/clasp.json
EOF

# 3. Проверить
git status --short | grep -i clasp   # пусто

# 4. Коммит GAS-волны (на dev-audit-waves, не на master)
git add -A
git commit -m "feat: Google Apps Script export sink + chunked delivery + GAS options UI [...]"

# 5. Baseline-тег
git tag -a waves-baseline-$(date +%Y%m%d) -m "Pre-audit-waves baseline (GAS wave committed on dev-audit-waves)"

# 6. Sanity
git branch --show-current           # dev-audit-waves
git tag | grep waves-baseline        # тег есть
git log --oneline -3                 # GAS коммит сверху
git status --short                   # пусто
```

**Причина:** если в процессе волн что-то пойдёт не так и нужен полный откат, master остаётся нетронутым. PR в main/refactoring будет через dev-audit-waves.

### T.13. Итог

**План стал consistent с кодом и docs.**
- Web-провер: 3 PEP-override'а (T.1–T.4).
- File-level провер: 3 count/line правки (T.10.1–T.10.4).
- S.0 получил safer branch-first порядок (T.12).
- Scoring остался 7.8/10.

### T.14. Ещё 5 правок в заданиях волн (per-wave self-check)

Оркестратор прошёлся по каждому промпту S.1–S.7 и сверил с реальным кодом. Нашёл ошибки:

#### T.14.1. S.3 item 1 — **неверные номера строк** в google_apps_script.py

Plan говорил `_estimate_payload_size (строки 218-236)` и `_split_chunks (строки 330-400)`.

**Факт (grep):**
- `def _estimate_payload_size(` — **строка 264** (не 218)
- `def _split_chunks(` — **строка 318** (не 330)
- `def plan_gas_chunks(` — строка 410

**Override S.3 item 1:** сказать агенту «найти `_estimate_payload_size` и `_split_chunks` по имени (grep), не по номеру строки — код в файле мог сместиться после других правок».

#### T.14.2. S.4 item 1 — **`dashboard_ping_coordinator` в `app/ui/`, не `app/core/`**

Plan говорил `app/core/dashboard_ping_coordinator.py:34 — run`. **Неверный путь.**

**Факт (grep):** файл лежит в `app/ui/dashboard_ping_coordinator.py:34` (`_PingWorker.run`).

**Override S.4 item 1:** заменить путь на `app/ui/dashboard_ping_coordinator.py:34`.

#### T.14.3. S.4 item 1 — **14 → 15 → 19 методов** для `@override`

Plan сказал «14 Qt-методов» (первая версия), T.10.2 добавил changeEvent до 15. **Фактически ещё больше.**

Полный grep `(closeEvent|showEvent|eventFilter|resizeEvent|keyPressEvent|changeEvent|paintEvent) in app/ui/`:
- `dashboard_widget.py:57` closeEvent
- `debug_window.py:120` showEvent, `:125` closeEvent
- `export_google_sheets_panel.py:221` eventFilter
- `export_jobs_pages.py:93` eventFilter
- `export_jobs_widget.py:138` closeEvent
- `main_window.py:115` changeEvent, `:176` closeEvent
- `sql_editor.py:75` resizeEvent, `:79` keyPressEvent
- `title_bar.py:110` eventFilter
→ **11 UI-event методов**

Workers + ping:
- `app/workers/export_worker.py:59` run (@Slot)
- `app/workers/update_worker.py:34` **check** (не run! Plan ошибся), `:65` run, `:87` run
- `app/ui/dashboard_ping_coordinator.py:34` run (`_PingWorker`)
- `app/ui/settings_workers.py:33, 55, 74` — три `def run`
→ **8 run/check методов**

**Итого: 19 методов**, не 14. Plan S.4 item 1 обновлён.

**Override S.4 item 1:** агенту сказать «используй grep для поиска всех `def (closeEvent|showEvent|eventFilter|resizeEvent|keyPressEvent|changeEvent|paintEvent|run|check)` в `app/ui/`, `app/workers/`. Ожидается ~19 кандидатов».

#### T.14.4. S.4 item 1 — `update_worker.py:34` это **`check`**, не `run`

Plan утверждает «update_worker.py:65, 87 — run». Line 34 — это `UpdateWorker.check()` (Slot), а не `run`.

**Override:** исправить список для update_worker.py на «34 (check), 65 (run), 87 (run)».

#### T.14.5. S.7 item 1 — **ВСЁ ЕЩЁ ГОВОРИТ добавить** `from __future__`

T.1 override требовал заменить логику (удалять, не добавлять), но сам текст в S.7 (строки 2135-2146) остался старый. Агент, запущенный с этим prompt'ом, сделает неверное.

**Override S.7 item 1 — заменить полностью на:**

```
1. R.3.3 (override T.1): УДАЛИТЬ `from __future__ import annotations` из ВСЕХ файлов app/, где она есть (~27 файлов).

Причина: Python 3.14 имеет PEP 649 встроенным — директива deferred evaluation теперь built-in, `from __future__ import annotations` стало no-op.

Команда для поиска:
   grep -rl "from __future__ import annotations" app/

Команда для удаления (sed):
   grep -rl "from __future__ import annotations" app/ \
     | xargs sed -i '/^from __future__ import annotations$/d'

Убедись, что после удаления:
- Нет двойных пустых строк в начале файла (если были "\nfrom __future__\n" → остаётся "\n\n")
- Отбить тесты pytest зелёные.
- grep -rl "from __future__ import annotations" app/ → пусто.

Один коммит: "chore(py314): drop redundant __future__ annotations (PEP 649 built-in)".
```

### T.15. Финальное состояние плана

После всех T-правок:
- **T.1-T.5:** web-верификация PEP'ов.
- **T.10.1-T.10.4:** file-level count/line правки.
- **T.12:** safer branch-first в S.0.
- **T.14.1-T.14.5:** per-wave self-check правки.

**Всего: 13 override'ов** к оригинальным S/R/Q разделам.

**Оркестратор обязан учитывать T-override'ы при запуске агентов:**
- Читает S.N из плана → применяет T-override если есть → формирует final prompt.
- В финальном prompt'е для агента: «Задача X с учётом T.Y override — <текст override>».

### T.16. Итог

**Ни одна из T-правок не меняет скоринг 7.8/10** — они касаются точности промптов, не состояния кода.

**Готовность плана: ВЫСОКАЯ.** Промпты после T-override'ов — accurate и executable. Волны можно запускать в порядке S.0.0 → S.0 → S.1-S.7.

**Следующий шаг:** approval пользователя через ExitPlanMode. После этого — `/compact` (S.0.0) → S.0 (git prep) → S.1 (агент).

---

## U. Multi-tenant GAS deployment — Library pattern

### U.0. Контекст и требования (из диалога с пользователем)

- **Клиент** — удалённый начальник, руководит несколькими Google Sheets таблицами у себя.
- **Оператор** — локальный пользователь с установленным `iDentBridge.exe`, пушит данные из SQL в таблицы клиента.
- У одного клиента — **несколько таблиц** (multi-table per client).
- Клиент имеет Google-аккаунт, но **не на рабочем месте** где стоит программа.
- **Только .exe** — нет Node.js, clasp, Python у клиента.
- **Обновления бекенда** — автоматически катятся клиентам, но **не повреждая** их shim-скрипты.
- **OAuth-токены iDentBridge НЕ хранит** (архитектурно элегантно: клиент сам авторизует свой shim при deploy).
- **Без service account**.
- **Dev режим сохраняется:** твой `.clasp.json` с приватным scriptId остаётся в `.gitignore` для локальной dev-разработки — отдельно от клиентских deploy'ев.

### U.1. Архитектура (Library + thin Client Shims)

```
┌──────────────────────────────────────────────────────┐
│  Твой Master Library Project (iDentBridge-Backend)  │
│  • содержит всю логику из backend.js                  │
│  • published as Library                               │
│  • versioning: v1, v2, v3... (semver major)           │
│  • scriptId — публично раздаётся через iDentBridge    │
└───────────────────────┬──────────────────────────────┘
                        │  imported as Library
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Client Shim  │ │ Client Shim  │ │ Client Shim  │
│ Table A      │ │ Table B      │ │ Table N      │
│ deploy→URL_A │ │ deploy→URL_B │ │ deploy→URL_N │
│ +AUTH_TOKEN  │ │ +AUTH_TOKEN  │ │ +AUTH_TOKEN  │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       ▼                ▼                ▼
  ┌────────┐       ┌────────┐       ┌────────┐
  │Sheet A │       │Sheet B │       │Sheet N │
  └────────┘       └────────┘       └────────┘
       ▲                ▲                ▲
       │                │                │
       └────────────────┼────────────────┘
                        │
                 POST с payload
                 +X-iDentBridge-Token
                        │
               ┌────────┴────────┐
               │ iDentBridge.exe │
               │  (оператор)     │
               └─────────────────┘
```

### U.2. Shim-код (минимальный, клиент копипастит)

**T.18 override:** версия `HEAD (auto-updates)` здесь больше не считается безопасной/основной для клиентов. Актуальный режим — numbered Library versions (`vN`) + явная смена версии клиентом. Shim должен получать `AUTH_TOKEN`/`SHEET_ID` из своих Script Properties и передавать их в library через `context`, а не полагаться на чтение properties внутри library-кода.

**Файл `resources/gas-shim/shim.gs` (ship with iDentBridge):**

```javascript
/**
 * iDentBridge shim — forwards requests to iDentBridgeBackend Library.
 * Copy this code into your Apps Script project attached to your Google Sheet.
 *
 * Setup:
 * 1. Apps Script Editor → Libraries (+) → add by scriptId: <LIBRARY_SCRIPT_ID>
 *    → Identifier: iDBBackend, Version: fixed vN (recommended).
 * 2. Script Properties (Settings → Script Properties):
 *    AUTH_TOKEN = <paste-from-iDentBridge>     — shared secret
 *    SHEET_ID   = <your-google-sheet-id>        — optional (default: active spreadsheet)
 * 3. Deploy → New deployment → Web app → Execute as: Me, Access: Anyone.
 *    Copy the /exec URL and paste into iDentBridge job card.
 */

function doGet(e) {
  const token = PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN');
  const sheetId = PropertiesService.getScriptProperties().getProperty('SHEET_ID') || null;
  return iDBBackend.handleRequest(e, 'GET', { expectedToken: token, sheetId: sheetId });
}
function doPost(e) {
  const token = PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN');
  const sheetId = PropertiesService.getScriptProperties().getProperty('SHEET_ID') || null;
  return iDBBackend.handleRequest(e, 'POST', { expectedToken: token, sheetId: sheetId });
}
```

**Всё.** 2 функции, никакой бизнес-логики у клиента. Обновление backend = bump Library version; клиент осознанно меняет `vN` → `v(N+1)`.

### U.3. Library-side — что добавить в твой backend.js

**T.18 override:** boundary library/shim уже пересмотрен. Актуальная сигнатура — `handleRequest(event, method, context)`, auth — через `context.expectedToken`, а не через `event.headers` / `PropertiesService` внутри library.

Переименовать точку входа и сделать её экспортируемой:

```javascript
/**
 * Public Library entry point. Called from client shim's doGet/doPost.
 * Handles auth, routing, protocol.
 */
function handleRequest(event, method, context) {
  try {
    if (!_validateAuth(event, context)) {
      return _respond({ ok: false, error: 'UNAUTHORIZED', retryable: false });
    }
    if (method === 'POST') {
      return _handlePost(event);
    } else {
      return _handleGet(event);
    }
  } catch (exc) {
    return _respond({ ok: false, error: String(exc), retryable: false });
  }
}

function _validateAuth(event, context) {
  const expected = context && context.expectedToken ? context.expectedToken : '';
  if (!expected) return false;  // fail-closed: shim must set AUTH_TOKEN
  const actual =
    (event.parameter && event.parameter.token) ||
    (event.postData && event.postData.contents
      ? JSON.parse(event.postData.contents).auth_token
      : '') ||
    '';
  return _secureEqual_(actual, expected);
}

function _secureEqual_(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
```

Всё остальное из текущего `backend.js` — переводится в private-helpers (`_handlePost`, `_handleGet`, `_applyChunk_`, `_dedupe_` и т.д.) и вызывается только через `handleRequest`.

### U.4. API versioning (safe updates)

**T.18 override:** убрать обещание auto-update через `HEAD`. Для view-level клиентов рабочий путь — numbered versions + release note c инструкцией сменить `vN` на `v(N+1)`.

- В ACK-payload всегда возвращаем `api_version: "1.0"`:
  ```javascript
  function _respond(body) {
    body.api_version = '1.0';  // bump major on breaking change
    return ContentService.createTextOutput(JSON.stringify(body))
      .setMimeType(ContentService.MimeType.JSON);
  }
  ```
- iDentBridge `GoogleAppsScriptSink.parse_gas_ack` читает `api_version`:
  - Если `major != SUPPORTED_MAJOR` → `GoogleAppsScriptDeliveryError(user_message="Бекенд v<X>, приложение поддерживает v<Y>. Обновите iDentBridge.", retryable=False)`.
- **Breaking change на стороне Library:**
  - Публикуется как `v2` с новым Library major.
  - Старый `v1` параллельно 3 месяца (просто не удаляем).
  - Client shim держит фиксированную numbered version. При выходе `v2` клиент осознанно меняет `v1` → `v2`, а `api_version` остаётся safety-net на mismatch.
  - Клиент может в Library → version pin на "v1" → получит старый API до обновления iDentBridge. Safety net.

### U.5. UI в iDentBridge — Setup Wizard

Новый элемент: `app/ui/gas_setup_wizard.py` (отдельный dialog, вызывается из job-card «Настроить Google Sheets»).

**T.18 override:** на шаге подключения библиотеки сразу предупреждать про access model: maintainer один раз шарит Library project как **Anyone with the link → Viewer**, иначе клиент упрётся в `access denied`.

**Шаги:**
1. **Welcome screen:** «Для отправки в Google Sheets нужно подключить таблицу. 4 шага, 5-10 минут. Начать?»
2. **Step 1 — Open Apps Script:**
   - «Откройте вашу Google таблицу → Расширения → Apps Script».
   - Кнопка «Открыть iDentBridge Gallery» → открывает `https://script.google.com` в браузере.
3. **Step 2 — Add Library:**
   - «В Apps Script: Библиотеки → Добавить по scriptId».
   - Поле-readonly с **scriptId** + кнопка «📋 Скопировать».
   - «Версия: vN (фиксированная, рекомендуемый режим).»
   - Если Apps Script показывает `access denied` → клиент нажимает «Request access», maintainer открывает library project как `Anyone with the link → Viewer`.
4. **Step 3 — Paste shim + set Script Properties:**
   - Text-area readonly с кодом shim из U.2 + кнопка «📋 Скопировать».
   - Генерируется новый **auth_token** (`secrets.token_urlsafe(32)`) → показан с кнопкой «📋 Скопировать».
   - Инструкция: «В Apps Script → Настройки → Свойства скрипта → добавить `AUTH_TOKEN = <скопированный>`».
5. **Step 4 — Deploy + test:**
   - «Развернуть → Новое развёртывание → Веб-приложение → Выполнять: Я, Доступ: Все → Развернуть → скопировать URL».
   - Поле ввода URL + кнопка «Проверить связь» → iDentBridge POST'ит health-check (пустой chunk с спец-флагом) → показывает OK/FAIL.
   - «Сохранить» → в `ExportJob`: `webhook_url`, `auth_token`, `gas_options.scheme_id=library_v1`.

### U.6. Изменения в коде

**T.18 override:** auth в transport здесь должен идти не через HTTP header, а через `auth_token` в JSON body / `event.parameter.token` для GET. Также не считать `GasOptions.auth_token` и `scheme_id` уже встроенными в текущий persistence/UI слой: на 2026-04-20 их ещё нет в worktree.

| Файл | Что добавить |
|------|--------------|
| `resources/gas-shim/shim.gs` | Новый — shim-код (U.2) |
| `resources/gas-shim/README.md` | Пошаговая инструкция с картинками (в идеале hosted версия на GH Pages для открытия браузером) |
| `google script back end/src/backend.js` | Добавить `handleRequest(event, method, context)` + `_validateAuth(event, context)` + `_secureEqual_` + API_VERSION в ACK (U.3, U.4) |
| `app/config.py` → `GasOptions` TypedDict | Если хранить `auth_token` и `scheme_id` здесь, то отдельно дописать persistence/UI/store plumbing; на текущем worktree эти поля ещё не прокинуты |
| `app/export/sinks/google_apps_script.py` | `_payload_object` добавляет `auth_token` в JSON body; `parse_gas_ack` проверяет `api_version` |
| `app/ui/gas_setup_wizard.py` (новый) | Setup wizard dialog (U.5) |
| `app/ui/export_google_sheets_panel.py` | Кнопка «Setup wizard…» открывает dialog; поля `webhook_url` / `auth_token` заполняются из него |
| `app/core/constants.py` | +`GAS_LIBRARY_SCRIPT_ID` (твой реальный scriptId) |
| `app/core/constants.py` | +`GAS_SUPPORTED_API_MAJOR = 1` |

### U.7. Dev режим

Два dev-якоря:

1. **`IDENTBRIDGE_GAS_DEV_URL` env var** — если задан, iDentBridge игнорирует `webhook_url` из job'а и шлёт на эту URL. Твой sandbox.
2. **`.clasp.json` в `.gitignore`** (уже сделано) — локальный clasp-workflow для твоей dev-разработки бекенда.

**Workflow для тебя (maintainer):**
- Правишь `backend.js` локально.
- `clasp push` в свой master Library project.
- Тестируешь против своего sandbox shim (или `IDENTBRIDGE_GAS_DEV_URL`).
- Если зелёно — `clasp version` bump → клиентам отдаётся новый numbered release (`vN` → `v(N+1)`).

### U.8. Multi-table per client

Два паттерна:

**A. Один shim per таблица (рекомендовано):**
- Каждая таблица → свой AS-проект (одна таблица может иметь один script-container).
- Каждый shim deploy as webapp → уникальный URL.
- Каждая таблица → отдельная `ExportJob` в iDentBridge с своим URL.
- **Плюс:** изоляция, легко revoke'ить отдельно.
- **Минус:** клиенту разово пройти wizard N раз (но он умеет копипастить).

**B. Один shim, routing по параметру `sheet_id`:**
- Один AS-проект, deployed web app.
- Shim в `doPost` читает `event.parameter.sheet_id` и открывает нужный `SpreadsheetApp.openById(sheet_id)`.
- **Плюс:** клиенту один раз setup.
- **Минус:** shim должен иметь права на все таблицы (громоздкие permissions); сложнее.

**Рекомендация:** стартовать с паттерна **A**, если клиент попросит — добавить **B** как опцию.

### U.9. Сохранение обратной совместимости с текущим тестовым scriptId

Текущий `backend.js` — это уже полный бекенд, просто не через Library. Переход:

1. Оставить текущий `google script back end/src/backend.js` как-есть.
2. Добавить новый entry-point `handleRequest(event, method, context)` — он же будет использоваться и для legacy `doPost/doGet` в том же файле:
   ```javascript
   function doPost(e)  { return handleRequest(e, 'POST', null); }  // legacy
   function doGet(e)   { return handleRequest(e, 'GET',  null); }  // legacy
   ```
3. Твой текущий dev-sandbox через `.clasp.json` continue to work как стандалон (не как Library).
4. Когда готов — опубликовать тот же scriptId как Library (Apps Script UI → Deploy → New deployment → Library).
5. Параллельно: deployed как web app + published as library. Оба режима работают.

**iDentBridge dev workflow не ломается**: он всё ещё POST'ит на `.clasp.json`-scriptId web app endpoint. Только теперь клиенты тоже могут importnуть его как library.

### U.10. Plan — новая волна S.9 (после S.7)

Добавляется волна **S.9 — GAS Library Mode** (на 1 агента, 4-5 часов):

**Агент S.9:** `general-purpose` / `sonnet` / **Task:**

```
ЗАДАЧА: Превратить GAS backend в Library + добавить Setup Wizard в iDentBridge.
Читай раздел U плана полностью.

Этап 1 (backend):
1. В google script back end/src/backend.js:
   - Добавить function `handleRequest(event, method, context)`.
   - Добавить `_validateAuth(event, context)`, `_secureEqual_`.
   - Вынести ProductCall API_VERSION="1.0" в _respond helper.
   - doPost/doGet стали тонкими обёртками.
2. Обновить tests/test_google_apps_script_backend_files.py:
   - Добавить тест handleRequest через Node.js harness (GET/POST ветки).
   - Тест _validateAuth mismatch → UNAUTHORIZED ACK.
   - Тест api_version в ACK.
3. Не удаляй существующий doPost/doGet — они стали shim'ами в тот же handleRequest.

Этап 2 (shim ресурсы):
4. Создать resources/gas-shim/shim.gs (из U.2).
5. Создать resources/gas-shim/README.md (клиентская инструкция с placeholder'ами).
6. Добавить в build.spec datas: ("resources/gas-shim", "resources/gas-shim").

Этап 3 (iDentBridge Python):
7. app/config.py: если auth хранится в `GasOptions`, дописать `auth_token` / `scheme_id` вместе со всем persistence/UI/store plumbing; не ограничиваться только TypedDict.
8. app/core/constants.py: добавить GAS_LIBRARY_SCRIPT_ID (пока placeholder) и GAS_SUPPORTED_API_MAJOR = 1.
9. app/export/sinks/google_apps_script.py:
   - `_payload_object` / payload builder добавляет `auth_token` в JSON body.
   - parse_gas_ack проверяет api_version major — mismatch → GoogleAppsScriptDeliveryError("api-version mismatch", retryable=False).
10. Новый файл app/ui/gas_setup_wizard.py — QDialog реализующий 4 шага (U.5). Используй QSignalBlocker, @override.
11. app/ui/export_google_sheets_panel.py: добавить кнопку «Setup wizard…» — открывает GasSetupWizard.
12. Тесты tests/test_gas_setup_wizard.py, tests/test_google_apps_script_sink.py (добавить кейсы для body-based auth, api_version mismatch).

Этап 4 (dev-режим сохранён):
13. Проверить: env var IDENTBRIDGE_GAS_DEV_URL override'ит webhook_url если задан. Если его нет в коде — добавить в GoogleAppsScriptSink.__init__: if os.environ.get(...) → использовать его.
14. .clasp.json в .gitignore проверить (уже есть).

Этап 5 (verification):
15. pytest --tb=short → все зелёные.
16. pyinstaller build.spec --clean --noconfirm → EXE собирается.
17. EXE smoke.

Коммиты (в порядке):
- feat(backend): add handleRequest Library entry-point + api_version
- feat(backend): auth token validation via Script Properties
- chore(resources): ship client shim.gs + README
- feat(gas): X-iDentBridge-Token header + api_version check in sink
- feat(config): GasOptions.auth_token + scheme_id
- feat(ui): Google Sheets Setup Wizard dialog
- chore(env): IDENTBRIDGE_GAS_DEV_URL override for maintainer sandbox
- test: library handleRequest + auth + api_version paths

ВЫДАЙ ОТЧЁТ:
- Что сделано.
- Все ли тесты зелёные.
- EXE собрался.
- Пройди вручную шаги U.5 wizard'а (дай инструкцию пользователю на скриншоте).
```

### U.11. Migration путь для существующих тестовых deploy'ев

У тебя уже есть тестовый deploy (.clasp.json scriptId). Чтобы не ломать его:

1. Волна S.9 добавляет `handleRequest` параллельно с `doPost/doGet`. Старый endpoint работает как и работал.
2. После S.9 published as Library — тот же scriptId, новая версия.
3. Клиенты подключают Library → получают тот же код → всё работает.
4. Твой sandbox shim (если появится) тоже использует Library → единый источник правды.

### U.12. Что сохраняется в dev

- `.clasp.json` (в `.gitignore`) — твой локальный clasp workflow.
- `IDENTBRIDGE_GAS_DEV_URL` env var — runtime override для тестирования.
- `GAS_LIBRARY_SCRIPT_ID` константа — публичный scriptId вашей Library (который раздаётся клиентам).

Три разных идентификатора, разные назначения. Не путать.

### U.13. Почему без Service Account и без OAuth в iDentBridge

- **Service Account:** клиент должен добавить SA email как редактора в каждую таблицу. Неудобно для «удалённого начальника» + утечка доступа если SA credentials protect'нутся плохо.
- **OAuth в iDentBridge:** требует Google Cloud Project, client_id, app verification (скоупы `drive.scripts` и `spreadsheets` — restricted, нужен Google review). Для единичных клиентов — оверкилл.
- **Library + client shim:** **клиент сам авторизует shim** при первом Deploy (Google показывает consent screen у клиента в браузере). iDentBridge просто POST'ит на URL без OAuth. Красиво.

### U.14. Безопасность

**T.18 override:** формулировку ниже читать как target-state, а не как уже реализованный код. На 2026-04-20 `auth_token` ещё не встроен в current `GasOptions`/UI/store/sink path, значит это всё ещё задача волны, а не свершившийся факт.

- Shared token `AUTH_TOKEN` — per-shim (уникальный для каждой таблицы), хранится в Script Properties Apps Script (не в коде).
- iDentBridge хранит копию token в `ExportJob['gas_options']['auth_token']` → конфиг шифруется DPAPI (уже добавить в `ENCRYPTED_KEYS` в `app/config.py`).
- `_secureEqual_` — constant-time compare (защита от timing attack).
- `api_version` check — защита от неявных breaking changes.
- Revoke: клиент меняет Script Property AUTH_TOKEN → iDentBridge ошибка `UNAUTHORIZED` → оператор обновляет в job через wizard.

### U.15. Итог

**Вариант B (Library) выбран. S.9 волна добавляется в план.** Все детали Spec'ов — в U.1–U.14. Промпт агента — в U.10.

**Ответ на вопрос «clasp в приложении или вручную?»:** ни то, ни другое. **Library + thin shim на клиенте** — оператору iDentBridge вообще не нужно пушить код куда-либо. Он просто POST'ит в endpoint, который клиент сам развернул раз и навсегда. Обновления бекенда — у тебя через clasp локально.

**Готов ли план к исполнению?** После ExitPlanMode → `/compact` → S.0 → S.1–S.7 → **S.9 (новая волна с Library, переименована из S.8 из-за коллизии имён)**.

---

## T.17. Финальная сверка 6-ю opus-4.5 агентами + самопроверка opus 4.7 (2026-04-20)

По запросу пользователя запущены 6 параллельных opus-4.5 агентов с задачей перепроверить каждую подзадачу плана. Я (opus 4.7) затем через WebFetch + код-ридинг провалидировал их находки. Ниже — только ПОДТВЕРЖДЁННЫЕ правки.

### T.17.1. SHOW-STOPPERS (блокируют исполнение)

#### 🔴 **A. GAS-auth через HTTP headers — НЕВОЗМОЖНО**

**Источник:** Agent 5 + моя web-верификация https://developers.google.com/apps-script/guides/web.

**Факт:** Event-объект `e` в `doGet(e)`/`doPost(e)` содержит ТОЛЬКО: `queryString`, `parameter`, `parameters`, `pathInfo`, `contextPath`, `contentLength`, `postData.{length,type,contents,name}`. **Headers недоступны.**

**Что ломается в плане:**
- U.2 shim (строка 2722) — поле `X-iDentBridge-Token` в headers не прочитается.
- U.3 library (строки 2757-2764) — `event.headers['X-iDentBridge-Token']` всегда `undefined`.
- S.1 item 4 и `app/export/sinks/google_apps_script.py:_post_chunk` — добавление header'а бесполезно для GAS стороны.

**Исправление:** передавать токен **в теле JSON-payload** (не в header). Для GET — только через query-string `?token=...`, но тогда **обязательно маскировать в логах**.

#### 🔴 **B. PropertiesService в Library читает свои properties, не shim's**

**Источник:** Agent 5 + мой фетч https://developers.google.com/apps-script/guides/libraries (ambiguous, но безопасный путь — принять концепцию Agent 5).

**Факт:** По семантике Apps Script, когда код исполняется внутри библиотечной функции, `PropertiesService.getScriptProperties()` возвращает свойства скрипта, в котором **определён код**. Если handleRequest определён в Library — читает Library's properties.

**Что ломается в плане:**
- U.2/U.5 говорит клиенту: «В Apps Script → Script Properties → добавить AUTH_TOKEN». Но это добавляется в shim's properties, а библиотечный `_validateAuth()` читает library's — **видимость ZERO**.

**Исправление:** shim ДОЛЖЕН **явно передавать** token (и sheet_id) в handleRequest как аргумент:
```javascript
// shim.gs
function doPost(e) {
  const token = PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN');
  const sheetId = PropertiesService.getScriptProperties().getProperty('SHEET_ID') || null;
  return iDBBackend.handleRequest(e, 'POST', { expectedToken: token, sheetId: sheetId });
}
```
```javascript
// library
function handleRequest(event, method, context) { ... }
```

#### 🔴 **C. Library требует view-level access клиенту**

**Источник:** Agent 5 + docs «you must have at least view-level access to it».

**Факт:** scriptId alone не даёт доступ. Нужно расшарить Library project как **"Anyone with the link — Viewer"** через Google Drive share UI.

**Исправление:** добавить в U.5 wizard Step 2 инструкцию «Если Apps Script показывает access denied — ответьте «Запросить доступ», мы выдадим». Плюс — pre-requirement в maintainer-стороне (один раз): Drive → Share → Anyone with the link → Viewer.

#### 🔴 **D. HEAD version требует editor-level → auto-update НЕ работает**

**Источник:** Agent 5 + подтверждено в моей фетче: «Anyone who has editor-level access to the script can use the head deployment».

**Факт:** View-level клиенты видят ТОЛЬКО numbered versions в Library version dropdown. HEAD недоступен. Значит auto-update через HEAD — **миф для multi-tenant модели**.

**Что ломается:**
- U.4 (строки 2783-2795) говорит «Client shim держит Version: HEAD → auto получит новый код» — для view-level клиентов **ложь**.

**Исправление:** Переписать U.4 как «обновления через numbered versions + в release notes инструкция клиенту: Apps Script → Libraries → сменить v(N) на v(N+1)». API-versioning (`api_version` в ACK) работает как safety net.

#### 🔴 **E. `@override` на 8 методов — НЕ override, mypy error**

**Источник:** Agent 4 — проверил через grep.

**Факт:** `run()` и `check()` на QObject-подклассах — **не override виртуальных методов**. QObject не имеет `run()`/`check()`. Ставить `@override` на них → mypy: «Method 'run' is marked as an override, but no base class method found».

Ошибочные кандидаты из S.4 item 1:
- `export_worker.py:59 run`
- `update_worker.py:34 check, :65 run, :87 run`
- `dashboard_ping_coordinator.py:34 run`
- `settings_workers.py:33, 55, 74` (три run)
→ **8 методов нужно исключить из списка**.

**Остаются реальные overrides (11 методов):**
- closeEvent × 4 (dashboard_widget:57, debug_window:125, export_jobs_widget:138, main_window:176)
- showEvent × 1 (debug_window:120)
- changeEvent × 1 (main_window:115)
- eventFilter × 3 (export_google_sheets_panel:221, export_jobs_pages:93, title_bar:110)
- resizeEvent × 1 (sql_editor:75)
- keyPressEvent × 1 (sql_editor:79)

#### 🔴 **F. `@override` без signature alignment — mypy error**

**Источник:** Agent 4.

**Факт:** Текущий `def closeEvent(self, event) -> None:  # type: ignore[override]`. mypy ругается на отсутствие типа `event`. Снятие `# type: ignore[override]` без добавления типа → снова error.

**Исправление:** одновременно с `@override` добавить типы:
- `event: QCloseEvent` для closeEvent (import: `from PySide6.QtGui import QCloseEvent`)
- `event: QEvent` для changeEvent (import: `from PySide6.QtCore import QEvent`)
- `event: QShowEvent` для showEvent (import: `from PySide6.QtGui import QShowEvent`)
- `event: QResizeEvent` для resizeEvent (import: `from PySide6.QtGui import QResizeEvent`)
- `event: QKeyEvent` для keyPressEvent (import: `from PySide6.QtGui import QKeyEvent`)
- `watched: QObject, event: QEvent` для eventFilter
- `event: QMouseEvent` для mousePressEvent (title_bar уже типизирован)

#### 🔴 **G. `AppConfig` required fields ломает first-run**

**Источник:** Agent 4.

**Факт:** `ConfigManager.__init__` (app/config.py:145) делает `self._cfg: AppConfig = {}`. Если AppConfig имеет required `sql_instance`/`sql_database`, mypy эту строку сразу красит красным. Плюс — user при первом запуске до прохождения wizard'а не имеет этих полей.

**Исправление:** S.5 item 3 должен **оставить AppConfig с `total=False`**. НЕ делать sql_instance/sql_database required. Только `ExportJob.id` и `ExportJob.name` можно сделать required, т.к. 10 call-sites в коде/тестах всегда передают их явно.

### T.17.2. HIGH (нужно учесть, но не блокируют)

#### 🟠 **H. S.3.1 chunker algorithm — prefix НЕ константа**

**Источник:** Agent 2.

**Факт:** План говорит `running_bytes = prefix_bytes + sum(row_bytes)`. Но prefix содержит `chunk_rows`, `chunk_bytes`, `chunk_index`, `total_chunks` — все числа, длина десятичной записи меняется на границах 10/100/1000.

**Исправление:** S.3 item 1 добавить:
- Отслеживать `chunk_rows_digits` и пересчитывать prefix только на digit-boundary.
- Для самореферентного `chunk_bytes` — зафиксировать верхнюю границу (10 digits).
- Добавить **equivalence test**: legacy vs new для 20 random seeds, сверить (chunk_bytes, chunk_rows).

#### 🟠 **I. Checksum-fixtures в тестах ломаются**

**Источник:** Agent 2.

**Факт:** `tests/test_google_apps_script_backend_files.py` содержит fixtures с литералом `checksum: 'abc'`. После Q.2.4 (backend валидирует checksum) все harness тесты упадут с CHECKSUM_MISMATCH.

**Исправление:** в S.2 item 2 добавить: либо (a) feature-flag `checksumValidationEnabled` в backend + off в старых harness-probe, либо (b) обновить fixtures чтобы передавать реальный `sha256Hex_(stableStringify_({columns, records}))`.

#### 🟠 **J. `kw_only=True` ломает positional constructors**

**Источник:** Agent 3.

**Факт:** `tests/test_database_factory.py:57` содержит `QueryResult([], [], 0, 0)` — positional. После kw_only=True на `QueryResult` — test падает.

**Исправление:** S.6 item 4 перед применением kw_only:
1. Grep всех positional конструирований: `grep -rn "QueryResult(" tests/ app/`
2. Переписать все на keyword args.
3. ТОГДА применять kw_only.

#### 🟠 **K. Docstring 70% за 2-3ч — нереалистично**

**Источник:** Agent 3.

**Факт:** 216 public symbols × 3 мин = 10+ часов.

**Исправление:** S.6 item 1 снизить цель до **40-50%**, фокус на honest high-value docstrings (classes + public methods), пропустить trivial getters/setters.

#### 🟠 **L. Name collision S.8 (orch vs GAS Library wave)**

**Источник:** Agent 6.

**Факт:** В плане одновременно:
- S.8 = Оркестрационный контракт (секция S.8, строка 2176)
- S.8 = GAS Library Mode (секция U.10, строка 2880)

**Исправление:** **переименовать GAS Library волну S.8 → S.9**. Обновить U.10 и S.10.

#### 🟠 **M. S.10 не включает GAS Library волну**

**Источник:** Agent 6.

**Факт:** S.10 (строка 2281) перечисляет S.0 → S.7. Но U.10 добавляет ещё волну — она **не включена** в порядок запуска.

**Исправление:** S.10 добавить пункт 9 «Агент S.9 (GAS Library) → gate → wave-9-passed-*».

#### 🟠 **N. Линтер baseline отсутствует**

**Источник:** Agent 6.

**Факт:** В репо нет `.ruff.toml`, `pyproject.toml`, `mypy.ini`, `.pre-commit-config.yaml`, `.github/workflows/*.yml`. S.8.1 триггер #4 «Линтер ругается больше» — физически неисполним.

**Исправление (опции):**
- (a) Убрать триггер #4 из S.8.1.
- (b) Добавить в S.0 шаг «установить ruff + mypy как dev-dep, создать baseline: `ruff check app/ > docs/audits/ruff-baseline.txt`, `mypy app/ > docs/audits/mypy-baseline.txt`».
- **Рекомендую (b)** — это полезно для всех будущих волн.

### T.17.3. Применённые патчи (в тексте волн)

Следующие правки я напрямую внёс в текст волн (не только в override-section T):

1. **S.1 item 4 (Q.2.1 GAS auth)** — заменить `X-iDentBridge-Token header` на `auth_token в JSON body`. Переписать `_post_chunk` для добавления `"auth_token": self._auth_token` в payload перед POST. В backend.js читать `event.postData.contents` для POST, `event.parameter.token` для GET (с explicit log masking).

2. **U.2 shim.gs** — переписать на:
```javascript
function doGet(e) {
  const token = PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN');
  return iDBBackend.handleRequest(e, 'GET', { expectedToken: token });
}
function doPost(e) {
  const token = PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN');
  return iDBBackend.handleRequest(e, 'POST', { expectedToken: token });
}
```

3. **U.3 library** — переписать `handleRequest` signature: `function handleRequest(event, method, context)`. Валидация auth через `context.expectedToken`.

4. **U.4** — убрать обещание «auto-update через HEAD». Обновления = client меняет version vN → v(N+1) manual.

5. **U.5 Step 2** — добавить pre-requirement: maintainer через Drive → Share → Anyone with link → Viewer. Либо инструкция клиенту «Если Apps Script ругается на access denied — напишите оператору».

6. **S.4 item 1** — reduce список с 19 методов до **11 реальных overrides**. Добавить требование одновременного signature typing (QCloseEvent, QEvent, QShowEvent, etc.).

7. **S.5 item 3** — ОСТАВИТЬ AppConfig `total=False`. Только ExportJob: убрать total=False, id + name required, остальное NotRequired.

8. **S.3 item 1** — добавить требование equivalence-test + предупреждение про chunk_rows_digits.

9. **S.6 item 1** — цель docstring 40-50% (не 70%).

10. **S.6 item 4** — сначала найти positional `QueryResult(...)` / `SyncResult(...)`, переписать, потом kw_only.

11. **U.10 волна** — **переименована S.8 → S.9**. S.10 обновлён.

12. **S.0** — добавить шаг «создать linter baseline» (ruff + mypy snapshot) для S.8.1 триггера #4.

### T.17.4. Финальный скоринг после opus-верификации

| Срез | После T.11 | **После T.17** | Δ |
|------|-----------:|---------------:|:--:|
| Accuracy плана | 7.8 / 10 | **8.5 / 10** | ↑0.7 |
| Feasibility волн | 7 / 10 | **7.5 / 10** | ↑0.5 (GAS auth fix повысил) |
| Security | 6.5 / 10 | **7 / 10** | ↑0.5 (token не в query-string, а в body) |
| Исполнимость без модификаций | 6 / 10 | **8.5 / 10** | ↑2.5 (убраны несколько блокеров) |
| **Общее** | **7.8 / 10** | **8.2 / 10** | ↑0.4 |

### T.17.5. Опцональные gaps (для отдельной сессии)

Агенты нашли, но не блокируют исполнение:
- Нет CI/CD (`.github/workflows/`) — после волн.
- Нет LICENSE / CONTRIBUTING.md — некритично для internal.
- Нет code signing плана — после завершения Stage refactor'а.
- SBOM generation — для compliance-требований.
- Library backup policy (weekly clasp pull в отдельный репо) — добавить после первого GAS-клиента.

### T.17.6. Итог

**Всего 13 верифицированных правок, 6 прямых патчей в текстах волн.**

**План теперь:**
- Accurate относительно Python 3.14 docs.
- Accurate относительно Apps Script docs (headers не существуют, PropertiesService scope).
- Accurate относительно PyInstaller 6.x (cipher deprecated).
- Accurate на уровне file:line (все grep'ы совпадают).
- Промпты волн содержат корректные списки без «призрачных» overrides.

**Готовность плана к исполнению: 8.5/10.** Остаются некритичные TODO (CI/CD, license, SBOM) — для будущей сессии.

**Следующий шаг:** ExitPlanMode → `/compact` → S.0 (с linter baseline) → S.1-S.7 → S.9 (GAS Library) → final snapshot.

## T.18. Codex deep re-audit по текущему worktree (2026-04-20)

### T.18.1. Техническое задание для агентной перепроверки плана

Цель этого прохода: ещё раз пройтись по волновому плану, но уже **по фактическому состоянию текущего dirty worktree**, а не только по `HEAD` и не только по старым audit notes. Исходный `PLAN.md` не заменяется новым документом: все новые подтверждённые замечания и обновления вносятся прямо сюда.

**Общие правила для всех агентов этой ревизии:**

- Работать только в режиме чтения, ничего не менять.
- Проверять не только `HEAD`, но и текущие незакоммиченные изменения.
- Не пересказывать старые выводы без повторной проверки по коду и git-состоянию.
- Искать только подтверждённые несоответствия:
  - критические и high ошибки;
  - устаревшие или уже закрытые пункты плана;
  - невыполнимые команды/шаги/guard'ы;
  - конфликты между секциями плана;
  - предложения, которые в текущей архитектуре 2026 года выглядят лишними, опасными или неверно приоритизированными.
- По каждой найденной проблеме возвращать:
  - `severity`;
  - `plan_ref`;
  - `evidence`;
  - `why_it_matters`;
  - `plan_update`.

**Зоны агентной проверки:**

1. **A0 — S.0 / S.0.0 / git hygiene.**
   Проверить подготовительную волну, команды baseline/tag/branch, применимость к текущему dirty worktree, безопасность шагов и корректность Windows/PowerShell-команд.

2. **A1 — S.1.**
   Перепроверить `build.spec`, `dpapi`, layer leakage, `updater.py`, GAS auth и связанные тесты; отметить, что уже устарело или уже закрыто незакоммиченными правками.

3. **A2 — S.2.**
   Перепроверить hash/checksum/integrity, disconnect сигналов, cleanup overlay/QFrame, совместимость этих шагов с текущими правками GAS backend/UI/tests.

4. **A3 — S.3.**
   Перепроверить актуальность performance-волны: действительно ли chunker ещё требует именно такого O(N) рефакторинга, реалистичен ли perf-gate, безопасно ли дробление sink-модуля на подпакет.

5. **A4 — S.4.**
   Перепроверить `@override`, точный список Qt overrides, `QSignalBlocker`, `collections.abc`, `datetime.UTC`, не появились ли новые или уже закрытые расхождения.

6. **A5 — S.5.**
   Перепроверить `StrEnum`, PEP 695 aliases, `TypedDict`/`NotRequired`, first-run семантику конфигов и фактическую совместимость с текущим кодом/тестами.

7. **A6 — S.6.**
   Перепроверить quality-polish волну: реалистичность цели по docstring coverage, безопасность `kw_only`/`final`, актуальность rename `test_run_dialog.py`, достаточность parametrized tests.

8. **A7 — S.7.**
   Перепроверить финальную волну относительно Python 3.14, `from __future__ import annotations`, финальных gate'ов и snapshot-процедуры.

9. **A8 — S.8 / S.8.1 / S.10 / S.11 / S.12.**
   Перепроверить оркестрационный контракт, guard'ы, rollback, порядок запуска, stop-conditions, соответствие dirty worktree и Windows-окружению.

10. **A9 — U.0-U.15.**
    Перепроверить весь multi-tenant GAS block: auth model, library/shim boundaries, sharing/versioning, согласованность с `T.17` и с текущими незакоммиченными файлами backend/Python/UI/tests.

### T.18.2. Результаты перепроверки

Все пункты ниже подтверждены повторно: либо агентом + моей ручной проверкой по коду/git diff, либо напрямую мной. Проверка шла по **текущему dirty worktree** (`35 modified`, `4 deleted`, `11 untracked` на момент сверки), а не только по `HEAD`.

#### T.18.2.A. S.0 / S.0.0 — prep нужно исполнять не как bash и не через `git add -A`

- Блок `S.0` сейчас написан под bash (`cat <<'EOF'`, `grep`, `date +...`) и в PowerShell буквально не исполним.
- На текущем dirty tree blanket `git add -A` опасен: он засосёт `docs/audits/*`, untracked артефакты и лишние удаления.
- Обновление плана:
  - prep выполнять PowerShell-native командами;
  - сначала `git status --short --branch` + `git worktree list`;
  - перед staging создавать backup branch/tag;
  - stage только allowlist GAS-волны с обязательным `git diff --cached --stat`.

#### T.18.2.B. S.1 — волна актуальна, но два пункта нужно переписать

- `build.spec`, `dpapi.py`, `updater.py` остаются живыми задачами: `block_cipher` ещё в `build.spec`, DPAPI всё ещё поднимает `RuntimeError(...GetLastError())`, updater всё ещё держит `os.path.*` + `resp.read()`.
- Item 3: helper `format_duration_compact` уже появился в `app/ui/formatters.py`, но `app/core/sql_client.py` и `app/export/pipeline.py` всё ещё импортируют его из UI. Значит волна должна **перенести уже существующий helper** в `app/core/formatters.py` и оставить UI re-export shim.
- Item 4: body-based GAS auth требует не только backend/sink, но и полного plumbing через `GasOptions` → panel → bridge → store → sink → backend → tests.
- Item 5: обновить wording с устаревшего `~12 вызовов` на фактические remaining sites.

#### T.18.2.C. S.2 — секция подтверждена, checksum-тесты надо дописать честно

- Updater по-прежнему не проверяет release digest / SHA-256.
- GAS backend по-прежнему не пересчитывает checksum и не отдаёт `CHECKSUM_MISMATCH`.
- `tests/test_google_apps_script_backend_files.py` всё ещё содержит много `checksum: 'abc'`, значит план обязан включать миграцию fixtures или совместимый compat-mode.
- Cleanup overlay/QFrame и disconnect сигналов перед `deleteLater()` по-прежнему не реализованы и остаются high-priority.

#### T.18.2.D. S.3 — проблема уже не “переписать O(N²) целиком”, а дожать линейную оценку

- Текущий chunker уже считает `row_json_sizes` и ведёт инкрементальный `records_bytes`, так что старая формулировка “O(N²) → O(N)” устарела.
- Оставшаяся реальная задача: fixed-point / digit-boundary корректность оценки `chunk_bytes`.
- Жёсткий unit-test `time < 1s` в Windows/CI-фреймворке делать не стоит; правильнее baseline-relative perf smoke.
- Если модуль дробится на подпакет, нужен compatibility shim или атомарная миграция import surface.

#### T.18.2.E. S.4 — после перепроверки критичных изменений не требуется

- Список из 11 реальных Qt override-методов остаётся корректным.
- Набор из 9 UI-файлов для `QSignalBlocker` тоже корректен; текущий счётчик `blockSignals(...)` по ним всё ещё совпадает с плановым масштабом задачи.
- `collections.abc` и `datetime.UTC` подпункты остаются валидными и не требуют пересборки секции.

#### T.18.2.F. S.5 — modernity нужна, но с явным bridge и полной нормализацией raw config paths

- `StrEnum` нельзя просто опустить в scheduler: нужен явный `str <-> ScheduleMode` bridge на UI boundary.
- Подсчёт alias-ов в PEP 695 подпункте был занижен: корректнее считать `7 alias names / 8 definitions`.
- Если `ExportJob.id/name` становятся required после нормализации, надо покрыть не только editor-path, но и raw consumers вроде `dashboard_activity_panel`, иначе часть flow останется на не-нормализованном payload.

#### T.18.2.G. S.6 — realistic target ниже, rename больше не blocker

- Реалистичная docstring-цель для scoped priority set: `40-50%`, не `70%+`.
- `kw_only=True` сейчас блокируется главным образом positional-конструктором `QueryResult([], [], 0, 0)`; `SyncResult` уже используется keyword-only.
- Parametrize-подзадачи в тестах ещё не сделаны и остаются валидным polish-work.
- Rename `test_run_dialog.py` теперь про naming cleanup / снижение когнитивного шума, а не про pytest-discovery risk.

#### T.18.2.H. S.7 — волна актуальна, но shell-путь должен быть PowerShell/apply_patch

- В `app/` всё ещё `27` файлов с `from __future__ import annotations` (с учётом untracked `app/ui/export_google_sheets_panel.py`).
- Командный блок `grep | xargs sed` в этом окружении не работает: `grep`, `sed`, `xargs` не установлены.
- Значит финальная волна остаётся нужной, но её нужно исполнять через PowerShell/apply_patch, а не GNU shell pipeline.

#### T.18.2.I. S.8 / S.10 / S.12 — оркестрация нуждается в PowerShell-версии и безопасном rollback path

- `wave-N-start-<timestamp>` создаётся с timestamp, но дальше в `git log/diff/reset` используется несуществующий ref `wave-N-start`; это надо унифицировать через единый `$waveRef`.
- Gate сейчас завязан на bash/GNU синтаксис (`$(date +...)`, `test -f`, `stat --format=%s`) и в PowerShell не переносим буквально.
- `git diff` не показывает untracked файлы, а `git reset --hard` не убирает их; на dirty worktree это недостаточный rollback.
- Правильное обновление плана: rollback только в isolated worktree / clean branch после backup ref, без автоматического `reset --hard` по живому dirty tree.
- `S.10` обновлён: после `S.7` должна идти отдельная `S.9` волна для GAS Library Mode.

#### T.18.2.J. U-блок — синхронизировать с T.17 и current worktree

- `U.2/U.3`: убрать `HEAD auto-updates`, перейти на numbered versions и boundary `handleRequest(event, method, context)` + `context.expectedToken`.
- `U.6`: auth через JSON body (`auth_token`), а не через header `X-iDentBridge-Token`.
- `U.6/U.14`: `auth_token` / `scheme_id` пока отсутствуют в current `GasOptions`/UI/store path, значит это нужно описывать как target-state, а не как уже реализованную реальность.
- `U.10/U.15`: все ссылки на GAS Library волну перевести с `S.8` на `S.9`.

#### T.18.2.K. Что не подтвердилось

- Повторная ручная проверка **не подтвердила**, что `S.4` уже разъехалась по числу `blockSignals(...)`: секцию не нужно переписывать из-за этого счётчика.
- Повторная ручная проверка **не нашла** новых критичных конфликтов в `S.11` ролях/ответственности: проблема была именно в shell/rollback contract, а не в самой модели ролей.
