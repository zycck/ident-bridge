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

