# Versioning

Format: `MAJOR.MINOR.PATCH`  
Start: `0.0.1`

## Rules

| Bump | When |
|---|---|
| `PATCH` (0.0.x) | Bug fixes, refactoring without new features |
| `MINOR` (0.x.0) | New feature (new screen, new export destination) |
| `MAJOR` (x.0.0) | Breaking change (protocol change, DB schema change) |

## Constants

- `app/core/constants.py` is the single source of truth for app identity and package metadata:
  - `APP_NAME = "iDentBridge"`
  - `CONFIG_DIR_NAME = "iDentSync"`
  - `EXE_NAME = "iDentSync"`
  - `APP_VERSION = "0.2.0"`
  - `USER_AGENT = f"{APP_NAME}/{APP_VERSION}"`
- `main.py` imports `APP_VERSION` from `app/core/constants.py`
- `build.spec` imports `EXE_NAME` from `app/core/constants.py`
- GitHub tag format: `v0.0.1`, `v0.1.0`, `v1.0.0`
- GitHub Release attachment: the packaged artifact name comes from `EXE_NAME` in `app/core/constants.py` (`iDentSync.exe` today)
- Перед release/push после заметной волны изменений обязательно синхронно обновлять:
  - `APP_VERSION` в `app/core/constants.py`
  - `USER_AGENT`
  - верхнюю релизную запись в `CHANGELOG.md`

## Commit convention

```
type(scope): short description in English

Types: feat | fix | refactor | style | build | docs
```

Examples:
- `feat(core): add DPAPI encryption module`
- `feat(ui): implement system tray with context menu`
- `fix(sql): exponential backoff on connection loss`
- `build: add pyinstaller spec with module exclusions`
