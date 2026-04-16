# Testing & Verification Guide

This guide walks you through verifying every critical feature of
iDentBridge step by step. Use it before any release or after major
changes. It answers the question: *"Как убедиться, что приложение
отработает на сто процентов?"*

Audit note: the current tree contains 178 `test_*` functions, and this
workspace is a WSL/Linux negative-control environment. The full gate is
expected to be validated on Windows 11 with Python 3.14.4 and the
documented Qt stack; tray, registry, reboot, and background-run checks
still need a real Windows desktop session.

The short answer is: run the automated suite first (catches regressions
in seconds), then walk through the manual checks below in order — they
cover what no automated test can: the real tray icon, a real scheduler
loop, real Windows registry writes, and real background execution.
App identity constants live in `app/core/constants.py`.

---

## Quick reference

| Check | How | Time |
|---|---|---|
| Automated test suite | `python -m pytest tests/` | ~1 sec |
| Headless smoke | one-liner (see §2) | 5 sec |
| Packaged build smoke | `python -m PyInstaller build.spec --noconfirm ...` | ~1-2 min |
| Live tray + scheduler | manual with FAST\_TRIGGER | ~1 min |
| Background execution | manual | ~2 min |
| Manual trigger (▶) | manual | 30 sec |
| Test-dialog trigger | manual | 30 sec |
| Autostart on reboot | manual + reboot | ~5 min |
| Failure notifications | manual | ~1 min |
| Settings persistence | manual | 1 min |
| Debug console | manual | 30 sec |
| Performance smoke | `python tools/perf_smoke.py --scenario all --cycles 5` | ~10 sec |
| Full release checklist | `docs/VERIFICATION.md` | 15 min |

---

## 1. Automated test suite

The fastest sanity check. **199 test functions / 200 collected test items** covering the scheduler engine,
export worker pipeline, config persistence, threading helpers, tray
behaviour, and Windows autostart.

The current tree actually contains **199 tests**. Keep this number in
sync with the tree, or the release checklist will drift again.

### One-time setup

```bash
cd "D:\ProjectLocal\identa report"
pip install -r requirements.txt -r requirements-dev.txt -c constraints-py314-win.txt
```

### Run

```bash
python -m pytest tests/ -v
```

Expected output:

```
200 passed in X.XXs
```

If anything fails, the test name + assertion message tells you exactly
which feature regressed. **Do not proceed with manual testing until
the automated suite is fully green.**

For packaged smoke on the same validated stack:

```bash
python -m PyInstaller build.spec --noconfirm --distpath build/dist --workpath build/work --clean
build\dist\iDentSync.exe
```

Expected result: the `.exe` is produced successfully, starts, and can be
closed cleanly.

### Coverage map

