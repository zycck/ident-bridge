# Переаудит плана Опуса — текущий HEAD (2026-04-20)

## Scope

- Цель: перепроверить большой план Опуса против **текущего состояния репозитория**, а не против исторического snapshot-а.
- Формат оценки:
  - качество плана Опуса **на дату написания**
  - качество плана Опуса **против текущего HEAD**
  - качество **обновлённого плана ChatGPT** против текущего HEAD
- Этот документ не меняет код. Он фиксирует факты, расхождения и текущие приоритеты.

Смежные артефакты:

- [обновлённый план в структуре Опуса](./2026-04-20-opus-plan-updated.md)
- [practical backlog fixes](./2026-04-20-opus-practical-backlog.md)

## Execution Evidence

| Check | Result |
|---|---|
| Branch | `master` |
| Worktree status | dirty |
| `python -m pytest -q` | `434 passed, 1 warning` |
| `python tools/perf_smoke.py --scenario all --cycles 3 --top 8` | `positive_retained_kib=1996.4` |
| `python -m PyInstaller build.spec --clean --noconfirm` | PASS |
| `dist/iDentSync.exe` smoke run | PASS, alive 10 s |

### Why this matters

- Большая часть текста Опуса была написана по состоянию на более ранний snapshot.
- Сегодня репозиторий уже содержит Stage 0-7 результаты и новую Google Apps Script волну.
- Поэтому часть тезисов Опуса остаётся полезной как историческая карта долга, но уже не является точным описанием текущего HEAD.

## Summary Verdict

План Опуса остаётся сильным по охвату и глубине, но уже заметно просел по точности и исполнимости как blueprint для текущего дерева.

Основные причины:

- в плане смешаны исторические факты и будущие действия, которые уже частично выполнены;
- часть severity завышена или устарела;
- часть file:line и счётчиков больше не соответствует коду;
- execution-блоки содержат команды и git-допущения, которые не воспроизводятся буквально в текущей среде Windows/PowerShell.

Одновременно план Опуса не потерял ценность полностью:

- он хорошо покрывает архитектурные направления;
- он правильно указывает на security-долги вокруг GAS и updater;
- его идея вынести GAS backend в библиотечную модель остаётся сильной как схема распространения обновлений;
- он помогает видеть эволюцию Stage 0-7 и причины появления новых abstraction layers.

## Scorecard

Шкала: `0-10`, где `10` означает «точно, прагматично, исполнимо и полезно прямо сейчас».

| Критерий | Opus на дату плана | Opus против текущего HEAD | ChatGPT против текущего HEAD |
|---|---:|---:|---:|
| Охват и полнота | 9.5 | 8.5 | 9.0 |
| Фактическая точность | 8.0 | 6.0 | 8.8 |
| Калибровка severity | 7.5 | 5.8 | 8.4 |
| Приоритизация | 8.2 | 6.4 | 8.6 |
| Исполнимость плана | 7.4 | 5.5 | 8.7 |
| Полезность для текущего HEAD | 8.0 | 6.2 | 9.0 |
| **Общая оценка** | **8.4** | **6.1** | **8.8** |

### Scoring Notes

- **Opus на дату плана = 8.4/10**: сильный audit-first документ, но уже тогда местами переоценивал severity и любил overspec.
- **Opus против текущего HEAD = 6.1/10**: как карта долга ещё полезен, но как прямой execution blueprint уже заметно устарел.
- **ChatGPT против текущего HEAD = 8.8/10**: обновлённая версия слабее в охвате исторических деталей, но сильнее по текущей точности, верифицируемости и практической полезности.

## Major Corrections Register

Ниже только те тезисы, которые были перепроверены по текущему HEAD и реально влияют на приоритеты.

