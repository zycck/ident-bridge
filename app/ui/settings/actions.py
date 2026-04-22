from dataclasses import dataclass

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

from app.core import startup as StartupManager
from app.core.app_logger import get_logger
from app.core.updater import GITHUB_REPO
from app.ui.threading import run_worker
from app.workers.update_worker import UpdateWorker

_log = get_logger(__name__)


@dataclass(slots=True)
class StartupToggleResult:
    ok: bool
    error: str
    actual_enabled: bool


def apply_startup_toggle(checked: bool) -> StartupToggleResult:
    _log.info("=" * 60)
    _log.info(
        "User toggled 'Запускать с Windows' → %s",
        "ВКЛ" if checked else "ВЫКЛ",
    )
    if checked:
        ok, err = StartupManager.register()
        if ok:
            _log.info(
                "Автозапуск ВКЛЮЧЁН — приложение запустится при следующем входе в Windows"
            )
        else:
            _log.error("Не удалось включить автозапуск: %s", err)
    else:
        ok, err = StartupManager.unregister()
        if ok:
            _log.info("Автозапуск ВЫКЛЮЧЕН")
        else:
            _log.error("Не удалось выключить автозапуск: %s", err)

    actual = StartupManager.is_registered()
    _log.info(
        "Автозапуск — текущее состояние реестра: %s",
        "ЗАРЕГИСТРИРОВАН" if actual else "НЕ ЗАРЕГИСТРИРОВАН",
    )
    _log.info("=" * 60)
    return StartupToggleResult(ok=ok, error=err, actual_enabled=actual)


def is_startup_enabled() -> bool:
    return StartupManager.is_registered()


class SettingsUpdateCoordinator(QObject):
    def __init__(self, widget: QWidget, *, current_version: str) -> None:
        super().__init__(widget)
        self._widget = widget
        self._current_version = current_version
        self._running = False
        self._update_worker: object | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def check(self) -> bool:
        if self._running:
            return False

        self._running = True
        worker = UpdateWorker(
            current_version=self._current_version,
            repo=GITHUB_REPO,
        )
        run_worker(
            self,
            worker,
            pin_attr="_update_worker",
            entry="check",
            on_error=self._on_update_error,
            connect_signals=lambda update_worker, _thread: (
                update_worker.update_available.connect(self._on_update_available),
                update_worker.no_update.connect(self._on_no_update),
            ),
        )
        return True

    @Slot(str, str)
    def _on_update_available(self, tag: str, download_url: str) -> None:
        self._running = False
        QMessageBox.information(
            self._widget,
            "Доступно обновление",
            f"Новая версия {tag} доступна.\n\nСсылка: {download_url}",
        )

    @Slot()
    def _on_no_update(self) -> None:
        self._running = False
        QMessageBox.information(
            self._widget,
            "Обновлений нет",
            f"Установлена актуальная версия ({self._current_version}).",
        )

    @Slot(str)
    def _on_update_error(self, message: str) -> None:
        self._running = False
        QMessageBox.warning(self._widget, "Ошибка проверки обновлений", message)
