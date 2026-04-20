"""Tests for app.config.ConfigManager + TypedDicts + TriggerType."""
import json
import os
import sys
from pathlib import Path

import pytest

from app.config import (
    AppConfig,
    ConfigManager,
    ExportHistoryEntry,
    ExportJob,
    TriggerType,
)


# ── TriggerType enum ──────────────────────────────────────────────────

def test_trigger_type_values():
    assert TriggerType.MANUAL.value == "manual"
    assert TriggerType.SCHEDULED.value == "scheduled"
    assert TriggerType.TEST.value == "test"
    assert issubclass(TriggerType, str)


def test_trigger_type_can_be_constructed_from_string():
    assert TriggerType("manual") is TriggerType.MANUAL
    assert TriggerType("scheduled") is TriggerType.SCHEDULED
    assert TriggerType("test") is TriggerType.TEST


def test_trigger_type_invalid_raises():
    with pytest.raises(ValueError):
        TriggerType("bogus")


def test_export_job_requires_identity_fields():
    assert {"id", "name"} <= set(ExportJob.__required_keys__)


# ── ConfigManager basic load/save ─────────────────────────────────────

def test_load_returns_empty_when_no_file(tmp_config):
    cfg = tmp_config.load()
    assert isinstance(cfg, dict)
    # Empty config → no keys
    assert not cfg or len(cfg) == 0


def test_save_then_load_roundtrip(tmp_config):
    tmp_config.save(AppConfig(
        sql_instance="localhost\\SQLEXPRESS",
        sql_database="test_db",
        github_repo="zycck/ident-bridge",
        auto_update_check=True,
        run_on_startup=False,
    ))
    cfg = tmp_config.load()
    assert cfg.get("sql_instance") == "localhost\\SQLEXPRESS"
    assert cfg.get("sql_database") == "test_db"
    assert cfg.get("auto_update_check") is True
    assert cfg.get("run_on_startup") is False


def test_save_creates_config_file(tmp_config, tmp_path):
    tmp_config.save(AppConfig(sql_instance="x"))
    config_file = tmp_path / "config.json"
    assert config_file.exists()


def test_save_writes_valid_json(tmp_config, tmp_path):
    tmp_config.save(AppConfig(sql_instance="x", sql_database="y"))
    config_file = tmp_path / "config.json"
    parsed = json.loads(config_file.read_text(encoding="utf-8"))
    assert parsed["sql_instance"] == "x"
    assert parsed["sql_database"] == "y"


def test_default_config_dir_prefers_appdata(monkeypatch, tmp_path):
    import app.config as config_module

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    expected = tmp_path / "appdata" / config_module.CONFIG_DIR_NAME
    assert config_module._default_config_dir() == expected


def test_default_config_dir_falls_back_to_xdg(monkeypatch, tmp_path):
    import app.config as config_module

    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    expected = tmp_path / "xdg" / config_module.CONFIG_DIR_NAME
    assert config_module._default_config_dir() == expected