| Test file | What it covers | Tests |
|---|---|---|
| `tests/test_scheduler.py` | supported schedule modes, jitter (±5 %), DST, timezone-aware next\_run, signal emission, stop/start lifecycle, invalid-mode validation | 23 |
| `tests/test_export_worker.py` | 4-step pipeline (connect → query → webhook → disconnect), DB errors, webhook errors, retry, SyncResult | 16 |
| `tests/test_config.py` | DPAPI roundtrip, update/merge, migration of legacy fields, JSON corruption resilience, save/load roundtrip, atomic save, config-dir fallback | 19 |
| `tests/test_threading.py` | `run_worker` factory, GC pin attribute, thread lifecycle, on\_error / on\_finished callbacks, late signal connection safety | 13 |
| `tests/test_tray_autostart.py` | tray close-to-tray behaviour, `register`/`unregister`/`sync_path`, registry read/write (mocked), main window construction, import-safe non-Windows autostart | 21 |
| `tests/test_connection.py` | ODBC connection-string escaping and trusted-connection fallback | 3 |
| `tests/test_instance_scanner.py` | registry/network instance discovery fallbacks, deduplication, database listing without hard pyodbc dependency | 6 |
| `tests/test_odbc_utils.py` | driver detection priority and missing-pyodbc diagnostics | 3 |
| `tests/test_sql_client.py` | escaped DSN building, missing-pyodbc behavior, query materialization, clearer connection-failure reporting | 5 |
| `tests/test_updater.py` | release asset selection, download helper, apply helper exit path | 4 |
| `tests/test_export_failure_alerts.py` | export failure counter thresholding and reset-after-success behavior | 2 |
| `tests/test_dashboard_activity_panel.py` | extracted dashboard activity panel: aggregated count, empty clear no-op, clear cancel/confirm behavior | 4 |
| `tests/test_dashboard_activity_store.py` | extracted dashboard activity store: pure history clearing and payload preservation | 2 |
| `tests/test_dashboard_ping_timer.py` | extracted dashboard ping timer: timer setup, deferred first ping, safe stop lifecycle | 2 |
| `tests/test_dashboard_update_banner.py` | extracted dashboard update banner: banner visibility, URL retention, request emission, in-progress state | 4 |
| `tests/test_dashboard_status_cards.py` | extracted dashboard status cards: connection state mapping, default labels, last-sync formatting | 3 |
| `tests/test_export_editor_header.py` | extracted export editor header: title editing, status summary, action signals | 2 |
| `tests/test_export_editor_runtime.py` | extracted export editor runtime: trigger bookkeeping, success/error status, alert thresholding | 3 |
| `tests/test_export_execution_controller.py` | extracted export execution controller: manual/scheduled starts, progress, success/error routing, test-entry recording | 4 |
| `tests/test_export_history_panel.py` | extracted export history panel: render, delete, clear-confirm behavior | 3 |
| `tests/test_export_jobs_store.py` | extracted export jobs store: raw normalization, config-preserving save, blank job creation | 3 |
| `tests/test_export_jobs_widget.py` | extracted export jobs pages: tiles/editor routing and reflow safety | 2 |
| `tests/test_export_schedule_panel.py` | extracted export schedule panel: validation, placeholder, round-trip state | 3 |
| `tests/test_export_sql_panel.py` | extracted export SQL panel: round-trip text, syntax indicator, empty reset | 3 |
| `tests/test_settings_helpers.py` | extracted settings helpers: instance parsing, autosave DB selection, config payload building | 4 |
| `tests/test_settings_actions.py` | extracted settings actions: startup toggle outcome handling | 2 |
| `tests/test_settings_app_panel.py` | extracted settings app panel: version text, startup toggle signal, update-request signal | 2 |
| `tests/test_settings_form_controller.py` | extracted settings form controller: load/save/autosave flow, DB tracking, config-preserving save | 5 |
| `tests/test_settings_sql_controller.py` | extracted settings SQL controller: scan orchestration, pending DB replay, auto-advance fallback, connection-test gating, scan error recovery | 6 |
| `tests/test_settings_sql_flow.py` | extracted settings SQL flow: scan/db-list/test state transitions and restore behavior | 4 |
| `tests/test_settings_sql_presenters.py` | extracted settings SQL presenters: instance/database list rendering and next-instance selection | 3 |
| `tests/test_main_window_lifecycle.py` | extracted main-window lifecycle: tray activation, close-to-tray notice, quit path, shutdown cleanup | 4 |
| `tests/test_main_window_navigation.py` | extracted main-window navigation: page order, button routing, active state/icon switching | 4 |
| `tests/test_main_window_pages.py` | extracted main-window pages: page construction and stack order | 1 |
| `tests/test_main_window_signal_router.py` | extracted main-window signal router: dashboard/update wiring, sync/history routing, tray failure alerts | 3 |
| `tests/test_main_window_chrome.py` | extracted main-window chrome: title-bar signal wiring, maximize/restore toggling, state-change icon sync | 4 |
| `tests/test_main_window_debug.py` | extracted main-window debug coordination: lazy create, toggle visibility, safe close | 4 |

### What the automated suite does NOT cover

These are tested by the manual sections that follow:

- **Real ODBC connection** — the SQL client is mocked; no actual
  SQL Server is contacted
- **Real webhook call** — HTTP is mocked; no actual POST is sent
- **Real Windows registry** — winreg is mocked; nothing is written
  to HKCU during tests
- **Real tray icon rendering** — the tray is created offscreen;
  visual presence in the notification area is not verified
- **Real background execution** — timer intervals are mocked; actual
  wall-clock firing is not tested
- **Autostart after reboot** — requires a real reboot

### Environment limitations to keep in mind

- The automated suite is written to run with `QT_QPA_PLATFORM=offscreen`
  so it can exercise Qt objects without opening visible windows.
