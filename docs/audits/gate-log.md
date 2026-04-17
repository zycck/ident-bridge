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

