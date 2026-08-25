"""
Provider Configuration — manages API keys for Bytez + NVIDIA NIM + OpenRouter.

Stores keys in ~/.dev/config.json (user-level) or .dev/config.json (project-level).
"""

import os
import json
import stat
from pathlib import Path
from typing import Optional


# Config file locations
USER_CONFIG_DIR = Path.home() / ".dev"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

PROJECT_CONFIG_DIR = Path(".dev")
PROJECT_CONFIG_FILE = PROJECT_CONFIG_DIR / "config.json"


def get_config_dir() -> Path:
    """Get the config directory (project-level if exists, else user-level)."""
    if PROJECT_CONFIG_DIR.exists():
        return PROJECT_CONFIG_DIR
    return USER_CONFIG_DIR


def get_config_file() -> Path:
    """Get the config file path."""
    if PROJECT_CONFIG_FILE.exists():
        return PROJECT_CONFIG_FILE
    return USER_CONFIG_FILE


def load_config() -> dict:
    """Load configuration from file."""
    config_file = get_config_file()
    if config_file.exists():
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(config: dict):
    """Save configuration to file."""
    config_file = get_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write config
    config_file.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    
    # Set restrictive permissions on Unix
    if os.name != "nt":
        try:
            config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
        except OSError:
            pass


def get_api_keys() -> dict[str, list[str]]:
    """
    Get all configured API keys.
    
    Returns:
        {"nvidia": ["key1", ...], "bytez": ["key1"], "openrouter": ["key1"]}
    """
    config = load_config()
    
    keys = {}
    
    # NVIDIA keys
    nvidia_keys = config.get("nvidia_api_keys", [])
    if nvidia_keys:
        keys["nvidia"] = nvidia_keys
    
    # Bytez keys
    bytez_keys = config.get("bytez_api_keys", [])
    if bytez_keys:
        keys["bytez"] = bytez_keys
    
    # OpenRouter keys
    openrouter_keys = config.get("openrouter_api_keys", [])
    if openrouter_keys:
        keys["openrouter"] = openrouter_keys
    
    # Also check environment variables
    nvidia_env = os.environ.get("NVIDIA_API_KEY", "")
    if nvidia_env and nvidia_env not in keys.get("nvidia", []):
        keys.setdefault("nvidia", []).append(nvidia_env)
    
    bytez_env = os.environ.get("BYTEZ_API_KEY", "")
    if bytez_env and bytez_env not in keys.get("bytez", []):
        keys.setdefault("bytez", []).append(bytez_env)
    
    openrouter_env = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_env and openrouter_env not in keys.get("openrouter", []):
        keys.setdefault("openrouter", []).append(openrouter_env)
    
    return keys


def save_api_keys(provider: str, keys: list[str]):
    """Save API keys for a provider."""
    config = load_config()
    
    if provider == "nvidia":
        config["nvidia_api_keys"] = keys
        # Also set env var for backward compatibility
        if keys:
            os.environ["NVIDIA_API_KEY"] = keys[0]
    elif provider == "bytez":
        config["bytez_api_keys"] = keys
        if keys:
            os.environ["BYTEZ_API_KEY"] = keys[0]
    elif provider == "openrouter":
        config["openrouter_api_keys"] = keys
        if keys:
            os.environ["OPENROUTER_API_KEY"] = keys[0]
    
    save_config(config)


def get_provider_order() -> list[str]:
    """Get the configured provider priority order."""
    config = load_config()
    return config.get("provider_order", ["openrouter", "nvidia", "bytez"])


def set_provider_order(order: list[str]):
    """Set the provider priority order."""
    config = load_config()
    config["provider_order"] = order
    save_config(config)


def has_any_key() -> bool:
    """Check if any API key is configured."""
    keys = get_api_keys()
    return bool(keys)


def get_key_count() -> dict[str, int]:
    """Get count of keys per provider."""
    keys = get_api_keys()
    return {prov: len(klist) for prov, klist in keys.items()}


def get_total_key_count() -> int:
    """Get total number of configured keys."""
    return sum(get_key_count().values())


def validate_key(provider: str, key: str) -> bool:
    """Basic key format validation."""
    if provider == "nvidia":
        return key.startswith("nvapi-") and len(key) > 20
    elif provider == "bytez":
        return len(key) > 10  # Bytez keys vary in format
    elif provider == "openrouter":
        return key.startswith("sk-or-") and len(key) > 20
    return False


def remove_provider_keys(provider: str):
    """Remove all keys for a provider."""
    config = load_config()
    
    if provider == "nvidia":
        config.pop("nvidia_api_keys", None)
        os.environ.pop("NVIDIA_API_KEY", None)
    elif provider == "bytez":
        config.pop("bytez_api_keys", None)
        os.environ.pop("BYTEZ_API_KEY", None)
    elif provider == "openrouter":
        config.pop("openrouter_api_keys", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
    
    save_config(config)


def get_config_summary() -> str:
    """Get a human-readable summary of the configuration."""
    keys = get_api_keys()
    order = get_provider_order()
    
    lines = ["Provider Configuration:"]
    for prov in order:
        klist = keys.get(prov, [])
        count = len(klist)
        if count > 0:
            masked = klist[0][:8] + "..." + klist[0][-4:] if len(klist[0]) > 12 else "***"
            lines.append(f"  {prov}: {count} key(s) ({masked})")
        else:
            lines.append(f"  {prov}: no keys configured")
    
    total = get_total_key_count()
    lines.append(f"  Total: {total} key(s)")
    
    return "\n".join(lines)
