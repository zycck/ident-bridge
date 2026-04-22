"""All magic numbers and hardcoded URLs in one place."""

# ── Timing (ms) ──────────────────────────────────────────────────────
DEBOUNCE_SAVE_MS          = 800
DEBOUNCE_SYNTAX_MS        = 300
PING_INTERVAL_MS          = 30_000
TEST_DIALOG_AUTO_RUN_MS   = 80

# ── Limits ───────────────────────────────────────────────────────────
HISTORY_MAX           = 50
LOG_RING_BUFFER       = 500
DEBUG_LOG_BLOCK_LIMIT = 3000
TEST_DIALOG_MAX_ROWS  = 1000

# ── Dimensions (px) ──────────────────────────────────────────────────
HISTORY_ROW_HEIGHT    = 22
NAV_SIDEBAR_W         = 168
TEST_DIALOG_MIN_W     = 700
TEST_DIALOG_MIN_H     = 520
TEST_DIALOG_DEFAULT_W = 860
TEST_DIALOG_DEFAULT_H = 580

# ── External URLs ────────────────────────────────────────────────────
GITHUB_REPO    = "zycck/ident-bridge"
GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"

# ── Identity / metadata ──────────────────────────────────────────────
APP_NAME = "iDentBridge"
EXPORT_SOURCE_ID = "identa-app"
# Keep the current runtime artifact/config names explicit until a dedicated
# migration wave moves users off the legacy iDentSync footprint.
LEGACY_RUNTIME_NAME = "iDentSync"
CONFIG_DIR_NAME = LEGACY_RUNTIME_NAME
EXE_NAME = LEGACY_RUNTIME_NAME
APP_VERSION = "0.1.0"
USER_AGENT = f"{APP_NAME}/{APP_VERSION}"

# ── Misc ─────────────────────────────────────────────────────────────
MIN_DOWNLOAD_BYTES = 1_000_000
MAX_WEBHOOK_ROWS   = 50_000   # safety cap to prevent OOM on huge query results
GOOGLE_SCRIPT_MAX_ROWS_PER_CHUNK = 10_000
GOOGLE_SCRIPT_MAX_PAYLOAD_BYTES = 5 * 1024 * 1024
GOOGLE_SCRIPT_RETRIES = 3
GOOGLE_SCRIPT_TIMEOUT = 20.0
GOOGLE_SCRIPT_HOSTS = ("script.google.com", "script.googleusercontent.com")