- The current WSL/Linux audit environment cannot be treated as the
  source of truth for the full gate; it does not represent a Windows
  desktop session and cannot validate tray, registry, or reboot flows.
- If `python -m pytest tests/` is being used as a release gate, run it
  on Windows 11 with Python 3.14.4, the project's documented
  dependencies installed, and a real desktop session available for the
  manual checks.
- For the exact dependency set that has already gone green in this repo,
  prefer the pinned constraints file:
  `pip install -r requirements.txt -r requirements-dev.txt -c constraints-py314-win.txt`

---

## 2. Headless smoke (5 seconds)

Verifies that the application constructs cleanly end-to-end without
showing any window. This catches import errors, missing assets, and
`__init__` crashes that the unit tests would not surface.

```bash
cd "D:\ProjectLocal\identa report"
python -c "
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
app = QApplication([])
import main
main._load_fonts()
main._load_app_icon(app)
qss = main._load_theme()
app.setStyleSheet(qss)
from app.config import ConfigManager
from app.ui.main_window import MainWindow
window = MainWindow(ConfigManager(), '0.0.1-test')
print('MainWindow constructs OK')
"
```

Expected output: `MainWindow constructs OK`

If this fails, look at the traceback — it will point to the exact
module that is broken. Nothing else will work until this passes.

---

## 3. Live tray + scheduler (FAST\_TRIGGER mode)

This is the most important manual test. It verifies the full
scheduled-trigger loop:

1. The app appears in the Windows system tray
2. The scheduler fires on schedule (every 10 seconds in dev mode)
3. Fired exports produce history entries with the correct trigger type
4. The scheduler keeps running while the main window is hidden

The environment variable `IDENTBRIDGE_FAST_TRIGGER_SECONDS` is read
by `SyncScheduler.start()` in `app/core/scheduler.py`. When set to a
positive integer, the scheduler ignores the configured daily/hourly
mode and fires that many seconds repeatedly instead.

### Setup

Open a terminal and run:

```cmd
set IDENTBRIDGE_FAST_TRIGGER_SECONDS=10
python main.py
```

You should see:

- The main window opens
- A tray icon (lime database cylinder) appears in the Windows
  notification area (bottom-right, next to the clock)
- In the debug log (Ctrl+D): `WARNING ... FAST_TRIGGER mode active:
  firing every 10 seconds (dev only)`

Right-click the tray icon and verify the context menu shows three
items: **Открыть**, **Проверить обновление**, **Выход**.

### Step-by-step test

1. Click **Выгрузки** in the left navigation sidebar
2. Click **+ Добавить**
3. Fill in the new job tile:
   - **Название**: `Quick Test`
   - **SQL запрос**: `SELECT 1 AS x`
   - **Webhook URL**: leave blank (or use `https://webhook.site` for a
     real end-to-end webhook test)
   - **Расписание**: set any value — it will be ignored in FAST\_TRIGGER
     mode, but the field must be filled for the scheduler to start
4. Toggle **Запускать автоматически** → ON
5. Click **← Назад к списку**
6. Wait approximately 10 seconds
7. Click the tile to open the editor
8. Scroll to the **История** section

**Verify:** at least one entry is present with:

- A clock icon on the left (scheduled trigger)
- A lime-green left accent bar
- Today's date and current time
- Status: `✓ N строк` (where N is the row count from the query)

If the history is empty after 15 seconds, check:

- The job's **Запускать автоматически** toggle is ON
- The debug log (Ctrl+D) shows SCHEDULED trigger log lines
- The env var is set *in the same terminal* where `python main.py`
  was launched

### Background execution test

Continue with the same FAST\_TRIGGER session:

1. While the editor is open, click the **X** button in the title bar
2. **Verify:** the main window disappears
3. **Verify:** the tray icon is still visible in the notification area
   (if this is the first time you've ever closed to tray, a balloon
   notification appears: *"iDentBridge свёрнут в трей"*)
4. **Verify:** the Windows process is still running (check Task Manager
   → look for `python.exe`)
5. Wait 30–40 seconds
6. Single-click or double-click the tray icon
7. **Verify:** the main window reappears
8. Navigate to the **Quick Test** tile → click it to open the editor
9. **Verify:** 3–4 additional history entries appeared while the window
   was hidden

This proves the scheduler thread and export worker continue running
independently of the UI.

