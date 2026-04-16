# iDentBridge Audit Package

Date: `2026-04-16`

## Scope
- Audit-only wave: no product refactor in this package.
- Goal: convert the approved audit plan into a decision-ready artifact with severity, debt mapping, runtime evidence, and Python/dependency readiness notes.
- Platform assumption: Windows-first desktop app. Linux/WSL is used here only as a negative-control environment.

## Execution Evidence
| Item | Value |
|---|---|
| Original branch point | `master @ f2c9d6e` |
| Snapshot branch | `refactoring` |
| Snapshot commit | `eca8774` |
| Current branch after snapshot | `refactoring` |
| Worktree status immediately after snapshot | clean |

Pre-snapshot dirty state included these files and was intentionally preserved inside the safety snapshot commit:

- `app/config.py`
- `app/core/app_logger.py`
- `app/ui/dashboard_widget.py`
- `app/ui/debug_window.py`
- `app/ui/error_dialog.py`
- `app/ui/export_jobs_widget.py`
- `app/ui/history_row.py`
- `app/ui/main_window.py`
- `app/ui/settings_widget.py`
- `app/ui/theme.py`
- `app/workers/export_worker.py`
- `build.spec`
- `main.py`
- `resources/theme.qss`

## Environment Evidence
| Check | Result |
|---|---|
| `python3 -VV` | `Python 3.10.12` on WSL/Linux |
| `python3 -m pytest --version` | `pytest 9.0.3` |
| `python3 -c 'import app.config'` | `app.config: OK` |
| `rg -n '^def test_' tests \| wc -l` | `115` test functions |

Interpretation:

- This repository is not currently self-verifying in the active WSL environment.
- The config/runtime base is now import-safe in WSL for non-GUI checks, but the full app still depends on Windows desktop and ODBC-specific behavior for real validation.
- The documented test gate in [docs/TESTING.md](/mnt/d/ProjectLocal/identa report/docs/TESTING.md:1) now matches the current tree, but the gate is still not reproducible from the active WSL environment.

## Executive Summary
- No confirmed `Critical` findings were reproduced in this audit wave.
- `High` risk is concentrated in reliability/threading, top-level UI orchestration, config/update/release coupling, and the lack of a reproducible automated quality gate from the current repo state.
- `Medium` risk is concentrated in scalability, contract drift, dependency reproducibility, and several fragile platform/runtime assumptions.
- `Low` risk is concentrated in portability constraints that appear intentional, plus local cleanup debt such as broad exception handling and inline UI policy.

## Scorecard
| Dimension | Status | Rationale |
|---|---|---|
| Architecture | `orange` | Strong core helpers exist, but major UI modules still carry multiple responsibilities and high change-risk. |
| Reliability / Threading | `red` | Confirmed late-connect worker races and synchronous update-install in the GUI thread are migration-blocking. |
| Scalability | `orange` | `fetchall()`, full UI rebuilds, and full config rewrites will become noticeable under larger data volumes. |
| Cleanliness | `yellow` | Codebase is readable overall, but naming drift, duplication, inline styles, and broad catches remain visible. |
| Technical Debt | `orange` | Debt is now mapped and localized, but several areas already impede safe refactoring. |
| Testability | `red` | Good core test coverage exists, but widget integration and packaged Windows runtime remain outside the automated gate. |
| Dependency Hygiene | `orange` | The stack is current enough, but `>=` floors without a lock/constraints file make reproduction and upgrades non-deterministic. |
| Python 3.14.4 Readiness | `orange` | Target runtime looks realistic for Windows, but cannot be claimed until the real Windows test environment is green. |

## Findings By Severity
### Critical
- No confirmed critical findings in this audit wave.

### High
1. Worker signal wiring is race-prone in multiple fast-path flows.
   Evidence:
   - [app/ui/dashboard_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/dashboard_widget.py:358)
   - [app/ui/test_run_dialog.py](/mnt/d/ProjectLocal/identa report/app/ui/test_run_dialog.py:168)
   - [app/ui/settings_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/settings_widget.py:638)
   Impact:
   - Fast workers can emit terminal signals before handlers are attached.
   - `_ping_running` can remain stuck and disable future health checks.
   Recommended action:
   - Refactor all callers so terminal and streaming signals are connected before thread start, or extend `run_worker()` with an attach-before-start contract.

2. Update installation still blocks the GUI thread.
   Evidence:
   - [app/ui/main_window.py](/mnt/d/ProjectLocal/identa report/app/ui/main_window.py:276)
   - [app/core/updater.py](/mnt/d/ProjectLocal/identa report/app/core/updater.py:62)
   Impact:
   - Download and file-replacement work can freeze the app during update apply.
   Recommended action:
   - Split "check update" from "download/apply update" and move blocking work out of the GUI thread.