| Section | Тезис Опуса | Verdict | Severity у Опуса | Severity сейчас | Evidence | Комментарий |
|---|---|---|---|---|---|---|
| `C1` | `ExportHistoryPanel` делает полный rebuild на каждый prepend/delete | obsolete | High | Low / closed | `app/ui/export_history_panel.py:99`, `:119`, `:171` | Горячий путь уже инкрементальный; полный rebuild остался только для `set_history()` и clear. |
| `C2` | Полный webhook URL течёт в обычные логи | partial | Critical/High | Low | `app/core/app_logger.py:51`, `app/core/log_sanitizer.py:67`, `main.py:134` | Обычный logging-поток уже маскируется `SecretFilter`; реальный оставшийся риск — сырые traceback в error dialog / errors.log. |
| `C3 / P.2.2` | GAS chunker и payload path дают O(N²) | false | High | Low | `app/export/sinks/google_apps_script.py:318-407` | Квадратичного обхода строк не подтвердилось; цена в сериализации и полном materialize rows, но не в O(N²). |
| `C8 / Q.2.3` | updater без hash/digest verification | true | Medium/High | High | `app/core/updater.py:80-113` | Это один из главных реальных текущих security-долгов. |
| `C9` | `urlopen` без явного SSL context | mixed | Low | Low | `app/export/sinks/webhook.py:149`, `app/export/sinks/google_apps_script.py:627` | Для webhook/GAS явный context уже есть. Замечание устарело для актуальных sink-ов. |
| `D2` | `ConfigManager.update()` делает fsync-path на UI thread | true | Medium | Medium | `app/config.py:280-322`, `app/ui/settings_form_controller.py:101-105` | Batch-режим уже появился, но autosave всё ещё идёт через диск и остаётся заметным perf-пунктом. |
| `D3` | Лишний `isinstance(rows, list)` в `sql_client` — проблема | obsolete | Low | None | `app/core/sql_client.py:118-144` | Основной guard убран; текущий real issue — `fetchall()` без streaming при `max_rows is None`. |
| `D6` | Двойной импорт `QApplication` в `main.py` | obsolete | Low | None | `main.py:124-137` | Исправлено. |
| `D7 / R.3.1` | `build.spec` с `cipher=block_cipher` — критичный build risk | partial | Medium/High | Low | `build.spec:6`, `:59`, `:63` | Шумный, но не воспроизвёлся как blocker: текущая сборка проходит на 6.19.0. |
| `E1 / R.3.3 / T.1` | `from __future__ import annotations` нужно массово добавить | false for 3.14 urgency | High/Medium | Low | `app/**/*.py`, `tests/test_config.py:364` | Для Python 3.14 это не urgent defect. Сейчас это вопрос стиля/совместимости, не блокер. |
| `E5` | `typing.Callable` остался в `app/ui/threading.py` | false | Low | Low | `app/export/protocol.py:15` | Остаток есть, но в другом файле и это одноместный хвост. |
| `E7 / R.4.1` | `@override` отсутствует | true | Low/Medium | Medium | `app/ui/dashboard_widget.py:57`, `app/ui/debug_window.py:120`, `app/ui/main_window.py:115` | Это хороший low-effort modernity fix, особенно там, где сейчас `# type: ignore[override]`. |
| `A2` | `dashboard_activity_store.py` — микромодуль-долг | obsolete | Low | None | file missing | Файл уже отсутствует; проблема снята. |
| `A5` | `test_run_dialog.py` — только латентная ловушка | confirmed, worsened | Low | Medium | `app/ui/test_run_dialog.py:108`, pytest warning | Сейчас это уже не теоретический риск: `python -m pytest -q` даёт `PytestCollectionWarning`. |
| `Q.2.1` | GAS backend без auth | true | Critical/High | High | `google script back end/src/backend.js:2190-2323` | Реальный и текущий security-gap. |
| `Q.2.2` | layer leakage: `core/export` тянут `ui.formatters` | true | High | Medium | `app/core/sql_client.py:17`, `app/export/pipeline.py:36` | Это не runtime-bug, но реальный архитектурный дефект слоя. |
| `Q.2.4` | backend не пересчитывает checksum | true | High | Medium | `google script back end/src/backend.js` | Payload checksum используется как данные протокола, но backend-side verify не найден. |
| `Q.2.5` | overlay frame в Google Sheets panel может осиротеть | true | High | Medium | `app/ui/export_google_sheets_panel.py:384-397` | Риск умеренный, но технически реальный. |
| `Q.2.6` | delete path должен явно disconnect signal-ы editor-а | partial / likely overstated | High | Low | `app/ui/export_jobs_delete_controller.py:45-64` | Qt auto-disconnect + running-guard снижают риск; это не top-tier bug на текущем HEAD. |
| `Q.2.9` | `database.factory` не wired into pipeline | true | Medium | High | `app/database/factory.py:40`, `app/export/pipeline.py:114`, `app/workers/export_worker.py:61` | Один из главных архитектурных долгов: фабрика и протоколы пока наполовину декларативны. |

