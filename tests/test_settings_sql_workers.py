from app.ui.settings_workers import TestConnectionWorker as _TestConnectionWorker


def test_test_connection_worker_uses_database_factory(monkeypatch) -> None:
    seen: list[tuple[str, dict]] = []
    finished: list[tuple[bool, str]] = []

    class _FakeClient:
        def test_connection(self):
            return True, "ok"

    def _factory(kind: str, cfg):
        seen.append((kind, cfg))
        return _FakeClient()

    monkeypatch.setattr(
        "app.ui.settings.sql.workers.create_database_client",
        _factory,
    )

    worker = _TestConnectionWorker(
        {
            "sql_instance": "srv\\SQLEXPRESS",
            "sql_database": "main_db",
            "sql_user": "sa",
            "sql_password": "secret",
        }
    )
    worker.finished.connect(lambda ok, msg: finished.append((ok, msg)))

    worker.run()

    assert seen == [("mssql", worker._cfg)]
    assert finished == [(True, "ok")]
