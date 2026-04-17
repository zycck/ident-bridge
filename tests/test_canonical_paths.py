"""Smoke-tests for the canonical import paths introduced by Stage 5.

Verifies that every new path exposes the same objects the legacy path
does — so downstream code can safely migrate import-by-import.
"""

from __future__ import annotations


def test_domain_reexports_config_types():
    from app.config import AppConfig as LegacyCfg, ExportJob as LegacyJob
    from app.domain import AppConfig, ExportJob, TriggerType
    assert AppConfig is LegacyCfg
    assert ExportJob is LegacyJob
    assert TriggerType.MANUAL.value == "manual"


def test_domain_reexports_result_types():
    from app.config import QueryResult as LegacyQR
    from app.domain.results import QueryResult, SqlInstance, SyncResult
    assert QueryResult is LegacyQR
    assert SqlInstance.__name__ == "SqlInstance"
    assert SyncResult.__name__ == "SyncResult"


def test_domain_constants_reexports_names():
    from app.core import constants as legacy
    from app.domain import constants as canonical
    assert canonical.APP_NAME == legacy.APP_NAME
    assert canonical.MAX_WEBHOOK_ROWS == legacy.MAX_WEBHOOK_ROWS


def test_platform_dpapi_reexports():
    from app.core.dpapi import encrypt as legacy_encrypt
    from app.platform.dpapi import encrypt
    assert encrypt is legacy_encrypt


def test_platform_startup_reexports():
    from app.core.startup import is_registered as legacy_is_registered
    from app.platform.startup import is_registered
    assert is_registered is legacy_is_registered


def test_platform_updater_reexports():
    from app.core.updater import check_latest as legacy_check
    from app.platform.updater import check_latest
    assert check_latest is legacy_check


def test_log_ext_qt_handler_reexports():
    from app.core.app_logger import QtLogHandler as LegacyHandler
    from app.log_ext.qt_handler import QtLogHandler
    assert QtLogHandler is LegacyHandler


def test_log_ext_sanitizer_reexports():
    from app.core.log_sanitizer import SecretFilter as LegacyFilter
    from app.log_ext.sanitizer import SecretFilter
    assert SecretFilter is LegacyFilter


def test_log_ext_package_bundles_common_api():
    from app.log_ext import QtLogHandler, SecretFilter, setup
    assert QtLogHandler is not None
    assert SecretFilter is not None
    assert callable(setup)
