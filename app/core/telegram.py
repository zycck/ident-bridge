import ssl
import threading
import urllib.parse
import urllib.request

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_LEN = 4000


class TelegramNotifier:
    """Implements INotifier Protocol — sends messages via Telegram Bot API."""

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id

    def notify(self, message: str) -> None:
        text = message[:_MAX_LEN]
        t = threading.Thread(target=self._send, args=(text,), daemon=True)
        t.start()

    def test(self) -> tuple[bool, str]:
        try:
            self._send("iDentBridge: connection test OK")
            return (True, "")
        except Exception as exc:
            return (False, str(exc))

    def _send(self, text: str) -> None:
        url = _API_URL.format(token=self._token)
        payload = urllib.parse.urlencode(
            {"chat_id": self._chat_id, "text": text}
        ).encode()
        headers = {
            "User-Agent": "iDentBridge/0.0.1",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        request = urllib.request.Request(url, data=payload, headers=headers)
        ssl_ctx = ssl.create_default_context()
        urllib.request.urlopen(request, context=ssl_ctx, timeout=10)
