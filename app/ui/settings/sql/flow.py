"""State helpers for SettingsWidget SQL discovery/test flows."""

from app.config import SqlInstance

_PENDING_DATABASE_TEXTS = frozenset({"Загрузка…", "Нет баз данных"})


class SettingsSqlFlowState:
    """Owns non-visual state for the SQL settings workflow."""

    def __init__(self) -> None:
        self.scan_running = False
        self.database_list_running = False
        self.connection_test_running = False
        self.pending_database_instance: SqlInstance | None = None
        self.selected_database = ""
        self.loading = False

    def begin_load(self) -> None:
        self.loading = True

    def end_load(self) -> None:
        self.loading = False

    def should_skip_autosave(self) -> bool:
        return self.loading

    def remember_loaded_database(self, database: str) -> None:
        if database:
            self.selected_database = database

    def remember_database_selection(self, text: str) -> None:
        if text and text not in _PENDING_DATABASE_TEXTS:
            self.selected_database = text

    def begin_scan(self) -> bool:
        if self.scan_running:
            return False
        self.scan_running = True
        return True

    def finish_scan(self) -> None:
        self.scan_running = False
        self.database_list_running = False

    def fail_scan(self) -> None:
        self.scan_running = False

    def begin_database_fetch(self, inst: SqlInstance) -> bool:
        if self.database_list_running:
            self.pending_database_instance = inst
            return False
        self.pending_database_instance = None
        self.database_list_running = True
        return True

    def finish_database_fetch(self, *, saved_database: str) -> tuple[str, SqlInstance | None]:
        self.database_list_running = False
        pending = self.pending_database_instance
        self.pending_database_instance = None
        restore = self.selected_database or saved_database or ""
        return restore, pending

    def fail_database_fetch(self) -> SqlInstance | None:
        self.database_list_running = False
        pending = self.pending_database_instance
        self.pending_database_instance = None
        return pending

    def begin_connection_test(self) -> bool:
        if self.connection_test_running:
            return False
        self.connection_test_running = True
        return True

    def finish_connection_test(self) -> None:
        self.connection_test_running = False
