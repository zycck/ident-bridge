from app.config import QueryResult


class SheetsWebhook:
    """Implements IExporter Protocol — stub for Google Sheets webhook."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url

    def push(self, data: QueryResult) -> None:
        raise NotImplementedError("Google Sheets webhook coming in next version")

    def is_configured(self) -> bool:
        return False