### Cleanup

```cmd
set IDENTBRIDGE_FAST_TRIGGER_SECONDS=
```

Unset the variable before doing any further tests so normal scheduling
behaviour is restored.

---

## 4. Manual trigger test (▶ button)

Verifies that the **play button on the tile** fires an immediate
on-demand export with the correct trigger type.

1. On the **Выгрузки** tile list, locate any job
2. Click the **▶** button directly on the tile (the small play icon
   in the tile's action bar — NOT the Run button inside the editor)
3. **Verify:** within 1–2 seconds, a new history entry appears
4. Open the tile editor and scroll to **История**
5. **Verify:** the newest entry has:
   - A **mouse-pointer-click** icon on the left
   - A blue left accent bar (manual trigger)
   - Status: `✓ N строк`

The manual trigger bypasses the scheduler entirely and uses the same
export worker pipeline as the scheduled trigger.

---

## 5. Test trigger (test dialog)

Verifies that the **Тест** button in the editor creates a dedicated
TEST history entry and that the SQL preview dialog works.

1. Open any job's editor (click a tile)
2. Click **Тест** in the editor header area
3. **Verify:** the test dialog opens with:
   - The job's SQL pre-filled in the editor
   - The query auto-runs immediately
   - Results shown in a table
4. Close the dialog (✕ or Закрыть)
5. Scroll to **История** in the editor
6. **Verify:** a new entry appears with:
   - A **flask-conical** icon on the left
   - A gray left accent bar (TEST trigger)
   - Status reflecting the result

TEST entries are cosmetically distinct from scheduled and manual entries
so they are never confused with production runs.

---

## 6. SQL editor full-screen

Verifies the expand button opens the full-screen SQL editor dialog.

1. In a job editor, find the SQL field
2. Click the **↗ expand** icon in the top-right corner of the SQL
   textarea
3. **Verify:** `SqlEditorDialog` opens at approximately 1100×720
4. **Verify:** syntax highlighting is active (keywords coloured)
5. Edit the SQL, click **Сохранить**
6. **Verify:** the inline SQL field in the editor reflects the change

---

## 7. Autostart with Windows

Verifies the app registers itself in the Windows Run registry key and
survives a cold reboot.

The relevant code lives in `app/core/startup.py`. The registry path is:

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

### Register

1. Run `python main.py`
2. Navigate to **Настройки**
3. Toggle **Запускать с Windows** → ON
4. Click **Сохранить**
5. Open Command Prompt and verify the registry entry:
   ```cmd
   reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v iDentBridge
   ```
6. **Verify:** the output shows a `REG_SZ` value pointing to the
   correct path (`python.exe main.py` for a dev install, or the
   frozen `.exe` path for a packaged build)

### Reboot test

1. Reboot Windows
2. After login, wait 30 seconds
3. **Verify:** the iDentBridge tray icon appears in the notification
   area without any manual action
4. Click (or double-click) the tray icon
5. **Verify:** the main window opens
6. **Verify:** all previously configured jobs are present with their
   history intact

### Unregister

1. Navigate to **Настройки** → toggle **Запускать с Windows** → OFF
2. Click **Сохранить**
3. Verify the registry value is gone:
   ```cmd
   reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v iDentBridge
   ```
   Expected output:
   ```
   ERROR: The system was unable to find the specified registry key or value.
   ```

### Path sync

If you move the iDentBridge folder after registering autostart, the
stored registry path becomes stale. The app calls `startup.sync_path()`
on every launch to detect and fix this. To test manually:

1. Register autostart (toggle ON)
2. Move (or rename) the project folder
3. Relaunch `python main.py` from the new location
4. **Verify:** `reg query` shows the updated path

---

## 8. Failure handling + tray notifications

Verifies that 3 consecutive export failures produce a tray balloon
notification and that recovering from the failure resets the counter.

### Setup

1. Set `IDENTBRIDGE_FAST_TRIGGER_SECONDS=10`
2. Create a job with a deliberately invalid SQL query:
   ```sql
   SELECT * FROM table_that_does_not_exist_xyz
   ```
3. Toggle **Запускать автоматически** → ON
4. Wait about 30 seconds (3 trigger cycles)

### Verify failures

- **Verify:** 3+ red history entries appear, each with an error message
  describing the DB failure
- **Verify:** a tray balloon notification appears after the 3rd
  consecutive failure:
  *"Выгрузка \<name\> не работает: 3 неудачных запуска подряд"*
- The balloon auto-dismisses after ~8 seconds

### Recovery test

1. Fix the SQL (e.g., change it to `SELECT 1 AS x`)
2. Either wait for the next scheduled trigger (10 sec) or click ▶
3. **Verify:** the next history entry is green (`✓ N строк`)
4. **Verify:** no further failure balloon appears for this job
5. The consecutive-failure counter has reset to 0 internally

---

## 9. Settings persistence

Verifies that all configuration and all jobs survive a full application
restart. (See also `docs/VERIFICATION.md` §10 for more detail.)

1. Configure the SQL connection: instance, database, credentials
2. Create 2–3 export jobs with different names and SQL queries
3. Run each job at least once (manual trigger ▶) so they have history
4. Close the application completely:
   - Right-click tray icon → **Выход**
   - Verify the process is gone (Task Manager)
5. Restart: `python main.py`
6. **Verify:** the SQL connection fields are pre-populated exactly as
   configured
7. **Verify:** all jobs are present with their names, SQL, schedule,
   and auto-run toggles intact
8. **Verify:** history entries from before the restart are still visible

---

## 10. Debug console (Ctrl+D)

Verifies the in-memory log ring buffer and the coloured log viewer.

1. With the app running, press **Ctrl+D** from anywhere in the window
2. **Verify:** the debug console window opens
3. **Verify:** log levels are colour-coded:
   - DEBUG = muted zinc/gray
   - INFO = cyan
   - WARNING = amber/yellow
   - ERROR = red
   - CRITICAL = bold red
4. **Verify:** lines follow the format `HH:MM:SS [LEVEL] logger.name: message`
5. Trigger any action (e.g., click ▶ to run an export)
6. **Verify:** progress log lines appear live in the console

The console mirrors the in-memory ring buffer (last 500 entries). For
entries older than that, check the persistent error log:

```
%APPDATA%\iDentSync\errors.log
```

This file is written by the global exception handler and captures
unhandled exceptions that bypass the normal logging path.

---

## 11. Resource usage check (long-running)

Verifies the app does not leak memory or threads over extended operation.
This test requires leaving the app running for at least several hours.

### Setup

1. Run `python main.py` (do NOT set FAST\_TRIGGER — use normal schedules)
2. Create 3–5 jobs with realistic hourly or daily schedules
3. Open Task Manager → find `python.exe` (iDentBridge process)
4. Note the current **Memory (Working Set)** value as your baseline
5. Close the window to tray (the app keeps running)

### Verify after 4–24 hours

1. Open Task Manager again
2. **Verify:** memory has not grown more than ~20 MB above baseline
3. **Verify:** CPU usage is near 0 % when no exports are actively running
4. **Verify:** history entries from the past few hours are present for
   all active jobs
5. Open the debug console (Ctrl+D) and scroll through recent entries
6. **Verify:** no repeated WARNING or ERROR lines about workers being
   created but not cleaned up

If memory grew significantly, open an issue and attach the relevant
lines from `%APPDATA%\iDentSync\errors.log`.

---

## 12. Update check

Verifies the GitHub update checker does not crash on first run.

1. Navigate to **Настройки**
2. Click **Проверить обновление**
3. Open the debug console (Ctrl+D)
4. **Verify:** no ERROR lines related to the update check
5. If you are behind the latest release:
   - **Verify:** an update banner or dialog appears on the **Статус** tab
6. If you are on the latest release:
   - **Verify:** no disruptive dialog — the check completes silently

---

## Reliability checklist (release blocker)

Before shipping any release, **all** of the following must pass. Check
each item off manually:

```
Core startup
  [ ] python -m pytest tests/ → 152/152 PASS (zero failures, zero errors)
  [ ] Headless smoke construct → "MainWindow constructs OK"

Tray
  [ ] Tray icon appears on launch (NOT empty, NOT invisible)
  [ ] Tray icon is the lime database cylinder, not a default Python icon
  [ ] Right-click menu shows: Открыть, Проверить обновление, Выход
  [ ] Close-to-tray works on first try
  [ ] Single-click OR double-click tray icon restores the main window
  [ ] "Выход" from tray menu cleanly quits (process gone, icon removed)

Scheduler triggers
  [ ] FAST_TRIGGER=10 → history entries appear every ~10 seconds
  [ ] History entry has clock icon + lime accent (scheduled trigger)
  [ ] Background execution works: history accumulates while window hidden
  [ ] Manual trigger (▶ on tile) → immediate history entry, blue accent
  [ ] Test dialog trigger → immediate history entry, gray accent + flask icon

Autostart
  [ ] Toggle ON → reg query shows REG_SZ value with correct path
  [ ] Reboot test → app starts in tray after Windows login without user action
  [ ] Toggle OFF → reg query returns "system was unable to find..."

Error handling
  [ ] 3 consecutive failures → tray balloon notification appears
  [ ] Balloon text names the failing job
  [ ] Fix the job → next run succeeds → no more balloons
  [ ] Invalid SQL is reported in history entry error message

Persistence
  [ ] All settings survive a full restart (Выход + relaunch)
  [ ] All jobs survive a full restart
  [ ] Job history survives a full restart

Debug + logging
  [ ] Ctrl+D opens debug console
  [ ] Log levels are colour-coded (INFO cyan, WARNING amber, ERROR red)
  [ ] Live export activity appears in the console

Resource usage
  [ ] Memory growth < 20 MB over 4+ hours of background operation
  [ ] CPU usage < 1 % when idle (no exports running)
```

If ANY item fails, fix it before shipping. iDentBridge is designed to
run unattended overnight and across weekends. Silent failures are
unacceptable.

---

## Troubleshooting

### Tray icon doesn't appear

- Check Task Manager — is `python.exe` running? If not, the app
  crashed at startup. Run `python main.py` from a terminal to see
  the exception.
- Some Windows setups hide overflow tray icons by default. Click the
  **^** (chevron) in the notification area to expand hidden icons.
- Right-click the taskbar → **Taskbar settings** → **Other system
  tray icons** → ensure iDentBridge is set to **On**.
- If using a packaged `.exe`, check that it is not blocked by antivirus.

### Scheduled exports don't fire

- Open the job editor and confirm **Запускать автоматически** is ON.
- Confirm **Расписание** mode and value are both set to valid values.
- Open the debug console (Ctrl+D). Look for lines containing
  `SCHEDULED` or `SyncScheduler`. Missing lines mean the scheduler
  never started.
- If using FAST\_TRIGGER, confirm the env var is set **in the same
  terminal session** where you launched `python main.py`. Env vars
  set after the process starts have no effect.
- Check for any ERROR lines in the debug console that could indicate
  a crash in the export worker.

### Autostart doesn't work after reboot

- Verify the registry entry exists before rebooting:
  ```cmd
  reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v iDentBridge
  ```
- If the path in the registry is wrong (stale from a previous
  install location), toggle autostart OFF then ON again in
  **Настройки** to refresh it.
- Check whether your antivirus or group policy is blocking the
  Run key. Some corporate environments disable per-user autostart
  entries.
- For a packaged `.exe`, confirm Windows Defender has not quarantined
  the file.

### Memory usage growing continuously

- Open the debug console and look for repeated WARNING lines about
  threads or workers.
- Restart the app — if memory drops back to baseline, the leak is
  in the long-running session only.
- Attach `%APPDATA%\iDentSync\errors.log` when filing an issue.

### "MainWindow constructs OK" not printed in headless smoke

- Read the Python traceback carefully — the last frame before the
  crash is the broken component.
- Common causes: missing asset file, import cycle, or a Qt widget
  that fails to initialise without a display (if `QT_QPA_PLATFORM`
  was not set to `offscreen`).

### Tests fail with "DPAPI unavailable" or similar

- DPAPI (credential encryption) tests are Windows-only. They are
  automatically skipped on Linux and macOS.
- On Windows, confirm you are running Python 3.10+ and that
  `pywin32` is installed (`pip install pywin32`).

### Current audit environment

- This workspace is Linux/WSL, so the Windows-only manual checks are
  intentionally not expected to pass here.
- The repository tree currently reports 199 test functions, but the
  release gate should still be confirmed in a clean Windows session
  before any shipping decision.

---

*See also: `docs/VERIFICATION.md` — shorter manual checklist focused
on the most common release-day scenarios.*
