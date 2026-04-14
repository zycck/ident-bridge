import winreg
import subprocess

import pyodbc

from app.config import SqlInstance

_INSTANCES_KEY = r"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL"


def scan_local() -> list[SqlInstance]:
    results: list[SqlInstance] = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _INSTANCES_KEY)
    except OSError:
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

    return results


def scan_network() -> list[SqlInstance]:
    try:
        proc = subprocess.run(
            ['sqlcmd', '-L', '-t', '3'],
            capture_output=True,
            text=True,
            timeout=5,
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
        return results
    except Exception:
        return []


def scan_all() -> list[SqlInstance]:
    combined = scan_local() + scan_network()

    seen: dict[str, SqlInstance] = {}
    for instance in combined:
        key = instance.display.lower()
        if key not in seen:
            seen[key] = instance

    return sorted(seen.values(), key=lambda i: i.display.lower())


def list_databases(instance: SqlInstance, user: str, password: str) -> list[str]:
    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        f"Server={instance.display};"
        "Database=master;"
        f"UID={user};"
        f"PWD={password};"
        "APP=iDentBridge"
    )
    conn: pyodbc.Connection | None = None
    try:
        conn = pyodbc.connect(conn_str, autocommit=True, timeout=10)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sys.databases WHERE state_desc = 'ONLINE' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except pyodbc.Error:
                pass
