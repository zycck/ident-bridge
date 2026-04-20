"""Tests for extracted export jobs collection/controller layer."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from app.config import ExportJob
from app.ui.export_jobs_collection_controller import ExportJobsCollectionController


class _DummyConfig:
    def __init__(self, jobs: list[ExportJob]) -> None:
        self._cfg = {"export_jobs": list(jobs)}
        self.saved = None

    def load(self):
        return dict(self._cfg)

    def save(self, cfg):
        self.saved = cfg
        self._cfg = dict(cfg)


class _FakeTile(QWidget):
    open_requested = Signal(str)
    run_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, job: ExportJob, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job = job
        self.updated: list[ExportJob] = []

    def job_id(self) -> str:
        return self._job["id"]

    def update_from_job(self, job: ExportJob) -> None:
        self._job = job
        self.updated.append(job)


class _FakeEditor(QWidget):
    changed = Signal(object)
    history_changed = Signal()
    sync_completed = Signal(object)
    failure_alert = Signal(str, int)

    def __init__(
        self,
        job: ExportJob,
        _config,
        _parent: QWidget | None = None,
    ) -> None:
        super().__init__(_parent)
        self._job = job
        self.start_calls = 0

    def to_job(self) -> ExportJob:
        return dict(self._job)

    def start_export(self) -> None:
        self.start_calls += 1

    def stop_scheduler(self) -> None:
        pass

    def stop_timers(self) -> None:
        pass


class _FakeTilesPage:
    def __init__(self) -> None:
        self._tiles: list[_FakeTile] = []
        self.refresh_calls = 0
        self.reflow_calls = 0

    def add_tile(self, tile: _FakeTile) -> None:
        self._tiles.append(tile)

    def tiles(self) -> list[_FakeTile]:
        return list(self._tiles)

    def refresh_empty(self) -> None:
        self.refresh_calls += 1

    def reflow_tiles(self) -> None:
        self.reflow_calls += 1


class _FakeEditorPage:
    def __init__(self) -> None:
        self.added_ids: list[str] = []
        self.scrolls: list[object] = []

    def add_editor(self, job_id: str, scroll) -> None:
        self.added_ids.append(job_id)
        self.scrolls.append(scroll)


def _job(job_id: str, name: str) -> ExportJob:
    return ExportJob(
        id=job_id,
        name=name,
        sql_query="SELECT 1",
        webhook_url="",
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],
    )


def _build_controller(*, jobs: list[ExportJob], warn_duplicate_target=None):
    opens: list[str] = []
    syncs: list[object] = []
    history_changed: list[bool] = []
    alerts: list[tuple[str, int]] = []
    config = _DummyConfig(jobs)
    tiles_page = _FakeTilesPage()
    editor_page = _FakeEditorPage()
    controller = ExportJobsCollectionController(
        config=config,
        parent=QWidget(),
        tiles_page=tiles_page,
        editor_page=editor_page,
        open_editor=lambda job_id: opens.append(job_id),
        delete_job=lambda job_id: opens.append(f"delete:{job_id}"),
        emit_sync_completed=lambda result: syncs.append(result),
        emit_history_changed=lambda: history_changed.append(True),
        emit_failure_alert=lambda name, count: alerts.append((name, count)),
        warn_duplicate_target=warn_duplicate_target,
        tile_factory=_FakeTile,
        editor_factory=_FakeEditor,
    )
    return controller, config, tiles_page, editor_page, opens, syncs, history_changed, alerts


def test_collection_controller_loads_jobs_into_tiles_and_editors(qtbot) -> None:
    controller, _config, tiles_page, editor_page, *_ = _build_controller(
        jobs=[_job("job-1", "One"), _job("job-2", "Two")],
    )
    qtbot.addWidget(controller._parent)

    controller.load_jobs()

    assert sorted(controller.editors()) == ["job-1", "job-2"]
    assert [tile.job_id() for tile in tiles_page.tiles()] == ["job-1", "job-2"]
    assert editor_page.added_ids == ["job-1", "job-2"]
    assert tiles_page.refresh_calls == 1
    assert tiles_page.reflow_calls == 1


def test_collection_controller_save_syncs_tiles_and_persists_config() -> None:
    controller, config, tiles_page, _editor_page, *_ = _build_controller(
        jobs=[_job("job-1", "One")],
    )

    controller.load_jobs()
    editor = controller.editors()["job-1"]
    editor._job = _job("job-1", "Renamed")

    controller.save_jobs()

    assert config.saved is not None
    assert config.saved["export_jobs"][0]["name"] == "Renamed"
    assert tiles_page.tiles()[0].updated[-1]["name"] == "Renamed"


def test_collection_controller_add_new_job_saves_and_opens_editor() -> None:
    controller, config, tiles_page, editor_page, opens, *_ = _build_controller(
        jobs=[],
    )

    controller.add_new_job()

    assert len(controller.editors()) == 1
    assert len(tiles_page.tiles()) == 1
    assert len(editor_page.added_ids) == 1
    assert len(opens) == 1
    assert config.saved is not None


def test_collection_controller_forwards_editor_actions(qtbot) -> None:
    controller, _config, _tiles_page, _editor_page, _opens, syncs, history_changed, alerts = _build_controller(
        jobs=[_job("job-1", "One")],
    )

    controller.load_jobs()
    editor = controller.editors()["job-1"]
    controller.run_job("job-1")
    editor.sync_completed.emit({"rows_synced": 5})
    editor.history_changed.emit()
    editor.failure_alert.emit("One", 3)

    assert editor.start_calls == 1
    assert syncs == [{"rows_synced": 5}]
    assert history_changed == [True]
    assert alerts == [("One", 3)]


def test_collection_controller_blocks_duplicate_webhook_and_sheet_targets(qtbot) -> None:
    warnings: list[tuple[str, str]] = []
    controller, config, _tiles_page, _editor_page, *_ = _build_controller(
        jobs=[
            {
                "id": "job-1",
                "name": "One",
                "sql_query": "SELECT 1",
                "webhook_url": "https://script.google.com/macros/s/abc/exec",
                "gas_options": {"sheet_name": "Exports", "auth_token": "one"},
                "schedule_enabled": False,
                "schedule_mode": "daily",
                "schedule_value": "",
                "history": [],
            },
            {
                "id": "job-2",
                "name": "Two",
                "sql_query": "SELECT 2",
                "webhook_url": "https://script.google.com/macros/s/abc/exec",
                "gas_options": {"sheet_name": "Exports", "auth_token": "two"},
                "schedule_enabled": False,
                "schedule_mode": "daily",
                "schedule_value": "",
                "history": [],
            },
        ],
        warn_duplicate_target=lambda title, message: warnings.append((title, message)),
    )

    controller.load_jobs()
    controller.save_jobs()

    assert config.saved is None
    assert warnings
    assert "адрес обработки" in warnings[0][1]
