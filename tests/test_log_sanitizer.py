"""Tests for app.core.log_sanitizer.SecretFilter."""

from __future__ import annotations

import logging

import pytest

from app.core.log_sanitizer import SecretFilter, mask_secrets


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


def test_mask_secrets_is_public_helper():
    masked = mask_secrets("https://example.com/hook?token=abc;PWD=secret;UID=user")
    assert "abc" not in masked
    assert "secret" not in masked
    assert "user" not in masked
    assert "example.com" in masked


# --- URL masking ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "fragments_absent", "fragments_present"),
    [
        (
            "Webhook https://hooks.slack.com/services/T123/B456/XYZsecret",
            ("XYZsecret", "T123"),
            ("hooks.slack.com",),
        ),
        (
            "sent to https://example.com/hook?token=abcdef&signature=xyz",
            ("abcdef", "signature"),
            ("example.com",),
        ),
        (
            "pinging https://example.com",
            (),
            ("https://example.com",),
        ),
        (
            "Webhook https://hooks.example.com/services/A/B/C failed",
            ("/A/B/C",),
            ("hooks.example.com",),
        ),
        (
            "Called https://example.com/webhook.",
            ("webhook",),
            (".", "example.com"),
        ),
    ],
)
def test_mask_secrets_masks_supported_url_forms(
    raw: str,
    fragments_absent: tuple[str, ...],
    fragments_present: tuple[str, ...],
) -> None:
    masked = mask_secrets(raw)
    for fragment in fragments_absent:
        assert fragment not in masked
    for fragment in fragments_present:
        assert fragment in masked


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