## What Opus Missed or Underrated

### 1. Raw traceback leakage path

**Status:** confirmed, missed  
**Severity:** Medium

Evidence:

- `app/ui/error_dialog_helpers.py:21-41`
- `app/ui/error_dialog.py:30-77`

Почему это важнее части старых логging-тезисов:

- обычный logging-поток уже проходит через `SecretFilter`;
- а вот traceback в `errors.log` и clipboard сейчас идёт как есть.

### 2. Real hot path: dashboard activity rebuild

**Status:** confirmed, missed  
**Severity:** Medium

Evidence:

- `app/ui/dashboard_activity.py:13-40`
- `app/ui/main_window_signal_router.py:19-21`

Что происходит:

- на каждый `history_changed` пересобирается до 100 `HistoryRow`;
- это более актуальный UI hot path, чем уже закрытый старый `ExportHistoryPanel` rebuild.

### 3. Full-result memory model in export pipeline

**Status:** confirmed, underestimated  
**Severity:** Medium/High

Evidence:

- `app/export/pipeline.py:80`
- `app/core/sql_client.py:118-144`

Что реально болит:

- export path по-прежнему забирает результат SQL целиком;
- streaming или bounded delivery для больших экспортов всё ещё нет.

## Execution Blueprint Problems in the Opus Plan

Это не проблемы кода, а проблемы самого плана как плана исполнения.

| Problem | Severity | Evidence | Why it matters |
|---|---:|---|---|
| План предполагает clean repo | High | текущий `git status --short` | Сегодня это неверно; execution-волны нельзя слепо запускать поверх грязного HEAD. |
| Команды смешивают POSIX и PowerShell | High | секции `M/N/S` в исходном плане | В этой среде часть команд нужно переписывать, иначе gate-выполнение будет шумно ломаться. |
| Используется `pytest`, хотя рабочая форма здесь `python -m pytest` | Medium | `pytest` не найден в PATH, `python -m pytest -q` работает | Это прямое execution mismatch. |
| Stage/Tags описаны как если бы они ещё не были выполнены | High | теги `stage-1-passed-*` ... `post-refactor-2026-04-17` уже существуют | План не различает уже пройденные и ещё гипотетические шаги. |
| Опус местами overspecifies refactor waves, которые код уже partially absorbed | Medium | `app/domain/`, `app/database/`, `app/export/`, `app/platform/` уже существуют | Часть волн должна быть превращена в cleanup/re-wiring, а не в «создать всё с нуля». |

## Current Bottom Line

### What still holds

- Security around GAS backend and updater.
- Архитектурный долг вокруг реального composition root для DB/sink selection.
- Неполная зрелость новой GAS-интеграции.
- Набор low-effort modernity fixes (`@override`, последний `typing.Callable`, pytest warning на `TestRunDialog`).

### What no longer holds

- Старый high-severity вокруг hot-path rebuild в `ExportHistoryPanel`.
- Старые числовые счётчики по файлам и future-imports.
- Идея, что текущий план можно исполнять как есть, начиная с чистого snapshot-а.

### Final Assessment

- Как исторический audit map: **сильный документ**.
- Как текущий execution plan для HEAD: **требует существенной нормализации**.
- Как база для practical backlog: **полезен, если сначала снять устаревшие тезисы и пересобрать приоритеты**.
