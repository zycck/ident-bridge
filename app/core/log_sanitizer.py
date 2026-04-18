"""Log-record sanitizer that masks URLs and credential fragments.

Motivation
----------
Webhook URLs in this project can carry secret tokens in their path
segments (Slack, Discord, n8n-style) or in the query-string. Logging
the full URL leaks those tokens into the in-memory ring buffer that
backs the debug panel, into stderr, and into any snapshot a user
copies out. Same story for ODBC connection strings containing
``UID=`` / ``PWD=`` fragments if they ever land in a log message.

SecretFilter
------------
A :class:`logging.Filter` that mutates each :class:`~logging.LogRecord`
before it reaches any handler:

* URLs are collapsed to ``scheme://host`` plus ``/***`` when they had
  any path or query — we keep the endpoint host (useful for debugging)
  but drop everything that could carry a secret.
* ``UID=...`` / ``PWD=...`` fragments are masked to ``UID=***`` /
  ``PWD=***`` regardless of surrounding separators.
* Both ``record.msg`` (the format string) and ``record.args`` (lazy
  interpolation values) are masked, so we catch ``_log.info("... %s",
  url)`` as well as already-interpolated messages.

Attach once on the root logger at startup — see
:func:`app.core.app_logger.setup`.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

# Match the textual form of an URL. Intentionally greedy — we'd rather
# mask too much than leak a token.
_URL_RE = re.compile(r"https?://[^\s<>\"']+")

# ``PWD=secret`` / ``UID=user`` — ODBC-style credentials. Match until a
# separator character (``;``, whitespace, quote) or end-of-string.
_PWD_RE = re.compile(r"(?i)(PWD=)[^;\s\"']+")
_UID_RE = re.compile(r"(?i)(UID=)[^;\s\"']+")


def _mask_url(match: re.Match[str]) -> str:
    """Collapse an URL to ``scheme://host`` + ``/***`` if anything extra."""
    url = match.group(0)
    # Strip trailing punctuation that was swept in by the regex.
    trailing = ""
    while url and url[-1] in ".,;:)]}\"'":
        trailing = url[-1] + trailing
        url = url[:-1]
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return match.group(0)
    if not parsed.scheme or not parsed.netloc:
        return match.group(0)
    has_extra = bool(parsed.path.strip("/")) or bool(parsed.query) or bool(parsed.fragment)
    base = f"{parsed.scheme}://{parsed.netloc}"
    masked = f"{base}/***" if has_extra else base
    return masked + trailing


def mask_secrets(text: str) -> str:
    """Apply all mask rules to a single string."""
    text = _URL_RE.sub(_mask_url, text)
    text = _PWD_RE.sub(r"\1***", text)
    text = _UID_RE.sub(r"\1***", text)
    return text


def _mask_any(value: Any) -> Any:
    """Mask strings inside arbitrary values; return non-strings unchanged."""
    if isinstance(value, str):
        return mask_secrets(value)
    return value


class SecretFilter(logging.Filter):
    """Masks URLs and credential fragments on every log record.

    The filter mutates the record in place; attach it once on the root
    logger so every handler (Qt bridge, stderr, file) sees the sanitised
    output.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(_mask_any(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: _mask_any(v) for k, v in record.args.items()}
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        return True


__all__ = ["SecretFilter", "mask_secrets"]
