"""
Path helpers for running from source OR a frozen executable (PyInstaller).

Key ideas:
- app_root: where static web assets live (repo root when running from source; _MEIPASS when frozen)
- data_root: where we store writable/persistent files (config, custom decoders)
"""

from __future__ import annotations

import os
import sys
from typing import Optional


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def get_app_root() -> str:
    """Directory containing the shipped static assets."""
    if is_frozen():
        return str(getattr(sys, "_MEIPASS"))
    return os.path.dirname(__file__)


def _is_writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        test_file = os.path.join(path, ".write_test")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
        return True
    except Exception:
        return False


def get_data_root() -> str:
    """Writable directory for persistent state."""
    # Explicit override
    override = os.environ.get("RBT_DATA_DIR", "").strip()
    if override:
        os.makedirs(override, exist_ok=True)
        return override

    # Prefer alongside the executable for a "portable" install
    if is_frozen():
        exe_dir = os.path.dirname(sys.executable)
        if _is_writable_dir(exe_dir):
            return exe_dir

    # Running from source: keep using repo root (matches current behavior)
    src_root = os.path.dirname(__file__)
    if _is_writable_dir(src_root):
        return src_root

    # Fallback: user/profile dir (offline-friendly, no admin required)
    # Linux: XDG_DATA_HOME or ~/.local/share/RadioBridgeTools
    # Windows: LOCALAPPDATA/APPDATA or ~/RadioBridgeTools
    if os.name == "posix":
        local_app = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    else:
        local_app = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    fallback = os.path.join(local_app, "RadioBridgeTools")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def get_config_dir() -> str:
    p = os.path.join(get_data_root(), "config")
    os.makedirs(p, exist_ok=True)
    return p


def get_custom_decoders_dir() -> str:
    p = os.path.join(get_data_root(), "NetworkDashboard-0.1", "static", "js", "decoders", "custom")
    os.makedirs(p, exist_ok=True)
    return p


def get_network_dashboard_py_dir() -> str:
    # This is needed for importing radiobridgev3.py (enhanced decoder)
    return os.path.join(get_app_root(), "NetworkDashboard-0.1", "static", "py")


def get_uplink_cache_dir() -> str:
    """Writable directory for persistent uplink cache (JSONL). Used so packets are stored when browser is closed."""
    p = os.path.join(get_data_root(), "uplink_cache")
    os.makedirs(p, exist_ok=True)
    return p