def test_save_uses_atomic_replace(tmp_config, tmp_path, monkeypatch):
    import app.config as config_module

    replace_calls: list[tuple[Path, Path]] = []
    original_replace = config_module.os.replace

    def _recording_replace(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(config_module.os, "replace", _recording_replace)

    tmp_config.save(AppConfig(sql_instance="atomic"))

    assert replace_calls, "save() should replace a temporary file atomically"
    assert replace_calls[0][1] == tmp_path / "config.json"
    assert (tmp_path / "config.json").exists()
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["sql_instance"] == "atomic"


# ── update() helper (atomic load → merge → save) ──────────────────────

def test_update_merges_without_clobbering(tmp_config):
    tmp_config.save(AppConfig(
        sql_instance="host1",
        sql_database="db1",
        auto_update_check=True,
    ))
    tmp_config.update(sql_database="db2")
    cfg = tmp_config.load()
    # The new key is set
    assert cfg.get("sql_database") == "db2"
    # Other keys are preserved
    assert cfg.get("sql_instance") == "host1"
    assert cfg.get("auto_update_check") is True


def test_update_with_no_changes_is_noop(tmp_config):
    tmp_config.save(AppConfig(sql_instance="host1"))
    tmp_config.update()  # no kwargs
    cfg = tmp_config.load()
    assert cfg.get("sql_instance") == "host1"


# ── batch() context manager (audit D2 / J1) ───────────────────────────

def test_batch_coalesces_multiple_updates_into_one_save(tmp_config, tmp_path, monkeypatch):
    import app.config as config_module

    save_calls = 0
    original_save = tmp_config.save

    def _counting_save(cfg):
        nonlocal save_calls
        save_calls += 1
        original_save(cfg)

    monkeypatch.setattr(tmp_config, "save", _counting_save)

    with tmp_config.batch():
        tmp_config.update(sql_instance="h1")
        tmp_config.update(sql_database="db1")
        tmp_config.update(auto_update_check=True)

    # Exactly one save at batch exit, not three
    assert save_calls == 1
    cfg = tmp_config.load()
    assert cfg.get("sql_instance") == "h1"
    assert cfg.get("sql_database") == "db1"
    assert cfg.get("auto_update_check") is True


def test_batch_with_no_changes_does_not_save(tmp_config, monkeypatch):
    save_calls = 0
    monkeypatch.setattr(tmp_config, "save", lambda cfg: (_ for _ in ()).throw(AssertionError("should not save")) if False else None)
    # Count real calls via a separate wrapper
    original_save = tmp_config.save

    def _counting(cfg):
        nonlocal save_calls
        save_calls += 1

    monkeypatch.setattr(tmp_config, "save", _counting)

    with tmp_config.batch():
        pass

    assert save_calls == 0


def test_batch_nested_only_outer_flushes(tmp_config, monkeypatch):
    save_calls = 0
    original_save = tmp_config.save

    def _counting_save(cfg):
        nonlocal save_calls
        save_calls += 1
        original_save(cfg)

    monkeypatch.setattr(tmp_config, "save", _counting_save)

    with tmp_config.batch():
        tmp_config.update(sql_instance="outer")
        with tmp_config.batch():
            tmp_config.update(sql_database="inner")
        # inner exit must not flush
        assert save_calls == 0
    # outer exit flushes exactly once
    assert save_calls == 1


def test_batch_exception_still_flushes_pending_writes(tmp_config, monkeypatch):
    """On exception inside batch, we still flush what was buffered.

    The rationale: a half-applied settings change is still the user's
    intent for the fields they did touch — losing them silently is worse
    than recording them.
    """
    save_calls = 0
    original_save = tmp_config.save

    def _counting_save(cfg):
        nonlocal save_calls
        save_calls += 1
        original_save(cfg)

    monkeypatch.setattr(tmp_config, "save", _counting_save)

    with pytest.raises(RuntimeError):
        with tmp_config.batch():
            tmp_config.update(sql_instance="partial")
            raise RuntimeError("boom")

    assert save_calls == 1
    cfg = tmp_config.load()
    assert cfg.get("sql_instance") == "partial"


def test_update_outside_batch_still_saves_immediately(tmp_config, monkeypatch):
    save_calls = 0
    original_save = tmp_config.save

    def _counting_save(cfg):
        nonlocal save_calls
        save_calls += 1
        original_save(cfg)

    monkeypatch.setattr(tmp_config, "save", _counting_save)

    tmp_config.update(sql_instance="immediate")
    assert save_calls == 1


# ── DPAPI encryption (Windows-only) ───────────────────────────────────

@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_encrypt_decrypt_roundtrip(tmp_config):
    """Save credentials → reload → plaintext recovered via DPAPI."""
    tmp_config.save(AppConfig(
        sql_user="alice",
        sql_password="s3cret-p4ss",
    ))
    cfg = tmp_config.load()
    assert cfg.get("sql_user") == "alice"
    assert cfg.get("sql_password") == "s3cret-p4ss"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_credentials_stored_encrypted_on_disk(tmp_config, tmp_path):
    """The on-disk config.json should NOT contain plaintext credentials."""
    tmp_config.save(AppConfig(sql_user="alice", sql_password="s3cret"))
    config_file = tmp_path / "config.json"
    raw = config_file.read_text(encoding="utf-8")
    # Plaintext should not appear in the saved JSON
    assert "alice" not in raw
    assert "s3cret" not in raw


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_encrypt_raises_winerror_on_failure(monkeypatch):
    import app.core.dpapi as dpapi

    class _FakeCrypt32:
        def CryptProtectData(self, *args, **kwargs):
            return False

    class _FakeKernel32:
        def GetLastError(self):
            return 123

        def LocalFree(self, *args, **kwargs):
            raise AssertionError("cleanup should not run on failed encrypt")

    winerror_calls: list[tuple[object, ...]] = []

    def _fake_winerror(*args):
        winerror_calls.append(args)
        raise OSError("winerror")

    monkeypatch.setattr(dpapi, "_IS_WINDOWS", True)
    monkeypatch.setattr(dpapi, "_crypt32", _FakeCrypt32())
    monkeypatch.setattr(dpapi, "_kernel32", _FakeKernel32())
    monkeypatch.setattr(dpapi.ctypes, "WinError", _fake_winerror)

    with pytest.raises(OSError, match="winerror"):
        dpapi.encrypt("secret")

    assert winerror_calls == [()]


def test_empty_credentials_no_warning(tmp_config, caplog):
    """sql_user/sql_password = "" should NOT log a warning."""
    import logging
    caplog.set_level(logging.WARNING)
    tmp_config.save(AppConfig(sql_user="", sql_password="", sql_instance="x"))
    caplog.clear()
    cfg = tmp_config.load()
    # No warnings about decryption
    decrypt_warnings = [r for r in caplog.records if "расшифровать" in r.getMessage()]
    assert len(decrypt_warnings) == 0, f"unexpected warnings: {decrypt_warnings}"


def test_corrupted_dpapi_field_logs_warning_and_clears(tmp_config, tmp_path, caplog, monkeypatch):
    """Encrypted blob present but undecryptable → warning + field cleared."""
    import logging
    # Write a config.json directly with a fake encrypted blob
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({
            "sql_instance": "x",
            "sql_user": "ZmFrZS1ibG9i",  # base64("fake-blob")
            "sql_password": "ZmFrZS1ibG9i",
        }),
        encoding="utf-8",
    )
    # Mock dpapi.decrypt to raise
    def _fail(_blob):
        raise RuntimeError("DPAPI master key changed")
    monkeypatch.setattr("app.core.dpapi.decrypt", _fail)

    caplog.set_level(logging.WARNING)
    cfg = tmp_config.load()
    # Field cleared
    assert cfg.get("sql_user") == ""
    assert cfg.get("sql_password") == ""
    # Warning logged
    decrypt_warnings = [r for r in caplog.records if "расшифровать" in r.getMessage()]
    assert len(decrypt_warnings) >= 1


