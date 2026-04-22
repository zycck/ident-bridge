from app.ui.dashboard.ping_coordinator import _PingWorker


def test_ping_worker_uses_database_factory_and_emits_alive(monkeypatch) -> None:
    seen: list[tuple[str, dict]] = []
    results: list[bool | None] = []
    finished: list[bool] = []

    class _FakeClient:
        def connect(self) -> None:
            pass

        def is_alive(self) -> bool:
            return True

        def disconnect(self) -> None:
            pass

    def _factory(kind: str, cfg):
        seen.append((kind, cfg))
        return _FakeClient()

    monkeypatch.setattr(
        "app.ui.dashboard.ping_coordinator.create_database_client",
        _factory,
    )

    worker = _PingWorker("srv\\SQLEXPRESS", "main_db", "sa", "secret", True)
    worker.result.connect(results.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.run()

    assert seen and seen[0][0] == "mssql"
    assert seen[0][1]["sql_instance"] == "srv\\SQLEXPRESS"
    assert results == [True]
    assert finished == [True]
