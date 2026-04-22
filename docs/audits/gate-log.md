# Gate log

Журнал прохождения gate-проверок по этапам плана `proud-twirling-moore`.

Формат: Stage N — дата — pytest / launch smoke / build / EXE smoke / tag.

## Stage 1 — 2026-04-17

- **N.1 pytest:** PASS — 328 passed in 2.23 s (baseline 299 + 29 new)
- **N.2 launch smoke:** PASS — `positive_retained_kib=2073.5` (baseline 2362.7, delta **−12.2 %**)
- **N.3 build:** PASS — `dist/iDentSync.exe` 40 736 321 bytes (40.7 MB)
- **N.4 EXE smoke:** PASS — process alive 15 s, killed cleanly
- **Tag:** `stage-1-passed-20260417`
- **Scope:** SecretFilter (audit C2) + ResourceMonitor/Bar (audit K)
- **Commits:** `ad55af8` + `18b9f75`

## Stage 2 — 2026-04-17

- **N.1 pytest:** PASS — 337 passed in 2.34 s (+9 from Stage 1: batch context + incremental-history)
- **N.2 launch smoke:** PASS — `positive_retained_kib=2072.1` (baseline 2362.7, delta **−12.3 %**)
- **N.3 build:** PASS — `dist/iDentSync.exe` 40 739 574 bytes (40.7 MB)
- **N.4 EXE smoke:** PASS — process alive 15 s, killed cleanly
- **Tag:** `stage-2-passed-20260417`
- **Scope:** incremental history (C1) + explicit ssl_context (C9) + ConfigManager.batch (D2/J1) + tmp_replaced safeguard (C4) + QApplication dedup (D6) + drop fetchall coercion (D3/J7-f)
- **Commits:** `8066e5c` `f9f90bb` `be32ef7` `e2bf031` `bc1076d` `251602d` `cee48e1`

## Stage 3 — 2026-04-17

- **N.1 pytest:** PASS — 361 passed in 2.40 s (+24 new: WebhookSink protocol/encoder/retry + ExportPipeline factory/disconnect paths)
- **N.2 launch smoke:** PASS — `positive_retained_kib=2072.7` (baseline 2362.7, delta **−12.3 %**)
- **N.3 build:** PASS — `dist/iDentSync.exe` 40 747 155 bytes (40.7 MB)
- **N.4 EXE smoke:** PASS — process alive 15 s, killed cleanly
- **Tag:** `stage-3-passed-20260417`
- **Scope:** ExportSink Protocol + WebhookSink + ExportPipeline + thin ExportWorker (audit G-1/J2, partial C3)

## Stage 4 — 2026-04-17

- **N.1 pytest:** PASS — 368 passed in 2.37 s (+7 new DatabaseClient factory tests)
- **N.2 launch smoke:** PASS — `positive_retained_kib=2072.2` (baseline 2362.7, delta **−12.3 %**)
- **N.3 build:** PASS — `dist/iDentSync.exe` 40 747 704 bytes (40.7 MB)
- **N.4 EXE smoke:** PASS — process alive 15 s, killed cleanly
- **Tag:** `stage-4-passed-20260417`
- **Scope:** DatabaseClient Protocol + factory (audit G-2/I; API-only, physical move deferred to Stage 5)

## Stage 5A — 2026-04-17

- **N.1 pytest:** PASS — 377 passed in 2.37 s (+9 canonical-path tests)
- **N.2 launch smoke:** PASS — `positive_retained_kib=2073.0` (baseline 2362.7, delta **−12.3 %**)
- **N.3 build:** PASS — `dist/iDentSync.exe` 40 747 539 bytes (40.7 MB)
- **N.4 EXE smoke:** PASS — process alive 15 s, killed cleanly
- **Tag:** `stage-5a-passed-20260417`
- **Scope:** Canonical paths for `app/domain/`, `app/platform/`, `app/log_ext/` (re-export shims; no physical moves yet)
- **Deferred (waves 5B / 5C):** split `app/config.py` into `app/config/` package; move UI families into `app/ui/<feature>/` subpackages. Both are mechanical but touch 70+ import sites and are safer to perform in an isolated session with the full focus of the tooling.

## Stage 6 — 2026-04-17

- **N.1 pytest:** PASS — 377 passed in 2.41 s
- **N.2 launch smoke:** PASS — `positive_retained_kib=2071.7` (baseline 2362.7, delta **−12.3 %**)
- **N.3 build:** PASS — `dist/iDentSync.exe` 40 747 769 bytes (40.7 MB)
- **N.4 EXE smoke:** PASS — process alive 15 s, killed cleanly
- **Tag:** `stage-6-passed-20260417`
- **Scope:** match in scheduler (E3/J4) + merge dashboard_activity_store (A2) + dedup ts formatters (A3)
- **Deferred:** SettingsSqlController split (A1) + test_run_dialog rename (A5) — both touch many import sites; rolled into a future focused session

## Stage 7 — 2026-04-17