3. Primary UI orchestration is concentrated in god-modules.
   Evidence:
   - [app/ui/export_jobs_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/export_jobs_widget.py:1)
   - [app/ui/settings_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/settings_widget.py:1)
   - [app/ui/main_window.py](/mnt/d/ProjectLocal/identa report/app/ui/main_window.py:1)
   Impact:
   - Refactoring risk is high because UI, persistence, orchestration, and worker control are tightly coupled.
   Recommended action:
   - Treat these files as first-wave separation targets before any broader modernization.

4. The quality gate is not reproducible from the current repo/environment pairing.
   Evidence:
   - [docs/TESTING.md](/mnt/d/ProjectLocal/identa report/docs/TESTING.md:1)
   - [tests](/mnt/d/ProjectLocal/identa report/tests)
   Impact:
   - Current WSL environment cannot run the suite.
   - The current WSL environment cannot run the suite, even though the tree and docs now agree on 115 test functions.
   Recommended action:
   - Rebuild the gate in a clean Windows Python 3.14.4 environment and update documentation only after fresh evidence.

5. Release/runtime identity is split across multiple hardcoded sources and still drifts between `iDentBridge` and `iDentSync`.
   Evidence:
   - [main.py](/mnt/d/ProjectLocal/identa report/main.py:21)
   - [build.spec](/mnt/d/ProjectLocal/identa report/build.spec:1)
   - [VERSIONING.md](/mnt/d/ProjectLocal/identa report/VERSIONING.md:1)
   - [app/core/updater.py](/mnt/d/ProjectLocal/identa report/app/core/updater.py:33)
   - [app/ui/error_dialog.py](/mnt/d/ProjectLocal/identa report/app/ui/error_dialog.py:100)
   Impact:
   - One missed edit can produce mismatched artifact names, updater paths, log locations, or release metadata.
   Recommended action:
   - Centralize app identity, version, artifact name, and updater metadata before any release process hardening.

### Medium
1. Export failures can be counted twice in the editor flow.
   Evidence:
   - [app/workers/export_worker.py](/mnt/d/ProjectLocal/identa report/app/workers/export_worker.py:124)
   - [app/ui/export_jobs_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/export_jobs_widget.py:871)
   - [app/ui/export_jobs_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/export_jobs_widget.py:894)
   Impact:
   - Failure alerts may fire earlier than intended.

2. Scheduler contract drift is real: `cron` appears in the API surface but is not implemented.
   Evidence:
   - [app/core/scheduler.py](/mnt/d/ProjectLocal/identa report/app/core/scheduler.py:19)
   Impact:
   - Callers can believe a mode is supported and discover the truth only at runtime.

3. Scalability hotspots are already visible.
   Evidence:
   - [app/core/sql_client.py](/mnt/d/ProjectLocal/identa report/app/core/sql_client.py:76)
   - [app/ui/test_run_dialog.py](/mnt/d/ProjectLocal/identa report/app/ui/test_run_dialog.py:202)
   - [app/ui/dashboard_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/dashboard_widget.py:308)
   - [app/ui/export_jobs_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/export_jobs_widget.py:1257)
   Impact:
   - Large result sets and large histories will stress UI responsiveness and memory use.

4. Dependency restoration is not deterministic.
   Evidence:
   - [requirements.txt](/mnt/d/ProjectLocal/identa report/requirements.txt:1)
   - [requirements-dev.txt](/mnt/d/ProjectLocal/identa report/requirements-dev.txt:1)
   Impact:
   - Clean environments can drift over time even without repo changes.

5. Secondary UI components also carry refactor-hostile debt.
   Evidence:
   - [app/ui/sql_editor.py](/mnt/d/ProjectLocal/identa report/app/ui/sql_editor.py:1)
   - [app/ui/title_bar.py](/mnt/d/ProjectLocal/identa report/app/ui/title_bar.py:1)
   - [app/ui/error_dialog.py](/mnt/d/ProjectLocal/identa report/app/ui/error_dialog.py:1)
   - [app/ui/debug_window.py](/mnt/d/ProjectLocal/identa report/app/ui/debug_window.py:1)
   Impact:
   - Even after primary screen refactors, several support components remain tightly coupled and weakly testable.

### Low
1. Windows-only portability is explicit but still a maintenance constraint.
   Evidence:
   - [app/config.py](/mnt/d/ProjectLocal/identa report/app/config.py:95)
   - [app/core/dpapi.py](/mnt/d/ProjectLocal/identa report/app/core/dpapi.py:1)
   - [app/core/startup.py](/mnt/d/ProjectLocal/identa report/app/core/startup.py:1)
   Impact:
   - Cross-platform packaging is not a realistic near-term goal without architectural changes.

