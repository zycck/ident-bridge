import pyodbc

_CANDIDATES = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
)


def best_driver() -> str:
    available = set(pyodbc.drivers())
    for candidate in _CANDIDATES:
        if candidate in available:
            return candidate
    installed = ", ".join(sorted(available)) or "нет"
    raise RuntimeError(
        "Не найден подходящий ODBC-драйвер для SQL Server.\n"
        f"Установленные драйверы: {installed}\n"
        "Установите 'ODBC Driver 17 for SQL Server' или новее."
    )
