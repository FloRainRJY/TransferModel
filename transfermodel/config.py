"""Centralised configuration for TransferModel.

Every value can be overridden via environment variable (prefixed with TM_).
Import this module and access attributes directly::

    from transfermodel import config
    print(config.DEFAULT_HOST)
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve helpers
# ---------------------------------------------------------------------------

_BOOL_MAP = {"1": True, "0": False, "true": True, "false": False}


def _env(key: str, default: str) -> str:
    return os.environ.get(f"TM_{key}", default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(f"TM_{key}", str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(f"TM_{key}", str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    return _BOOL_MAP.get(
        os.environ.get(f"TM_{key}", "").lower(), default
    )


def _env_path(key: str, default: Path) -> Path:
    val = os.environ.get(f"TM_{key}", "")
    return Path(val) if val else default


# ===================================================================
# Server
# ===================================================================

DEFAULT_HOST = _env("HOST", "127.0.0.1")
DEFAULT_PORT = _env_int("PORT", 8080)
DEFAULT_LOG_LEVEL = _env("LOG_LEVEL", "info")

# ===================================================================
# Provider defaults
# ===================================================================

DEFAULT_PROVIDER_TIMEOUT = _env_int("PROVIDER_TIMEOUT", 120)
DEFAULT_PROVIDER_PRIORITY = _env_int("PROVIDER_PRIORITY", 10)
DEFAULT_PROVIDER_ENABLED = _env_bool("PROVIDER_ENABLED", True)

# ===================================================================
# API protocol
# ===================================================================

ANTHROPIC_VERSION = _env("ANTHROPIC_VERSION", "2023-06-01")
TEST_CONNECTION_TIMEOUT = _env_float("TEST_TIMEOUT", 15.0)

# ===================================================================
# UI
# ===================================================================

DASHBOARD_POLL_MS = _env_int("POLL_MS", 500)
WINDOW_MIN_WIDTH = _env_int("WINDOW_MIN_WIDTH", 800)
WINDOW_MIN_HEIGHT = _env_int("WINDOW_MIN_HEIGHT", 560)
WINDOW_DEFAULT_WIDTH = _env_int("WINDOW_WIDTH", 900)
WINDOW_DEFAULT_HEIGHT = _env_int("WINDOW_HEIGHT", 640)
APP_NAME = _env("APP_NAME", "TransferModel")
APP_ORG = _env("APP_ORG", "TransferModel")

# ===================================================================
# Storage
# ===================================================================

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = _env_path("DATA_DIR", _PROJECT_ROOT / "data")

# ===================================================================
# Logging
# ===================================================================

LOG_RESPONSE_PREVIEW_CHARS = _env_int("LOG_PREVIEW_CHARS", 300)
