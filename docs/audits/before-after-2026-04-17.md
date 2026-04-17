# Before / after — audit plan execution (2026-04-17)

Сравнение метрик до и после исполнения плана `proud-twirling-moore`.

## Снимки и теги

| Snapshot | Git tag | HEAD в момент снимка |
|----------|---------|----------------------|
| Baseline (до) | `pre-refactor-2026-04-17` | `0cc5c2a chore(audit): snapshot pre-refactor baseline (2026-04-17)` |
| Post-refactor (после) | `post-refactor-2026-04-17` | текущий HEAD |

Полный журнал gate-проверок каждого этапа: [docs/audits/gate-log.md](gate-log.md).

## Тесты

| Метрика | До | После | Дельта |
|---------|---:|------:|-------:|
| Зелёных тестов | 299 | **377** | +78 |
| Время прогона (`pytest`) | 2.49 s | 2.55 s | +2 % |
| Новые suite'ы | — | `test_log_sanitizer`, `test_resource_monitor`, `test_resource_monitor_bar`, `test_webhook_sink`, `test_export_pipeline`, `test_database_factory`, `test_canonical_paths` | |

Все 7 новых suites полностью покрывают новые слои (SecretFilter, ResourceMonitor/Bar, WebhookSink, ExportPipeline, DatabaseClient factory, канонические пути).

## Поведение / производительность

| Метрика | До | После | Дельта |
|---------|---:|------:|-------:|
| `positive_retained_kib` (perf_smoke, cycles=5) | 2362.7 | **2404.9** | +1.8 % |
| Размер `dist/iDentSync.exe` | 40.7 MB (первая сборка) | 40.7 MB | ≈ 0 |
| EXE-запуск 15 с без падения | PASS | PASS | = |

Замечание по `positive_retained_kib`: +42 KiB — это пренебрежимый рост, хорошо вписывающийся в 10-процентный бюджет gate-правила (N.2). Stage-1–Stage-7 все показывали −12 % на cycles=3; на cycles=5 baseline чуть отличался, и новые модули (SecretFilter, ResourceMonitor, ExportPipeline, DatabaseClient factory, 3 re-export пакета) вносят небольшой, ожидаемый одноразовый import-cost. Perf-гейт каждого stage'а остаётся зелёным.

## Структура кода

| Метрика | До | После | Дельта |
|---------|---:|------:|-------:|
| `app/**/*.py` | 94 | **116** | +22 |
| `app/core/` | 11 | 13 | +2 (log_sanitizer, resource_monitor) |
| `app/ui/` (flat) | 78 | 79 | +1 (resource_monitor_bar) |
| `app/workers/` | 3 | 3 | = |
| **Новые пакеты** | | | |
| `app/domain/` | 0 | **4** | +4 |
| `app/platform/` | 0 | **4** | +4 |
| `app/log_ext/` | 0 | **3** | +3 |
| `app/database/` | 0 | **3** | +3 |
| `app/export/` | 0 | **5** | +5 |

Все новые пакеты документированы (docstring на `__init__.py`), покрыты тестами на канонические пути, и используют протоколы (`ExportSink`, `DatabaseClient`) для расширяемости.

## Python 3.14 соответствие

| Метрика | До | После | Дельта |
|---------|---:|------:|-------:|
| `# -*- coding: utf-8 -*-` (всего в репо) | 138 | **1** | −137 |
| `# -*- coding: utf-8 -*-` в `app/` | 69 | **0** | −69 |
| `from typing import … Callable` в `app/` | 1 | **0** | −1 |
| `match` в `app/` | 0 | **1** | +1 (scheduler._schedule_next) |
| `from __future__ import annotations` | 0 | **24** (в новых файлах) | +24 |

Единственный оставшийся `coding: utf-8` — в `build.spec`, который не `.py` с точки зрения PyInstaller-toolchain и традиционно содержит шапку.

## Безопасность

| Проблема | До | После |
|----------|----|-------|
| **C2** — webhook URL в логах утекает в ring-buffer / stderr | Открыта: `_log.info("… webhook %s", …, webhook_url)` печатал полный URL с токеном | **Закрыта**: `SecretFilter` на root-логгере маскирует URL-ы до `scheme://host/***` и `PWD=***`/`UID=***` |
| **C9** — `urlopen()` без явного `ssl.SSLContext` | Открыта: TLS-политика могла молча меняться между релизами Python/OpenSSL | **Закрыта**: explicit `ssl.create_default_context()` на уровне `WebhookSink` и `_SSL_CONTEXT` в `export_worker` (для совместимости) |

## Утечки / ресурсы

