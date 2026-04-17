"""Tests for ExportJobsWidget page scaffold and routing."""

from app.config import ExportJob
from app.ui.export_jobs_widget import ExportJobsWidget


class _DummyConfig:
    def __init__(self, jobs: list[ExportJob]) -> None:
        self._cfg = {"export_jobs": list(jobs)}
        self.saved = None

    def load(self):
        return dict(self._cfg)

    def save(self, cfg):
        self.saved = cfg
        self._cfg = dict(cfg)


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


def test_export_jobs_widget_routes_between_tiles_and_editor(qtbot) -> None:
    widget = ExportJobsWidget(_DummyConfig([_job("job-1", "One"), _job("job-2", "Two")]))
    qtbot.addWidget(widget)
    widget.show()

    assert len(widget._tiles_page.tiles()) == 2
    assert widget._editor_page.editor_count() == 2

    widget._show_editor("job-1")

    assert widget._stack.currentIndex() == 1
    assert widget._navigation.current_editor_id == "job-1"

    widget._show_tiles()

    assert widget._stack.currentIndex() == 0
    assert widget._navigation.current_editor_id is None


def test_export_jobs_widget_reflow_keeps_tile_set_intact(qtbot) -> None:
    widget = ExportJobsWidget(_DummyConfig([_job("job-1", "One"), _job("job-2", "Two")]))
    qtbot.addWidget(widget)
    widget.show()
    widget.resize(1440, 900)

    widget._tiles_page.reflow_tiles()

    tile_ids = [tile.job_id() for tile in widget._tiles_page.tiles()]

    assert tile_ids == ["job-1", "job-2"]
