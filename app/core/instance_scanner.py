import logging
import winreg
import subprocess

import pyodbc

from app.config import SqlInstance
from app.core.connection import build_sql_connection_string
from app.core.odbc_utils import best_driver

_INSTANCES_KEY = r"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL"
_log = logging.getLogger(__name__)


def scan_local() -> list[SqlInstance]:
    results: list[SqlInstance] = []
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
    conn: pyodbc.Connection | None = None
    try:
        conn = pyodbc.connect(conn_str, autocommit=True, timeout=3)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sys.databases WHERE state_desc = 'ONLINE' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        if conn is not None:
            try:
                conn.close()
            except pyodbc.Error:
                pass
