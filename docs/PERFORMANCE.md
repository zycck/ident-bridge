# Performance Diagnostics

This repository includes a lightweight `tracemalloc` smoke harness for
repeated UI lifecycle checks. It is meant to catch obvious retained
allocations before we attempt deeper optimization work.

## Validated environment

- Windows 11
- Python 3.14.4
- Install the validated stack first:

```bash
pip install -r requirements.txt -r requirements-dev.txt -c constraints-py314-win.txt
```

## Run the harness

```bash
python tools/perf_smoke.py --scenario all --cycles 5 --top 8
```

Useful narrower runs:

```bash
python tools/perf_smoke.py --scenario main-window --cycles 3
python tools/perf_smoke.py --scenario sql-editor --cycles 10
python tools/perf_smoke.py --scenario debug-window --cycles 10
python tools/perf_smoke.py --scenario export-editor --cycles 5
python tools/perf_smoke.py --scenario settings-widget --cycles 5
python tools/perf_smoke.py --scenario test-run-dialog --cycles 10
```

## Optional threshold gate

If you want a failing exit code for a CI-style experiment, pass an
explicit threshold:

```bash
python tools/perf_smoke.py --scenario all --cycles 5 --fail-over-kib 2048
```

This is intentionally opt-in. One-time allocations from Qt caches,
font loading, icon loading, and style initialization can move the
baseline, so thresholds should only be enforced after measuring on the
real target machine.

## What it exercises

- `MainWindow` construction and teardown
- `ExportJobEditor` construction and teardown
- `SettingsWidget` construction and teardown
- `TestRunDialog` construction and teardown
- `DebugWindow` construction and teardown
- `SqlEditorDialog` construction and teardown
- `ErrorDialog` construction and teardown

The harness runs headless via `QT_QPA_PLATFORM=offscreen`, so it is
safe for automated diagnostics and does not require a visible desktop
session.

## Current Windows baseline

Latest expanded baseline on Windows 11 / Python 3.14.4:

```text
scenario=all
cycles=1
positive_retained_kib=1714.9
```

Largest retained buckets in that run were dominated by first-load costs
from Python/Qt imports plus UI page construction, especially
`enum.py`, `app/ui/export_jobs_pages.py`, and `app/ui/main_window_navigation.py`.
After moving `sqlglot` to lazy import, removing eager SQL validation
on initial export-editor load, and reusing cached highlighter assets,
the narrower `export-editor` scenario dropped from `1681.1 KiB` to
`993.4 KiB` on the same Windows 11 / Python 3.14.4 machine.
Treat these numbers as a living baseline, not a hard regression
threshold yet.
