"""Configuration and settings for karing-cli."""

import os
import json
from pathlib import Path

# Default values from Karing source code (setting_manager.dart)
DEFAULT_CONTROL_PORT = 3057
DEFAULT_MIXED_PORT = 3067
DEFAULT_HTML_BOARD_PORT = 3072
DEFAULT_HOST = "127.0.0.1"

# Karing Group Container path (macOS)
KARING_GROUP_CONTAINER = Path.home() / "Library" / "Group Containers" / \
    "group.com.nebula.karing"
KARING_SETTING_FILE = KARING_GROUP_CONTAINER / "karing_setting.json"
KARING_SERVICE_FILE = KARING_GROUP_CONTAINER / "service.json"
KARING_SERVICE_CORE_FILE = KARING_GROUP_CONTAINER / "service_core.json"

# Config file for karing-cli itself
CONFIG_DIR = Path.home() / ".config" / "karing-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_karing_settings():
    """Load Karing's own settings file to get port/host info."""
    try:
        if KARING_SETTING_FILE.exists():
            with open(KARING_SETTING_FILE, "r") as f:
                data = json.load(f)
                proxy = data.get("proxy", {})
                return {
                    "host": proxy.get("host", DEFAULT_HOST),
                    "control_port": proxy.get("control_port", DEFAULT_CONTROL_PORT),
                    "mixed_port": proxy.get("mixed_port", DEFAULT_MIXED_PORT),
                    "html_board_port": data.get("html_board_port", DEFAULT_HTML_BOARD_PORT),
                }
    except Exception:
        pass
    return {
        "host": DEFAULT_HOST,
        "control_port": DEFAULT_CONTROL_PORT,
        "mixed_port": DEFAULT_MIXED_PORT,
        "html_board_port": DEFAULT_HTML_BOARD_PORT,
    }


def load_cli_config():
    """Load karing-cli's own config (secret etc)."""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_cli_config(config):
    """Save karing-cli's config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_secret():
    """Get API secret from multiple sources.

    Priority:
    1. --secret CLI flag (handled in main.py)
    2. KARING_SECRET environment variable
    3. Saved config file
    4. Karing service.json (auto-discovered)
    5. Karing service_core.json (auto-discovered)
    6. Try empty string (might work if no secret set)
    """
    # Check environment variable
    env_secret = os.environ.get("KARING_SECRET")
    if env_secret:
        return env_secret

    # Check saved config
    config = load_cli_config()
    saved_secret = config.get("secret")
    if saved_secret:
        return saved_secret

    # Auto-discover from Karing service.json
    try:
        if KARING_SERVICE_FILE.exists():
            with open(KARING_SERVICE_FILE, "r") as f:
                data = json.load(f)
                secret = data.get("secret")
                if secret:
                    return secret
    except Exception:
        pass

    # Auto-discover from Karing service_core.json (clash_api config)
    try:
        if KARING_SERVICE_CORE_FILE.exists():
            with open(KARING_SERVICE_CORE_FILE, "r") as f:
                data = json.load(f)
                clash_api = data.get("experimental", {}).get("clash_api", {})
                secret = clash_api.get("secret")
                if secret:
                    return secret
    except Exception:
        pass

    return None


def get_secret_source():
    """Return a tuple of (secret_value, source_description) for display."""
    env_secret = os.environ.get("KARING_SECRET")
    if env_secret:
        return env_secret, "env var (KARING_SECRET)"

    config = load_cli_config()
    saved_secret = config.get("secret")
    if saved_secret:
        return saved_secret, "saved config"

    try:
        if KARING_SERVICE_FILE.exists():
            with open(KARING_SERVICE_FILE, "r") as f:
                data = json.load(f)
                secret = data.get("secret")
                if secret:
                    return secret, f"auto (service.json)"
    except Exception:
        pass

    try:
        if KARING_SERVICE_CORE_FILE.exists():
            with open(KARING_SERVICE_CORE_FILE, "r") as f:
                data = json.load(f)
                clash_api = data.get("experimental", {}).get("clash_api", {})
                secret = clash_api.get("secret")
                if secret:
                    return secret, f"auto (service_core.json)"
    except Exception:
        pass

    return None, "not configured"
