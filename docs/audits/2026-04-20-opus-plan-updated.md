# Обновлённый план Опуса — нормализован под текущий HEAD

## Как читать этот документ

Структура исходного плана **сохранена**, но каждый блок помечен статусом:

- `Актуален`
- `Частично актуален`
- `Устарел`
- `Уже выполнен`
- `Требует замены`

Цель документа — не переписать весь текст Опуса заново, а превратить его в карту, которую можно читать без повторного расследования состояния репозитория.

## A. Архитектура папок и модулей

**Статус:** Частично актуален

Оставить:

- тезис о плоском и перегруженном `app/ui/`;
- тезис о сложном settings-family;
- тезис о naming confusion вокруг `controller/runtime/bridge`.

Скорректировать:

- часть декомпозиции уже произошла: появились `app/domain/`, `app/database/`, `app/export/`, `app/platform/`, `app/log_ext/`;
- поэтому план больше не про «создать слои с нуля», а про **довести wiring и boundaries до конца**.

Заменить:

- вместо абстрактного давления на разбиение `ui/` в целом поднять выше два конкретных долга:
  - `database.factory` не wired into production path;
  - `core/export` всё ещё импортируют `ui.formatters`.

## B. Нейминг

**Статус:** Частично актуален

Оставить:

- confusion вокруг `ExportJobEditorBridge`, `ExportEditorController`, `ExportExecutionController`, `ExportEditorRuntime`;
- legacy naming `iDentSync` vs `iDentBridge`.

Скорректировать:

- naming сейчас уже не главная боль; он уступает raw dict contracts и незавершённому composition root.

## C. Утечки и ресурсы

**Статус:** Частично актуален

Оставить:

- updater hash/digest verification как открытый долг;
- overlay cleanup риск в `export_google_sheets_panel`;
- логика tempfile / update artifact path в updater;
- `errors.log` / clipboard leakage через raw traceback.

Понизить:

- старый `ExportHistoryPanel` rebuild — уже не hot path;
- `urlopen` без `ssl_context` — для webhook/GAS уже не ключевая проблема;
- `.clasp.json` leak risk — снять как security finding.

Добавить:

- raw traceback leakage path как отдельный пункт;
- полный `fetchall()` в export path как более важный resource/perf issue.

## D. Производительность

**Статус:** Частично актуален

Оставить:

- `ConfigManager.update()` / autosave pressure;
- full-result export pipeline;
- общий сигнал о тяжёлом UI hot path после history updates.

Снять или понизить:

- старый тезис про rebuild `ExportHistoryPanel`;
- тезис про `isinstance(rows, list)` как meaningful perf issue;
- тезис про O(N²) в GAS chunker.

Добавить:

- `dashboard_activity.refresh_dashboard_activity()` как текущий rebuild hot path;
- full-result SQL materialization как более значимый perf-risk, чем часть старых микроправок.

## E. Соответствие Python 3.14

**Статус:** Частично актуален

Оставить:

- отсутствие `@override` как полезный low-effort fix;
- незавершённая modernity по `typing.Callable`;
- риск drift-а между floors в `requirements*.txt` и pinned stack в `constraints-py314-win.txt`.

Понизить:

- `from __future__ import annotations` как high-priority пункт;
- `cipher=block_cipher` как urgent build blocker.

Скорректировать:

- в текущем HEAD Python 3.14 уже практически подтверждён тестами и сборкой;
- современный remaining scope — это скорее cleanup и type-safety, чем compatibility rescue.

## F. Многопоточность

**Статус:** В основном актуален, но без красных флагов

Оставить:

- аккуратность around worker lifecycle и Qt threading helper.

Снять:

- repeated connect / helper leak как высокий риск — подтверждения нет.

Понизить:

- явный signal-disconnect перед delete path — оставить как defensive improvement, не как top-tier defect.

## G. Масштабируемость и поддержка

**Статус:** Актуален

Оставить:

- `ExportSink` и DB-abstraction как правильное направление;
- один backend/sink selection point как будущий composition root;
- риск того, что factory и protocol пока формальны.

Поднять выше:

- `database.factory` не wired into execution path;
- `resolve_export_sink()` остаётся central dispatch, поэтому расширяемость пока частично декларативная.

## H. Приоритизированный action-list

**Статус:** Требует замены

Причина:

- исходный список смешивает уже закрытые пункты, старые high/critical и новые GAS-specific долги.

Новый practical backlog вынесен в отдельный документ:

- [2026-04-20-opus-practical-backlog.md](./2026-04-20-opus-practical-backlog.md)

## I. Целевая структура папок

**Статус:** Частично актуален

Оставить:

- общую идею explicit package boundaries;
- вынесение integration-specific логики из плоского `ui/`/`core/`.

Скорректировать:

- часть этой структуры уже materialized;
- текущая задача не «создать target tree», а понять:
  - какие shim/re-export пакеты оставить,
  - что перевести на canonical path,
  - где убрать половинчатые abstractions.

## J. Конкретные API-правки

**Статус:** Частично актуален

Оставить:

- updater hash/digest verify;
- backend auth/checksum verify;
- перенос formatter out of `ui`;
- cleanup around Google Sheets panel overlay;
- `@override` / last `typing.Callable`.

Снять:

- пункты, уже реализованные Stage 0-7;
- пункты, завязанные на старый `ExportHistoryPanel` hot path.

## K. Resource monitor / debug panel

**Статус:** Уже выполнен

Evidence:

