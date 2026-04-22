# Manual verification checklist

This document covers the manual end-to-end verification steps for
iDentBridge that the automated test suite cannot fully exercise.
Run through it before any release.

Audit note: this checklist assumes a real Windows 10/11 desktop
session. The current WSL/Linux workspace is only a negative-control
environment and cannot substitute for tray, registry, reboot, or other
Windows-specific validation.

## Prerequisites
- Windows 10 or 11
- Python 3.14.4 with PySide6 installed
- Install the validated dependency set before running the checklist:
  `pip install -r requirements.txt -r requirements-dev.txt -c constraints-py314-win.txt`
- Optional: a reachable MS SQL Server instance for end-to-end export tests
- Run the automated suite from the same Windows environment before
  relying on this checklist as a release gate.

## 1. Cold start + tray icon
1. Run `python main.py`
2. **Verify:** main window opens with the lime brand
3. **Verify:** tray icon appears in the Windows notification area
4. **Verify:** the tray icon is the app icon (database cylinder), not the default Python feather

## 2. Close-to-tray
1. With the app running, click the X button in the title bar
2. **Verify:** main window disappears
3. **Verify:** tray icon stays in the notification area
4. Double-click the tray icon
5. **Verify:** main window reappears
6. Right-click the tray icon → "Выход"
7. **Verify:** the app fully exits (process gone, tray icon removed)

## 3. Background scheduler with FAST_TRIGGER
This verifies that scheduled exports run in the background while the
window is closed-to-tray.

1. Set the dev env var:
   ```cmd
   set IDENTBRIDGE_FAST_TRIGGER_SECONDS=10
   ```
2. Run `python main.py`
3. Go to **Выгрузки**, click **Добавить**
4. Fill in:
   - Name: `Test Background`
   - SQL: `SELECT 1 as x`
   - Webhook URL: leave blank
5. Toggle **Запускать автоматически** → on
6. Go back to the tile list (← Назад)
7. Wait ~10 seconds
8. **Verify:** open the tile and check **История** — first entry appears with **scheduled** trigger (clock icon, lime accent)
9. Close the window (X) — it goes to tray
10. Wait ~20 more seconds
11. Restore from tray (double-click tray icon)
12. **Verify:** 2-3 more history entries have appeared while the window was hidden
13. **Verify:** **Статус** tab shows the same entries in the global activity feed
14. Stop the app

## 4. Windows autostart
1. Run `python main.py`
2. Go to **Настройки** → toggle **Запускать с Windows** → on
3. Verify the registry key:
   ```cmd
   reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v iDentBridge
   ```
4. **Verify:** the value points to the app identity defined in `app/core/constants.py` (`APP_NAME` for the Run key, `EXE_NAME.exe` for the packaged build)
5. Reboot Windows
6. **Verify:** after login, the app starts automatically (tray icon appears)
7. Open the app → **Настройки** → toggle off
8. Re-verify the registry key is gone

This step must be validated on Windows; registry write/read and reboot
behaviour are not meaningful from WSL/Linux.

## 5. Update check
1. **Настройки** → click **Проверить обновление**
2. **Verify:** no errors in the debug log (Ctrl+D)
3. **Verify:** if a new version is available, the update banner appears on Status

## 6. Test query (manual + dialog)
1. **Выгрузки** → tile → click into the editor
2. Click **Тест** below the SQL editor
3. **Verify:** test dialog opens, query auto-runs, results table populated
4. **Verify:** if the result is very large, the dialog shows only the
   first rows and the status line explicitly says that the result was
   truncated for display
5. Close the dialog
6. **Verify:** history gains a new entry with the **test** trigger (flask icon, gray accent)

## 7. SQL editor full-screen
1. In the editor, click the **↗ expand** icon in the top-right of the SQL field
2. **Verify:** SqlEditorDialog opens at 1100×720, light theme, syntax highlighting visible
3. Edit the SQL
4. Click **Сохранить**
5. **Verify:** the inline editor reflects the changes

## 8. History clear
1. Click **Очистить** in the editor's history section
2. **Verify:** confirm dialog appears, all entries gone after Yes
3. Go to **Статус** → **Очистить всё** in the activity card
4. **Verify:** all jobs' history is cleared globally

## 9. Debug console (Ctrl+D)
1. Press Ctrl+D
2. **Verify:** debug window opens with colored log levels:
   - DEBUG = muted gray
   - INFO = cyan
   - WARNING = amber
   - ERROR = red
   - CRITICAL = bold red
3. Trigger any action that logs — verify it appears live

## 10. Settings persistence
1. Change the SQL instance to something
2. Close + reopen the app
3. **Verify:** the instance is remembered

## 11. Packaged build smoke
1. Build the packaged app:
   ```cmd
   python -m PyInstaller build.spec --noconfirm --distpath build\dist --workpath build\work --clean
   ```
2. Start the packaged executable:
   ```cmd
   build\dist\iDentSync.exe
   ```
3. **Verify:** the app starts without an import/runtime crash
4. **Verify:** the window or tray process appears as expected
5. Close the packaged app
6. **Verify:** the process exits cleanly

## 12. Google Apps Script chunked webhook
This verifies the current Google Apps Script path with direct writes,
schema evolution, rerun recovery, and sanitized failure handling.

1. Publish the library from `google script back end/`
2. Install the shim into the target spreadsheet project as described in
   `google script back end/README.md`
3. Verify that the Apps Script project has the Advanced Sheets service
   enabled (`Sheets`, version `v4`)
4. In the app create a new export job and paste the deployed GAS web
   app URL into **Webhook URL**
5. Use a query that returns more than `10000` rows
6. Run the export manually
7. **Verify:** progress text advances through
   `Отправка данных... 1/N`, `2/N`, ..., `N/N`
8. **Verify:** the target sheet receives all rows without duplicates
9. **Verify:** the run finishes successfully and history stores only a
   short user-facing message
10. Add one new extra column to the SQL query and run again
11. **Verify:** the sheet header extends only to the right and old
    columns stay on their original positions
12. Remove or effectively rename one previously existing column and run again
13. **Verify:** the run fails cleanly, the app stays alive, and the
    debug console shows a sanitized technical dump without raw payload
    rows, URL tokens, or credentials
14. Start a `replace_all` or `replace_by_date_source` export large enough
    for multiple chunks, interrupt it in the middle, then run it again
15. **Verify:** the rerun starts from chunk `1`, rewrites the target
    slice on the first chunk, and leaves one consistent final dataset
    without torn rows

---

## Cleanup after verification

```cmd
set IDENTBRIDGE_FAST_TRIGGER_SECONDS=
```

Unset the env var so production behavior is restored.

For automated source-tree smoke only, you may also set
`IDENTBRIDGE_FORCE_QUIT_ON_CLOSE=1` so `python main.py` exits cleanly
under automation without changing the normal tray UX.

Manual-only remainder: tray visibility, close-to-tray, autostart
registry writes, reboot persistence, and real background scheduler
behaviour all require the Windows desktop shell and are not fully
covered by the automated suite.
