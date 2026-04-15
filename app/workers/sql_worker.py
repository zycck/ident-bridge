"""
SqlWorker — runs a SQL query in a worker thread (moveToThread pattern).

Usage:
    thread = QThread()
    worker = SqlWorker(config_manager)
    worker.moveToThread(thread)
    thread.start()
    worker.run_query.emit("SELECT ...")   # or connect a signal to run_query slot
"""
from PySide6.QtCore import QObject, Signal, Slot

from app.config import ConfigManager, QueryResult
from app.core.sql_client import SqlClient


class SqlWorker(QObject):
    """QObject worker that executes a SQL query off the main thread."""

    # Emitted on successful query execution
    result: Signal = Signal(object)   # carries QueryResult
    # Emitted when an exception is raised
    error: Signal = Signal(str)
    # General status messages (e.g. "Подключение...", "Запрос выполнен")
    status: Signal = Signal(str)
    # Emitted after result or error — use to stop/clean up the thread
    finished: Signal = Signal()

    def __init__(self, config: ConfigManager) -> None:
        super().__init__()
        self._config = config

    @Slot(str)
    def run_query(self, sql: str) -> None:
        """Connect to SQL Server, run *sql*, disconnect, then emit result or error."""
        cfg = self._config.load()
        client = SqlClient(cfg)
        try:
            self.status.emit("Подключение к БД...")
            client.connect()

            self.status.emit("Выполнение запроса...")
            query_result: QueryResult = client.query(sql)

            self.status.emit(f"Готово — {query_result.count} строк за {query_result.duration_ms} мс")
            self.result.emit(query_result)

        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

        finally:
            client.disconnect()
            self.finished.emit()
