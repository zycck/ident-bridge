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

- `APP_VERSION = "0.0.1"` in `main.py`
- GitHub tag format: `v0.0.1`, `v0.1.0`, `v1.0.0`
- GitHub Release attachment: `iDentSync.exe`

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
