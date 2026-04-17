"""Tests for app.core.log_sanitizer.SecretFilter."""

from __future__ import annotations

import logging

import pytest

from app.core.log_sanitizer import SecretFilter


def _make_record(msg: str, args: object = ()) -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


@pytest.fixture
def sanitized() -> SecretFilter:
    return SecretFilter()


def _render(record: logging.LogRecord) -> str:
    """Format the record the same way a real handler would."""
    return logging.Formatter("%(message)s").format(record)


# --- URL masking ---------------------------------------------------------


def test_masks_slack_style_webhook_in_args(sanitized):
    url = "https://hooks.slack.com/services/T123/B456/XYZsecret"
    rec = _make_record("Webhook %s", (url,))
    sanitized.filter(rec)
    out = _render(rec)
    assert "XYZsecret" not in out
    assert "T123" not in out
    assert "hooks.slack.com" in out  # host still visible


def test_masks_query_string_token(sanitized):
    url = "https://example.com/hook?token=abcdef&signature=xyz"
    rec = _make_record("sent to %s", (url,))
    sanitized.filter(rec)
    out = _render(rec)
    assert "abcdef" not in out
    assert "signature" not in out
    assert "example.com" in out


def test_leaves_plain_domain_without_path_alone(sanitized):
    url = "https://example.com"
    rec = _make_record("pinging %s", (url,))
    sanitized.filter(rec)
    out = _render(rec)
    assert out.endswith("https://example.com")


def test_masks_url_in_preformatted_message(sanitized):
    msg = "Webhook https://hooks.example.com/services/A/B/C failed"
    rec = _make_record(msg)
    sanitized.filter(rec)
    out = _render(rec)
    assert "/A/B/C" not in out
    assert "hooks.example.com" in out


def test_preserves_trailing_punctuation(sanitized):
    rec = _make_record("Called %s.", ("https://example.com/webhook",))
    sanitized.filter(rec)
    out = _render(rec)
    assert out.endswith(".")
    assert "webhook" not in out


def test_masks_multiple_urls(sanitized):
    rec = _make_record(
        "%s and %s",
        (
            "https://a.example.com/secret/path",
            "https://b.example.com/also/secret",
        ),
    )
    sanitized.filter(rec)
    out = _render(rec)
    assert "secret" not in out
    assert "a.example.com" in out and "b.example.com" in out


# --- Credentials masking -------------------------------------------------


def test_masks_odbc_pwd(sanitized):
    rec = _make_record(
        "conn=Driver={ODBC};Server=host;UID=admin;PWD=S3cret!;Timeout=5;"
    )
    sanitized.filter(rec)
    out = _render(rec)
    assert "S3cret" not in out
    assert "admin" not in out
    assert "PWD=***" in out
    assert "UID=***" in out


def test_masks_pwd_in_args(sanitized):
    rec = _make_record(
        "connecting with %s",
        ("Server=host;PWD=top_secret;Driver=xyz",),
    )
    sanitized.filter(rec)
    out = _render(rec)
    assert "top_secret" not in out


# --- Robustness ----------------------------------------------------------


def test_leaves_non_string_args_untouched(sanitized):
    rec = _make_record("rows=%d ok=%s", (42, True))
    sanitized.filter(rec)
    out = _render(rec)
    assert "rows=42" in out
    assert "ok=True" in out


def test_dict_args_are_masked(sanitized):
    rec = _make_record(
        "call %(url)s with %(n)d rows",
        {"url": "https://hooks.slack.com/services/A/B/C", "n": 5},
    )
    sanitized.filter(rec)
    out = _render(rec)
    assert "/A/B/C" not in out
    assert "5 rows" in out


def test_filter_returns_true_always(sanitized):
    rec = _make_record("plain text")
    assert sanitized.filter(rec) is True


def test_non_http_urls_are_ignored(sanitized):
    rec = _make_record("path=%s", ("file:///C:/tmp/x.txt",))
    sanitized.filter(rec)
    out = _render(rec)
    assert "x.txt" in out  # not http(s), not masked


def test_integration_masks_through_root_logger(sanitized, caplog):
    """Attach filter on a local logger, verify masking in captured records."""
    logger = logging.getLogger("test.sanitizer.integration")
    logger.addFilter(sanitized)
    logger.setLevel(logging.DEBUG)
    try:
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            logger.info(
                "posting %d rows → %s",
                100,
                "https://hooks.slack.com/services/T/B/X",
            )
        msg = caplog.records[-1].getMessage()
        assert "T/B/X" not in msg
        assert "hooks.slack.com" in msg
    finally:
        logger.removeFilter(sanitized)
