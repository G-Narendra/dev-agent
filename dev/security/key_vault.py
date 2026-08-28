"""
Key Vault — API key encryption at rest.

Uses machine-derived keys (hostname + username + salt) to encrypt/decrypt
API keys stored in config.json. This prevents casual reading of keys
if the config file is copied or accessed by other processes.

NOT cryptographically strong — use for obfuscation only.
For true encryption, use a dedicated secrets manager.
"""

from __future__ import annotations

import base64
import hashlib
import os
import platform
import struct
from pathlib import Path


# Salt for key derivation (hardcoded, same across installations)
_SALT = b"dev-agent-key-vault-2024"


def _derive_key() -> bytes:
    """Derive an encryption key from machine-specific info."""
    # Combine hostname, username, and salt
    machine_id = f"{platform.node()}:{os.getuid() if hasattr(os, 'getuid') else os.getenv('USERNAME', 'user')}"
    raw = hashlib.sha256(machine_id.encode() + _SALT).digest()
    return raw[:32]  # 256-bit key


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR data with repeating key."""
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def encrypt_value(value: str) -> str:
    """Encrypt a string value for storage.
    
    Returns a prefixed string: "enc:<base64-encoded-encrypted-data>"
    """
    if not value:
        return value
    
    # Already encrypted
    if value.startswith("enc:"):
        return value
    
    key = _derive_key()
    data = value.encode("utf-8")
    
    # XOR encrypt
    encrypted = _xor_bytes(data, key)
    
    # Base64 encode
    encoded = base64.b64encode(encrypted).decode("ascii")
    
    return f"enc:{encoded}"


def decrypt_value(value: str) -> str:
    """Decrypt an encrypted string value.
    
    If the value is not encrypted (no "enc:" prefix), returns as-is.
    """
    if not value:
        return value
    
    # Not encrypted
    if not value.startswith("enc:"):
        return value
    
    # Strip prefix
    encoded = value[4:]
    
    try:
        key = _derive_key()
        encrypted = base64.b64decode(encoded)
        
        # XOR decrypt (same as encrypt — XOR is symmetric)
        decrypted = _xor_bytes(encrypted, key)
        
        return decrypted.decode("utf-8")
    except Exception:
        # Decryption failed — return as-is
        return value


def encrypt_config_keys(config: dict) -> dict:
    """Encrypt all API keys in a config dict."""
    if "api_keys" not in config:
        return config
    
    config = config.copy()
    encrypted_keys = {}
    
    for provider, keys in config["api_keys"].items():
        if isinstance(keys, list):
            encrypted_keys[provider] = [encrypt_value(k) for k in keys]
        else:
            encrypted_keys[provider] = keys
    
    config["api_keys"] = encrypted_keys
    return config


def decrypt_config_keys(config: dict) -> dict:
    """Decrypt all API keys in a config dict."""
    if "api_keys" not in config:
        return config
    
    config = config.copy()
    decrypted_keys = {}
    
    for provider, keys in config["api_keys"].items():
        if isinstance(keys, list):
            decrypted_keys[provider] = [decrypt_value(k) for k in keys]
        else:
            decrypted_keys[provider] = keys
    
    config["api_keys"] = decrypted_keys
    return config