2. Cleanup debt remains in broad exception handling, inline style policy, and stringly-typed theme usage.
   Evidence:
   - [app/ui/theme.py](/mnt/d/ProjectLocal/identa report/app/ui/theme.py:1)
   - [app/ui/widgets.py](/mnt/d/ProjectLocal/identa report/app/ui/widgets.py:1)
   - [app/ui/history_row.py](/mnt/d/ProjectLocal/identa report/app/ui/history_row.py:1)
   Impact:
   - Low immediate risk, but these patterns increase maintenance overhead.

## Component Debt Matrix
### Core, Config, Workers
| Component | Severity | Debt summary |
|---|---|---|
| [app/config.py](/mnt/d/ProjectLocal/identa report/app/config.py:1) | `high` | Import-time `APPDATA`, non-atomic save, permissive update path, silent cache fallback. |
| [app/core/constants.py](/mnt/d/ProjectLocal/identa report/app/core/constants.py:1) | `low` | Hardcoded repo/update metadata. |
| [app/core/connection.py](/mnt/d/ProjectLocal/identa report/app/core/connection.py:1) | `medium` | DSN builder assumes simple unescaped values. |
| [app/core/dpapi.py](/mnt/d/ProjectLocal/identa report/app/core/dpapi.py:1) | `low` | Hard Windows-only import coupling. |
| [app/core/app_logger.py](/mnt/d/ProjectLocal/identa report/app/core/app_logger.py:1) | `low` | Root logger side effects and bootstrap-order coupling. |
| [app/core/instance_scanner.py](/mnt/d/ProjectLocal/identa report/app/core/instance_scanner.py:1) | `high` | Registry/sqlcmd coupling, swallowed failures, eager listing. |
| [app/core/odbc_utils.py](/mnt/d/ProjectLocal/identa report/app/core/odbc_utils.py:1) | `medium` | Brittle dependence on driver naming and legacy fallback ladder. |
| [app/core/scheduler.py](/mnt/d/ProjectLocal/identa report/app/core/scheduler.py:1) | `high` | API/runtime contract drift for `cron`; late validation. |
| [app/core/sql_client.py](/mnt/d/ProjectLocal/identa report/app/core/sql_client.py:1) | `medium` | `fetchall()`, flattened diagnostics, partial retry coverage. |
| [app/core/startup.py](/mnt/d/ProjectLocal/identa report/app/core/startup.py:1) | `medium` | Tight Run-key coupling and silent drift. |
| [app/core/updater.py](/mnt/d/ProjectLocal/identa report/app/core/updater.py:1) | `high` | Fragile release assumptions and weak diagnostics. |
| [app/workers/export_worker.py](/mnt/d/ProjectLocal/identa report/app/workers/export_worker.py:1) | `high` | Full materialization in memory; poor failure semantics. |
| [app/workers/update_worker.py](/mnt/d/ProjectLocal/identa report/app/workers/update_worker.py:1) | `medium` | Multiple failure classes collapsed into a single string path. |

### UI
| Component | Severity | Debt summary |
|---|---|---|
| [app/ui/export_jobs_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/export_jobs_widget.py:1) | `high` | Primary god-module for editor state, history, scheduling, persistence, and orchestration. |
| [app/ui/settings_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/settings_widget.py:1) | `high` | SQL discovery, DB listing, connection test, autostart, update flow, and settings UI mixed together. |
| [app/ui/dashboard_widget.py](/mnt/d/ProjectLocal/identa report/app/ui/dashboard_widget.py:1) | `high` | Ping orchestration, history aggregation, update banner, and race-prone worker path mixed together. |
| [app/ui/main_window.py](/mnt/d/ProjectLocal/identa report/app/ui/main_window.py:1) | `high` | Navigation, tray, update flow, debug panel, exception hook, cleanup, and cross-screen orchestration. |
| [app/ui/sql_editor.py](/mnt/d/ProjectLocal/identa report/app/ui/sql_editor.py:1) | `high` | Highlighter, editor behavior, overlay UI, and dialog shell are all fused. |
| [app/ui/title_bar.py](/mnt/d/ProjectLocal/identa report/app/ui/title_bar.py:1) | `high` | Styling, event filtering, drag logic, and host-window behavior are tightly coupled. |
| [app/ui/error_dialog.py](/mnt/d/ProjectLocal/identa report/app/ui/error_dialog.py:1) | `high` | Error UI, logging, rotation, and global hook management in one module. |
| [app/ui/test_run_dialog.py](/mnt/d/ProjectLocal/identa report/app/ui/test_run_dialog.py:1) | `medium` | Late signal wiring and heavy table population path. |
| [app/ui/debug_window.py](/mnt/d/ProjectLocal/identa report/app/ui/debug_window.py:1) | `medium` | Hard dependency on current logger format and live handler API. |
| [app/ui/history_row.py](/mnt/d/ProjectLocal/identa report/app/ui/history_row.py:1) | `medium` | Data normalization, timestamp formatting, and rendering all in-widget. |
| [app/ui/lucide_icons.py](/mnt/d/ProjectLocal/identa report/app/ui/lucide_icons.py:1) | `medium` | Rendering, recolor, cache policy, and resource-layout knowledge mixed together. |
| [app/ui/threading.py](/mnt/d/ProjectLocal/identa report/app/ui/threading.py:1) | `low` | Good helper overall; most risk lives in callers. |
| [app/ui/theme.py](/mnt/d/ProjectLocal/identa report/app/ui/theme.py:1) | `low` | Good central token layer, but consumers still bypass it and values are stringly-typed. |
| [app/ui/widgets.py](/mnt/d/ProjectLocal/identa report/app/ui/widgets.py:1) | `low` | Useful shared helpers, but still encode UI policy in Python. |
| [app/ui/icons_rc.py](/mnt/d/ProjectLocal/identa report/app/ui/icons_rc.py:1) | `none` | Generated artifact. |

