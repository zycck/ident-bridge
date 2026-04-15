import pyodbc

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
    available = set(pyodbc.drivers())
    for candidate in _CANDIDATES:
        if candidate in available:
            return candidate
    installed = ", ".join(sorted(available)) or "нет"
    raise RuntimeError(
        "Не найден подходящий ODBC-драйвер для SQL Server.\n"
        f"Установленные драйверы: {installed}\n"
        "Установите ODBC Driver 17 (или новее) с сайта Microsoft."
    )
