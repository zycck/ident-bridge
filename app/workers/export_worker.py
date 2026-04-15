"""
ExportWorker — full sync pipeline in a worker thread (moveToThread pattern).

Pipeline steps (emitted via progress signal):
    0  Подключение к БД...
    1  Выполнение запроса...
    2  Отправка данных...
    3  Уведомление...
    4  Готово
"""
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, Slot

from app.config import ConfigManager, IExporter, INotifier, SyncResult
from app.core.sql_client import SqlClient


class ExportWorker(QObject):
    """QObject worker that runs the full SQL → exporter → notifier pipeline."""

    # (step 0-4, human-readable description)
    progress: Signal = Signal(int, str)
    # Emitted on both success and failure; carries SyncResult
    finished: Signal = Signal(object)
    # Emitted only on failure
    error: Signal = Signal(str)

    def __init__(
        self,
        config: ConfigManager,
        exporter: IExporter,
        notifier: INotifier | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._exporter = exporter
        self._notifier = notifier

    @Slot()
    def run(self) -> None:
        """Execute the full sync pipeline."""
        cfg = self._config.load()
        sql_client = SqlClient(cfg)
        try:
            self.progress.emit(0, "Подключение к БД...")
            sql_client.connect()

            self.progress.emit(1, "Выполнение запроса...")
            sql = cfg.get("sql_query", "")  # type: ignore[call-overload]
            if not sql:
                raise ValueError("sql_query не настроен в конфигурации")
            result = sql_client.query(sql)

            self.progress.emit(2, "Отправка данных...")
            self._exporter.push(result)

            self.progress.emit(3, "Уведомление...")
            if self._notifier is not None:
                self._notifier.notify(
                    f"Синхронизация завершена: {result.count} строк за {result.duration_ms}мс"
                )

            self.progress.emit(4, "Готово")
            self.finished.emit(
                SyncResult(
                    success=True,
                    rows_synced=result.count,
                    error=None,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.error.emit(msg)
            # Send only exception type to notifier — str(exc) may contain DSN credentials
            if self._notifier is not None:
                safe_msg = type(exc).__name__
                self._notifier.notify(f"Ошибка синхронизации: {safe_msg}")
            self.finished.emit(
                SyncResult(
                    success=False,
                    rows_synced=0,
                    error=msg,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        finally:
            sql_client.disconnect()
