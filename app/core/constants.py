# -*- coding: utf-8 -*-
"""All magic numbers and hardcoded URLs in one place."""
from __future__ import annotations

# ── Timing (ms) ──────────────────────────────────────────────────────
DEBOUNCE_SAVE_MS          = 800
DEBOUNCE_SYNTAX_MS        = 300
PING_INTERVAL_MS          = 30_000
SETTINGS_SAVE_DEBOUNCE_MS = 800
TEST_DIALOG_AUTO_RUN_MS   = 80

# ── Limits ───────────────────────────────────────────────────────────
HISTORY_MAX           = 50
LOG_RING_BUFFER       = 500
DEBUG_LOG_BLOCK_LIMIT = 3000

# ── Dimensions (px) ──────────────────────────────────────────────────
SQL_EDITOR_MIN_H      = 88
SQL_EDITOR_MAX_H      = 180
HISTORY_SCROLL_MAX_H  = 160
HISTORY_ROW_HEIGHT    = 22
SCHED_VALUE_INPUT_W   = 72
NAV_SIDEBAR_W         = 168
TEST_DIALOG_MIN_W     = 700
TEST_DIALOG_MIN_H     = 520
TEST_DIALOG_DEFAULT_W = 860
TEST_DIALOG_DEFAULT_H = 580
ERROR_DIALOG_MIN_W    = 600
ERROR_DIALOG_MIN_H    = 400

# ── External URLs ────────────────────────────────────────────────────
GITHUB_REPO    = "zycck/ident-bridge"
GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"

# ── Identity / metadata ──────────────────────────────────────────────
APP_NAME       = "iDentBridge"
CONFIG_DIR_NAME = "iDentSync"
EXE_NAME        = "iDentSync"
APP_VERSION     = "0.0.1"
USER_AGENT      = f"{APP_NAME}/{APP_VERSION}"

# ── Misc ─────────────────────────────────────────────────────────────
MIN_DOWNLOAD_BYTES = 1_000_000
MAX_WEBHOOK_ROWS   = 50_000   # safety cap to prevent OOM on huge query results