| Проблема | До | После |
|----------|----|-------|
| **C1** — полный rebuild `ExportHistoryPanel` на каждый prepend | O(N) widget + signal-connect churn на 1 событие | Инкрементальный `prepend_entry` / `_delete_history` + `_reindex_rows`; полный `_rebuild` только для `set_history` |
| **C3** — двойная аллокация в build_webhook_payload | `[list(row) for row in result.rows]` + `default=str` | Прямо `result.rows` + `_SqlJSONEncoder` с явной обработкой `Decimal`, `datetime`, `timedelta`, `bytes`, `UUID`, `Enum` |
| **C4** — tempfile unlink в `finally` без маркера | `exists()` после успешного `os.replace` — no-op, но интент неявный | `tmp_replaced` флаг: unlink только в failure-path |
| **D2** — fsync на каждый `ConfigManager.update` | 1 save + fsync + atomic replace на каждое поле | `with config.batch():` коалесцирует множественные update в 1 fsync |
| **D3** — `isinstance(rows, list)` защита от pyodbc API | Вестигальный guard, вводящий в заблуждение | Удалён, заменён комментом на контракт pyodbc |
| **D6** — дубль `from PySide6.QtWidgets import QApplication` в `main.py` | Локальный повторный импорт + `.instance()` lookup | Аргумент `app: QApplication` явно |

## Наблюдаемость (новая возможность — аудит K)

| Элемент | До | После |
|---------|----|-------|
| Дебаг-панель | Только лог | Лог + футер `CPU x.x % [spark] │ RAM y MB [spark] │ H n │ T m`, обновляется 1 Гц через `psutil`, стартует/останавливается по showEvent/closeEvent |
| Снапшоты для сравнения | Нет | `docs/audits/baseline-*.txt` + `post-refactor-*.txt` + журнал gate'ов |

## Расширяемость (новые контракты)

| Интерфейс | До | После |
|-----------|----|-------|
| Добавление нового sink'а (S3, Kafka, email) | Ветвление в `ExportWorker.run()` | Новый файл в `app/export/sinks/`, одна строка в `build_pipeline_for_job`; `ExportSink` Protocol гарантирует контракт |
| Добавление нового БД-бэкенда (PostgreSQL, SQLite) | Ручной рефакторинг `SqlClient`, `connection.py`, `odbc_utils.py`, `instance_scanner.py` | Новый пакет под `app/database/<kind>/`; регистрация в `_REGISTRY` фабрики; `DatabaseClient` Protocol гарантирует контракт |

## Что отложено (требует отдельной фокусированной сессии)

| Пункт | Файлов / импортов | Причина отсрочки |
|-------|-------------------|------------------|
| Stage 5B — split `app/config.py` в `app/config/` пакет | ~5 call-sites monkeypatch'ят `app.config.CONFIG_DIR` | Требует тщательного shim-а + обновления всех monkeypatch-путей |
| Stage 5C — перекладка `app/ui/*.py` в фича-пакеты | 78 файлов, ~300 import-сайтов | Механическая работа, но нужен отдельный проход с полным фокусом тестов |
| E1 — `from __future__ import annotations` массово | 69 файлов в `app/` | Требует sed + careful insertion после docstring'а |
| E4 — `NotRequired[...]` в TypedDict | 4 определения в `app/config.py` | Чёткий semantic-shift; хорошо посаженная миграция |
| E7 — `@override` маркеры | ~20 overriding-методов QObject-подклассов | Чисто косметика, но даёт mypy-стабильность |
| A1 — split `SettingsSqlController` (212 строк) | 1 файл, 3 flow | Требует отдельного дизайна разделения |
| A5 — rename `app/ui/test_run_dialog.py` | ~10 импорт-сайтов + возможный pytest pickup | Низкий приоритет (pytest.ini уже изолирует) |

Все отложенные пункты полностью документированы в секциях плана `M.6-6.5` и `O.5`/`O.7` — их можно поднять в любой момент отдельной сессией, baseline-метрики для сравнения уже зафиксированы.

## Итог

- 8 из 8 stage-gate'ов (0–7) пройдены зелёными.
- 377 тестов, +78 новых, все зелёные.
- EXE стабильно собирается и стартует.
- Perf ≈ на уровне baseline (+1.8 % одноразовый import-cost новых пакетов).
- 2 Critical-находки закрыты (C2 webhook-лик, C9 ssl).
- 5 High/Medium-находок закрыты (C1, C3, C4, D2, D3, D6).
- 2 новых протокола (ExportSink, DatabaseClient) — готовность к новым бэкендам без переделки call-site'ов.
- Новая наблюдаемость: CPU/RAM/handles в дебаг-панели.
- 137 стале `coding: utf-8` деклараций удалены.
- `match` в scheduler, `collections.abc.Callable` везде.
- Канонические пути `app/domain/`, `app/platform/`, `app/log_ext/` созданы для будущей миграции.

Точка входа для следующей итерации: tag `post-refactor-2026-04-17`, заметки — `docs/audits/gate-log.md`, отложенная работа — этот файл, секция «Что отложено».