- `app/core/resource_monitor.py`
- `app/ui/resource_monitor_bar.py`
- `tests/test_resource_monitor.py`
- `tests/test_resource_monitor_bar.py`

## L. Визуальные макеты

**Статус:** Исторически полезны, сейчас неоперационные

Оставить:

- как explanatory material.

Снять:

- как источник текущих инженерных приоритетов.

## M. Этапы 0-7

**Статус:** Уже выполнены частично или полностью

| Stage | Текущий статус | Комментарий |
|---|---|---|
| Stage 0 | Уже выполнен | baseline snapshot и теги уже существуют |
| Stage 1 | Уже выполнен | SecretFilter + ResourceMonitor landed |
| Stage 2 | Уже выполнен частично | часть high-fix пунктов уже в коде |
| Stage 3 | Уже выполнен | ExportPipeline / WebhookSink / thin worker landed |
| Stage 4 | Уже выполнен частично | DB protocol/factory появились, но wiring не доведён |
| Stage 5 | Частично выполнен | package layers materialized, но move-to-canonical incomplete |
| Stage 6 | Частично выполнен | scheduler `match` уже есть; часть cleanup not done |
| Stage 7 | Частично выполнен | косметика частично landed, но не закрыта полностью |

Вывод:

- Эти stages нельзя исполнять повторно как есть.
- Их надо трактовать как **историческую карту**, а не как следующий runbook.

## N. Gate после каждого этапа

**Статус:** Частично актуален

Оставить:

- сам принцип `tests -> perf smoke -> build -> exe smoke`.

Скорректировать:

- команды должны быть Windows/PowerShell-native;
- рабочая форма test command здесь — `python -m pytest -q`, а не `pytest`;
- часть gate-логов уже исторически записана, их не нужно «создавать снова» автоматически.

## O. Оркестрация агентов

**Статус:** Устарел как прямой blueprint

Причины:

- исходный план предполагает clean snapshot и sequential fresh execution;
- текущий HEAD уже содержит результаты Stage 0-7 и новую GAS-волну;
- многие agent tasks описывают работу, которая уже materialized или должна быть заменена на cleanup.

Что оставить:

- идею точечных independent review passes;
- раздельные security/perf/arch/python сверки;
- gate-thinking как quality discipline.

Что снять:

- прямой запуск `agent-1.x`, `agent-2.x`, ... `agent-final-snapshot` по исходному тексту.

## P. Audit uncommitted snapshot / GAS wave

**Статус:** Частично актуален

Оставить:

- тезис о том, что GAS wave добавила функциональность и архитектурную нагрузку;
- pointer на новые sink/UI/backend areas.

Скорректировать:

- `.clasp.json` убрать из security findings;
- O(N²) в chunker снять;
- акцент сместить на:
  - auth,
  - checksum verify,
  - full-result delivery model,
  - overlay lifecycle.

## Q. Углублённый аудит 4 sonnet-агентов

**Статус:** Частично актуален

Оставить:

- GAS auth;
- updater hash verify;
- layer leakage;
- factory not wired.

Понизить или снять:

- `.clasp.json` как blocker;
- signal-disconnect как High;
- ряд severity, завышенных без учёта уже landed Stage 0-7 fixes.

## R. Python 3.14 углублённый скан

**Статус:** Частично актуален

Оставить:

- `@override`;
- last `typing.Callable`;
- dependency drift risk;
- weak modernity gaps.

Скорректировать:

- future-import не urgent;
- `cipher=block_cipher` low;
- текущая 3.14 readiness по HEAD уже подтверждена tests + build.

## S. Волновой план исполнения

**Статус:** Устарел как execution blueprint

Причины:

- опирается на старое git-state предположение;
- часть волн описывает уже существующие изменения;
- literal команды не совпадают с текущей средой.

Чем заменить:

- не «волнами S.1-S.8», а practical backlog с независимыми fix-batches.

## T. Корректировки после web-верификации

**Статус:** Частично актуален

Оставить:

- нормализацию тезиса про `from __future__ import annotations`;
- исправление переоценки некоторых PEP-related claims;
- мысль про branch-first safety.

Скорректировать:

- ряд счётчиков и line references снова устарели;
- нужно считать T-блок исторической коррекцией, а не финальным truth source.

## U. Multi-tenant GAS deployment / Library pattern

**Статус:** Целевая архитектура распространения обновлений для GAS, но не текущий blocker

Оставить:

- как архитектурное направление для дальнейшей эволюции продукта;
- как осознанную схему доставки backend-обновлений через тонкие client shim-скрипты и общий library backend;
- как часть долгосрочного distribution model, а не как случайную опциональную идею.

Понизить:

- это не то, что нужно делать раньше auth/hash/checksum/basic hardening.

Вывод:

- U-блок сейчас не должен конкурировать с текущими security/reliability fixes;
- при этом U-блок не нужно выкидывать из плана: для сценария с централизованным распространением обновлений он остаётся правильной целевой моделью.

## Итоговая нормализация

### Что считать актуальной основой

- security и integrity по GAS/updater;
- unfinished architecture around factory/composition root/layer boundaries;
- practical cleanup вокруг Google Sheets panel и error-trace sanitization;
- small modernity fixes с хорошим ROI.

### Что считать историческим контекстом

- исходные Stage/Tag/Agent waves;
- часть ранних perf/resource тезисов;
- часть Python 3.14 panic-claims;
- большая часть S/T-оркестрации как runbook.

### Что делать дальше

- использовать этот документ как map;
- использовать practical backlog как реальный следующий execution list;
- не запускать старый opus-style plan literally.