# ── Trigger migration (auto → scheduled) ──────────────────────────────

def test_legacy_auto_trigger_migrated_to_scheduled_on_load(tmp_config, tmp_path):
    """Existing history entries with trigger='auto' should be rewritten."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({
            "export_jobs": [
                {
                    "id": "j1",
                    "name": "Old job",
                    "history": [
                        {"ts": "2025-01-01 10:00", "trigger": "auto", "ok": True, "rows": 5},
                        {"ts": "2025-01-01 11:00", "trigger": "manual", "ok": True, "rows": 3},
                    ],
                }
            ],
        }),
        encoding="utf-8",
    )
    cfg = tmp_config.load()
    jobs = cfg.get("export_jobs") or []
    assert len(jobs) == 1
    history = jobs[0].get("history") or []
    triggers = [h.get("trigger") for h in history]
    assert "auto" not in triggers, "legacy 'auto' should be migrated"
    assert triggers[0] == "scheduled"
    assert triggers[1] == "manual"  # unchanged


def test_export_jobs_missing_identity_fields_are_normalized_on_load(tmp_config, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({
            "export_jobs": [
                {
                    "history": [],
                    "sql_query": "SELECT 1",
                }
            ],
        }),
        encoding="utf-8",
    )

    cfg = tmp_config.load()
    jobs = cfg.get("export_jobs") or []
    assert len(jobs) == 1
    assert jobs[0]["id"]
    assert jobs[0]["name"] == ""


# ── Invalid JSON resilience ───────────────────────────────────────────

def test_invalid_json_falls_back_to_last_known(tmp_config, tmp_path):
    """Corrupted config.json should not crash; load returns last cached cfg."""
    # First save a valid config (this also warms _cfg in memory)
    tmp_config.save(AppConfig(sql_instance="known"))
    # Load once so _cfg is populated in the manager's cache
    tmp_config.load()
    # Corrupt the file
    config_file = tmp_path / "config.json"
    config_file.write_text("{ NOT VALID JSON", encoding="utf-8")
    # load() should return the in-memory cached version
    cfg = tmp_config.load()
    assert cfg.get("sql_instance") == "known"


# ── TypedDict generics ────────────────────────────────────────────────

def test_export_job_history_is_list(tmp_config):
    """ExportJob.history annotation should be list[ExportHistoryEntry]."""
    import typing
    hints = typing.get_type_hints(ExportJob)
    history_type = hints.get("history")
    assert history_type is not None
    # Should be parameterized list (e.g. list[ExportHistoryEntry])
    assert hasattr(history_type, "__origin__") or history_type is list