### Runtime, Build, Tests, Docs
| Component | Severity | Debt summary |
|---|---|---|
| [main.py](/mnt/d/ProjectLocal/identa report/main.py:1) | `high` | Version/runtime identity still hardcoded and duplicated. |
| [build.spec](/mnt/d/ProjectLocal/identa report/build.spec:1) | `high` | Packaging identity drifts from runtime and updater metadata. |
| [docs/TESTING.md](/mnt/d/ProjectLocal/identa report/docs/TESTING.md:1) | `high` | Stale test-count gate and partially drifted verification story. |
| [VERSIONING.md](/mnt/d/ProjectLocal/identa report/VERSIONING.md:1) | `medium` | Useful policy doc, but not executable source of truth. |
| [requirements.txt](/mnt/d/ProjectLocal/identa report/requirements.txt:1) | `medium` | Lower bounds only; no deterministic restore path. |
| [requirements-dev.txt](/mnt/d/ProjectLocal/identa report/requirements-dev.txt:1) | `medium` | Same reproducibility gap as runtime requirements. |
| [tests](/mnt/d/ProjectLocal/identa report/tests) | `medium` | Good core coverage, weak packaged/Windows/UI integration coverage. |
| [docs/VERIFICATION.md](/mnt/d/ProjectLocal/identa report/docs/VERIFICATION.md:1) | `low` | Explicit Windows assumptions are useful, but the manual-only path remains fragile. |

## Dependency And Python Readiness Snapshot
Observed from current audit tooling:

| Package | Repo floor | Latest observed | Audit note |
|---|---|---|---|
| `PySide6-Essentials` | `>=6.7` | `6.11.0` | Current pip index shows a current release line compatible with staying on the modern Qt stack. |
| `pyodbc` | `>=5.1` | `5.3.0` | Runtime still depends on external Microsoft ODBC drivers on Windows. |
| `sqlglot` | `>=27.0` | `30.4.3` | Very active package cadence; pure-Python package reduces runtime risk. |
| `Pillow` | `>=10.0` | `12.2.0` | Current WSL env already has `12.0.0`; security review should stay active because this library has frequent upstream churn. |
| `pytest` | `>=8.0` | `9.0.3` | Present in the current WSL env, but the documented test gate still needs Windows 3.14.4 validation. |
| `pytest-qt` | `>=4.4` | `4.5.0` | Still the least certain part of a future Python 3.14.4 story; validate in the real Windows test env. |

Observed security query notes:

- Current OSV API query returned no active findings for `PySide6-Essentials`, `pyodbc`, and `sqlglot` during this run.
- The same query path became unstable while continuing through the full package list due SSL EOF failures from the current WSL environment.
- Treat dependency security as `incomplete but non-alarming` until the same pass is repeated in the clean Windows validation environment.

Python readiness:

- Python `3.14.4`: the intended target baseline for Windows, but not claimable until the real Windows environment can install the stack and run the full gate.

## Recommended Next Sequence
1. Recreate the documented environment on Windows 10/11 with Python 3.14.4 and the required ODBC driver.
2. Re-run the full test and manual verification flow there, then record fresh evidence.
3. Fix the `High` reliability blockers before any broad refactor or Python upgrade wave.
4. Centralize app identity/version/update metadata before touching release engineering again.
5. Only after the above decide whether the next execution wave targets stabilization, debt reduction, or Python 3.14.4 adoption.

## Audit Conclusion
- This repository is not in crisis, but it is not ready for a broad modernization pass without first paying down several concentrated `High`-severity risks.
- The safest path is still audit-first on `refactoring`, followed by a narrowly scoped reliability wave, then a reproducible Windows 3.14.4 validation pass, and only then a decision on a runtime upgrade.
