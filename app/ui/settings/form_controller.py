"""Settings form load/save/autosave orchestration extracted from SettingsWidget."""

from collections.abc import Callable

from PySide6.QtCore import QObject, QSignalBlocker
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit

from app.config import ConfigManager
from app.core.app_logger import get_logger
from app.ui.settings_persistence import (
    build_settings_payload,
    resolve_autosave_database,
)
from app.ui.settings_sql_flow import SettingsSqlFlowState
from app.ui.settings_workers import instance_from_text

_log = get_logger(__name__)


class SettingsFormController(QObject):
    """Owns non-visual form persistence for the settings screen."""

    def __init__(
        self,
        *,
        config: ConfigManager,
        flow: SettingsSqlFlowState,
        instance_combo: QComboBox,
        db_combo: QComboBox,
        login_edit: QLineEdit,
        password_edit: QLineEdit,
        startup_check: QCheckBox,
        auto_update_check: QCheckBox,
        github_repo: str,
        is_startup_enabled_fn: Callable[[], bool],
        on_instance_selected: Callable[[int], object],
    ) -> None:
        super().__init__(instance_combo)
        self._config = config
        self._flow = flow
        self._instance_combo = instance_combo
        self._db_combo = db_combo
        self._login_edit = login_edit
        self._password_edit = password_edit
        self._startup_check = startup_check
        self._auto_update_check = auto_update_check
        self._github_repo = github_repo
        self._is_startup_enabled = is_startup_enabled_fn
        self._on_instance_selected = on_instance_selected

    def load_fields(self) -> None:
        self._flow.begin_load()
        try:
            self._load_fields_impl()
        finally:
            self._flow.end_load()

    def _load_fields_impl(self) -> None:
        cfg = self._config.load()

        self._login_edit.setText(cfg.get("sql_user", "") or "")
        self._password_edit.setText(cfg.get("sql_password", "") or "")

        saved_db = cfg.get("sql_database", "") or ""
        self._flow.remember_loaded_database(saved_db)

        saved_instance = cfg.get("sql_instance", "")
        if saved_instance:
            target_idx = 0
            with QSignalBlocker(self._instance_combo):
                idx = self._instance_combo.findText(saved_instance)
                if idx < 0:
                    inst = instance_from_text(saved_instance)
                    if inst:
                        self._instance_combo.addItem(saved_instance, userData=inst)
                    else:
                        self._instance_combo.addItem(saved_instance)
                    idx = self._instance_combo.count() - 1
                target_idx = max(idx, 0)
            self._instance_combo.setCurrentIndex(target_idx)
            self._on_instance_selected(target_idx)

        with QSignalBlocker(self._startup_check):
            self._startup_check.setChecked(self._is_startup_enabled())
        self._auto_update_check.setChecked(bool(cfg.get("auto_update_check", True)))

    def save(self) -> None:
        cfg = self._config.load()
        cfg.update(self._current_payload())
        self._config.save(cfg)

    def handle_database_changed(self, idx: int, *, autosave: bool = True) -> None:
        text = self._db_combo.itemText(idx)
        self._flow.remember_database_selection(text)
        if autosave:
            self.auto_save()

    def auto_save(self) -> bool:
        if self._flow.should_skip_autosave():
            return False
        self._config.update(**self._current_payload())
        _log.debug("Auto-saved settings")
        return True

    def _current_payload(self) -> dict:
        db = resolve_autosave_database(
            self._flow.selected_database,
            self._db_combo.currentText().strip(),
        )
        return build_settings_payload(
            sql_instance=self._instance_combo.currentText().strip(),
            sql_database=db,
            sql_user=self._login_edit.text().strip(),
            sql_password=self._password_edit.text(),
            auto_update_check=self._auto_update_check.isChecked(),
            run_on_startup=self._startup_check.isChecked(),
            github_repo=self._github_repo,
        )
