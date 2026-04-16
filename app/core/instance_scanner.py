import logging
import subprocess

try:
    import winreg
except Exception as exc:  # pragma: no cover - depends on OS
    winreg = None
    _WINREG_IMPORT_ERROR = exc
else:
    _WINREG_IMPORT_ERROR = None

try:
    import pyodbc
except Exception as exc:  # pragma: no cover - runtime availability differs by OS
    pyodbc = None
    _PYODBC_IMPORT_ERROR = exc
else:
    _PYODBC_IMPORT_ERROR = None

from app.config import SqlInstance
from app.core.connection import build_sql_connection_string
from app.core.odbc_utils import best_driver

_INSTANCES_KEY = r"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL"
_log = logging.getLogger(__name__)


def _require_pyodbc() -> None:
    if pyodbc is None:
        raise RuntimeError(
            "pyodbc is unavailable; install pyodbc and the native ODBC runtime"
        ) from _PYODBC_IMPORT_ERROR


def scan_local() -> list[SqlInstance]:
    results: list[SqlInstance] = []
    if winreg is None:
        _log.debug("scan_local: winreg unavailable, skipping registry scan")
        return results
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _INSTANCES_KEY)
    except OSError:
        _log.debug("No local SQL instances found in registry")
        return results

    with key:
        idx = 0
        while True:
            try:
                value_name, _data, _type = winreg.EnumValue(key, idx)
                results.append(SqlInstance(
                    name=value_name,
                    host='localhost',
                    display=f'localhost\\{value_name}',
                ))
                idx += 1
            except OSError:
                break

    _log.debug("scan_local: %d instances", len(results))
    return results


def scan_network() -> list[SqlInstance]:
    try:
        _log.debug("scan_network: running sqlcmd -L")
        proc = subprocess.run(
            ['sqlcmd', '-L', '-t', '1'],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode != 0 and not (proc.stdout or "").strip():
            stderr = (proc.stderr or "").strip()
            if stderr:
                _log.debug("scan_network: sqlcmd exited with %d: %s", proc.returncode, stderr)
            else:
                _log.debug("scan_network: sqlcmd exited with %d", proc.returncode)
            return []
        results: list[SqlInstance] = []
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            # sqlcmd -L emits a "Servers:" header and blank lines — skip both
            if not stripped or stripped.lower() == 'servers:':
                continue
            parts = stripped.split('\\', 1)
            host = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else ''
            results.append(SqlInstance(
                name=name,
                host=host,
                display=stripped,
            ))
        _log.debug("scan_network: %d instances", len(results))
        return results
    except FileNotFoundError:
        _log.debug("scan_network: sqlcmd not found, skipping network scan")
        return []
    except Exception as exc:
        _log.warning("scan_network failed: %s", exc)
        return []


def scan_all() -> list[SqlInstance]:
    """Scan local registry (fast) then network (2 s timeout), deduplicate, sort."""
    combined = scan_local() + scan_network()

    seen: dict[str, SqlInstance] = {}
    for instance in combined:
        key = instance.display.lower()
        if key not in seen:
            seen[key] = instance

    sorted_instances = sorted(seen.values(), key=lambda i: i.display.lower())
    _log.info("scan_all: %d unique instances", len(sorted_instances))
    return sorted_instances


def list_databases(instance: SqlInstance, user: str, password: str) -> list[str]:
    _require_pyodbc()
    driver = best_driver()
    conn_str = build_sql_connection_string(
        driver=driver,
        server=instance.display,
        database="master",
        user=user,
        password=password,
        trust_cert=True,
        timeout=3,
    )
    conn: object | None = None
    try:
        conn = pyodbc.connect(conn_str, autocommit=True, timeout=3)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sys.databases WHERE state_desc = 'ONLINE' ORDER BY name"
        )
        return [row[0] for row in cursor]
    finally:
        if conn is not None:
            try:
                conn.close()
            except pyodbc.Error:
                pass