- **N.1 pytest:** PASS — 377 passed in 2.42 s
- **N.2 launch smoke:** PASS — `positive_retained_kib=2069.4` (baseline 2362.7, delta **−12.4 %**)
- **N.3 build:** PASS — `dist/iDentSync.exe` 40 747 376 bytes (40.7 MB)
- **N.4 EXE smoke:** PASS — process alive 15 s, killed cleanly
- **Tag:** `stage-7-passed-20260417`
- **Scope:** strip 138× `# -*- coding: utf-8 -*-` (E2) + `collections.abc.Callable` in threading.py (E5)
- **Deferred:** `from __future__ import annotations` mass add (E1), `NotRequired[...]` rewrite (E4), `@override` markers (E7)

## Stage 8 — 2026-04-22

- **N.1 pytest:** PASS — 524 passed in 4.27 s
- **N.2 perf smoke:** PASS — `gas-chunking` `positive_retained_kib=0.7`
- **N.3 build:** SKIP — code-only safety slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** worker shutdown hardening + export autosave coalescing
- **Commit:** `05a61af`

## Stage 9 — 2026-04-22

- **N.1 pytest:** PASS — 529 passed
- **N.2 perf smoke:** PASS — `gas-chunking` `positive_retained_kib=0.7`; `settings-widget` stable over repeated cycles
- **N.3 build:** SKIP — code-only safety slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** debounce settings I/O + config cache + worker lifetime hardening
- **Commit:** `6a1200d`

## Stage 10 — 2026-04-22

- **N.1 pytest:** PASS — 529 passed
- **N.2 perf smoke:** PASS — `gas-chunking` `positive_retained_kib=0.7`
- **N.3 build:** SKIP — code-only safety slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** async dashboard activity refresh off GUI thread
- **Commit:** `8c78ecf`

## Stage 11 — 2026-04-22

- **N.1 pytest:** PASS — 534 passed
- **N.2 perf smoke:** PASS — `main-window` scenario no longer hangs on temp-dir cleanup
- **N.3 build:** SKIP — code-only safety slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** explicit SQLite connection close + lazy export editor creation
- **Commit:** `668c238`

## Stage 12 — 2026-04-22

- **N.1 pytest:** PASS — 535 passed
- **N.2 perf smoke:** PASS — `export-editor` false linear leak removed; `positive_retained_kib` stabilized around `1006 KiB` over repeated cycles
- **N.3 build:** SKIP — code-only safety slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** flush `DeferredDelete` in perf harness so retained-memory readings are honest
- **Commit:** `1f99fd2`

## Stage 13 — 2026-04-22

- **N.1 pytest:** PASS — 535 passed
- **N.2 perf smoke:** PASS — `main-window` scenario green after scheduler fix
- **N.3 build:** SKIP — code-only safety slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** scheduler without wall-clock drift; no random jitter; scheduled start while running stays idempotent
- **Commit:** `c4bd960`

## Stage 14 — 2026-04-22

- **N.1 pytest:** PASS — 536 passed
- **N.2 perf smoke:** PASS — `gas-chunking` `positive_retained_kib=0.9`
- **N.3 build:** SKIP — code-only safety slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** one-pass GAS chunk planner; peak synthetic planner memory down from `7718.2 KiB` to `3951.0 KiB`
- **Commit:** `9546261`

## Stage 15 — 2026-04-22

- **N.1 pytest:** PASS — 539 passed in 5.15 s
- **N.2 perf smoke:** PASS — `gas-chunking` `positive_retained_kib=0.9`
- **N.3 build:** SKIP — docs + correctness slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** preserve `manual/scheduled` trigger in GAS SQLite journal + refresh TESTING/PERFORMANCE docs to current gate numbers
- **Commit:** `ba65eed`

## Stage 16 — 2026-04-22

- **N.1 pytest:** PASS — 536 passed in 5.13 s
- **N.2 perf smoke:** PASS — `gas-chunking` `positive_retained_kib=0.9`
- **N.3 build:** SKIP — safe dead-code cleanup, packaged build not rerun
- **N.4 EXE smoke:** SKIP — desktop smoke not rerun
- **Scope:** remove test-only `sync_path()` autostart helper, drop dead updater helper `_pick_download_url()`, remove dead webhook retry re-exports, sync docs to new test count
- **Commits:** `04695ae` + working-tree docs sync

## Stage 17 - 2026-04-22

- **N.1 pytest:** PASS - 541 passed in 5.75 s
- **N.2 perf smoke:** PASS - `main-window` `positive_retained_kib=1390.4`
- **N.3 build:** SKIP - bugfix/doc slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP - desktop smoke not rerun
- **Scope:** restore export history counts in dashboard/editor/tiles, preserve config-history fallback when SQLite is empty, record generic export failures in history, route worker callbacks back to GUI thread, sync TESTING baseline to current count
- **Commit:** `7d02607`

## Stage 18 - 2026-04-22

- **N.1 pytest:** PASS - 544 passed in 5.49 s
- **N.2 perf smoke:** PASS - `gas-chunking` `positive_retained_kib=0.9`
- **N.3 build:** SKIP - code-only seam slice, packaged build not rerun
- **N.4 EXE smoke:** SKIP - desktop smoke not rerun
- **Scope:** switch export pipeline default DB construction to `app.database.create_database_client`, keep `sql_client_cls` only as test override, add regression for factory-backed default path, sync TESTING baseline
- **Commit:** current refactor-v3 slice
