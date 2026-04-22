from __future__ import annotations

from app.config import AppConfig, ExportJob, QueryResult
from app.core.constants import EXPORT_SOURCE_ID
from app.export.pipeline import build_pipeline_for_job
from app.export.sinks.google_apps_script import GoogleAppsScriptSink, plan_gas_chunks
from tests.test_google_apps_script_backend_files import (
    SOURCE_COLUMN,
    TECH_COLUMN,
    _run_backend_probe,
)


def _job(*, webhook: str) -> ExportJob:
    return ExportJob(
        id="123e4567-e89b-12d3-a456-426614174000",
        name="UUID job",
        sql_query="SELECT 1",
        webhook_url=webhook,
        schedule_enabled=False,
        schedule_mode="daily",
        schedule_value="",
        history=[],
    )


def _qr() -> QueryResult:
    return QueryResult(columns=["id"], rows=[(1,)], count=1, duration_ms=1)


def test_build_pipeline_for_job_uses_app_source_id_for_gas_sink() -> None:
    pipeline = build_pipeline_for_job(
        AppConfig(),
        _job(webhook="https://script.google.com/macros/s/abc/exec"),
        sql_client_cls=lambda cfg: object(),
    )

    assert isinstance(pipeline.sink, GoogleAppsScriptSink)
    assert pipeline.sink._source_id == EXPORT_SOURCE_ID  # type: ignore[attr-defined]


def test_plan_gas_chunks_falls_back_to_app_source_id() -> None:
    chunk = plan_gas_chunks(
        "Employees",
        _qr(),
        run_id="run-1",
        export_date="2026-04-21",
    )[0]

    assert chunk.checksum
    assert chunk.chunk_rows == 1


def test_backend_replace_by_date_source_keeps_numeric_foreign_sources_untouched() -> None:
    result = _run_backend_probe(
        """
        __registerSheet('Reports', {
          sheetId: 10,
          values: [
            ['id', 'name', '__TECH_COLUMN__', '__SOURCE_COLUMN__'],
            [90, 'Legacy zero', '2026-04-20', '0'],
            [91, 'Legacy one', '2026-04-20', '1'],
            [77, 'External row', '2026-04-20', 'external']
          ]
        });

        const payload = {
          protocol_version: 'gas-sheet.v2',
          job_name: 'nightly_export',
          run_id: 'run-numeric-foreign',
          chunk_index: 1,
          total_chunks: 1,
          total_rows: 2,
          chunk_rows: 2,
          sheet_name: 'Reports',
          export_date: '2026-04-20',
          source_id: '__SOURCE_ID__',
          write_mode: 'replace_by_date_source',
          columns: ['id', 'name'],
          records: [
            { id: 1, name: 'Ana' },
            { id: 2, name: 'Boris' }
          ]
        };
        payload.checksum = __checksum__(payload);

        const ack = JSON.parse(__callPost(payload));
        const mainSheet = __spreadsheet.getSheetByName('Reports');

        console.log(JSON.stringify({
          ack,
          mainValues: mainSheet.getDataRange().getValues()
        }));
        """
    )

    assert result["ack"]["status"] == "accepted"
    assert result["mainValues"] == [
        ["id", "name", TECH_COLUMN, SOURCE_COLUMN],
        [90, "Legacy zero", "2026-04-20", "0"],
        [91, "Legacy one", "2026-04-20", "1"],
        [77, "External row", "2026-04-20", "external"],
        [1, "Ana", "2026-04-20", EXPORT_SOURCE_ID],
        [2, "Boris", "2026-04-20", EXPORT_SOURCE_ID],
    ]
