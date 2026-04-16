try:
    import pyodbc
except Exception as exc:  # pragma: no cover - import availability depends on runtime
    pyodbc = None
    _PYODBC_IMPORT_ERROR = exc
else:
    _PYODBC_IMPORT_ERROR = None

# Порядок важен — сначала самый новый.
# Driver 18+ требует TrustServerCertificate=yes для серверов без доверенного сертификата
# (уже прописано во всех строках подключения).
_CANDIDATES = (
    "ODBC Driver 21 for SQL Server",   # 2024+
    "ODBC Driver 18 for SQL Server",   # 2022+
    "ODBC Driver 17 for SQL Server",   # 2018+
    "ODBC Driver 13.1 for SQL Server", # 2016
    "ODBC Driver 13 for SQL Server",   # 2016
    "ODBC Driver 11 for SQL Server",   # 2012
    "SQL Server Native Client 11.0",   # SQL Server 2012
    "SQL Server Native Client 10.0",   # SQL Server 2008
    "SQL Server",                       # встроенный Windows-драйвер (крайний случай)
)


def best_driver() -> str:
    """Возвращает наилучший доступный ODBC-драйвер для SQL Server."""
    if pyodbc is None:
        raise RuntimeError(
            "pyodbc is not available; install pyodbc and the native ODBC runtime "
            "to detect SQL Server drivers"
        ) from _PYODBC_IMPORT_ERROR

    try:
        available = set(pyodbc.drivers())
    except Exception as exc:
        raise RuntimeError("Unable to enumerate installed ODBC drivers via pyodbc") from exc
    for candidate in _CANDIDATES:
        if candidate in available:
            return candidate
    installed = ", ".join(sorted(available)) or "нет"
    raise RuntimeError(
        "Не найден подходящий ODBC-драйвер для SQL Server.\n"
        f"Установленные драйверы: {installed}\n"
        "Установите ODBC Driver 17 (или новее) с сайта Microsoft."
    )
