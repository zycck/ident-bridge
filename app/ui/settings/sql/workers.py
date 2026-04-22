from PySide6.QtCore import QObject, Signal, Slot

from app.config import AppConfig, SqlInstance
from app.core.app_logger import get_logger
from app.core.instance_scanner import list_databases, scan_all
from app.core.sql_client import SqlClient

_log = get_logger(__name__)

_PLACEHOLDER_INSTANCE_TEXTS = frozenset({
    "Сканирование…",
    "Нет экземпляров",
    "Ошибка сканирования",
    "Загрузка…",
})


def instance_from_text(text: str) -> SqlInstance | None:
    text = text.strip()
    if not text or text in _PLACEHOLDER_INSTANCE_TEXTS:
        return None
    parts = text.split("\\", 1)
    host = parts[0].strip()
    name = parts[1].strip() if len(parts) > 1 else ""
    return SqlInstance(name=name, host=host, display=text)


class InstanceScanWorker(QObject):
    finished: Signal = Signal(list)
    error: Signal = Signal(str)

    @Slot()
    def run(self) -> None:
        _log.debug("Scanning SQL instances…")
        try:
            instances = scan_all()
            _log.info("Instance scan done: %d found", len(instances))
            self.finished.emit(instances)
        except Exception as exc:
            _log.error("Instance scan failed: %s", exc)
            self.error.emit(str(exc))


class DatabaseListWorker(QObject):
    finished: Signal = Signal(list)
    error: Signal = Signal(str)

    def __init__(self, inst: SqlInstance, user: str, password: str) -> None:
        super().__init__()
        self._inst = inst
        self._user = user
        self._password = password

    @Slot()
    def run(self) -> None:
        _log.debug("Fetching databases for %s", self._inst.display)
        try:
            databases = list_databases(self._inst, self._user, self._password)
            _log.info("Database list for %s: %d entries", self._inst.display, len(databases))
            self.finished.emit(databases)
        except Exception as exc:
            _log.error("Database list failed (%s): %s", self._inst.display, exc)
            self.error.emit(str(exc))


class TestConnectionWorker(QObject):
    finished: Signal = Signal(bool, str)

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self._cfg = cfg

    @Slot()
    def run(self) -> None:
        _log.debug("Testing SQL connection to %s", self._cfg.get("sql_instance"))
        client = SqlClient(self._cfg)
        ok, msg = client.test_connection()
        if ok:
            _log.info("SQL connection test passed")
        else:
            _log.warning("SQL connection test failed: %s", msg)
        self.finished.emit(ok, msg or "")
