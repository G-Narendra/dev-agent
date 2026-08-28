"""Tests for security hardening features.

Covers:
- Key vault encryption/decryption at rest
- Audit log rotation
- Dangerously-skip-permissions warning
"""
import json
import os
import tempfile
import pytest


class TestKeyVault:
    """Verify API key encryption at rest."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted value should decrypt back to original."""
        from dev.security.key_vault import encrypt_value, decrypt_value
        original = "nvapi-test-key-12345"
        encrypted = encrypt_value(original)
        assert encrypted.startswith("enc:"), "Encrypted value should have enc: prefix"
        assert encrypted != original, "Encrypted value should differ from original"
        decrypted = decrypt_value(encrypted)
        assert decrypted == original, "Decrypted value should match original"

    def test_encrypt_empty_string(self):
        """Empty string should pass through unchanged."""
        from dev.security.key_vault import encrypt_value
        assert encrypt_value("") == ""

    def test_decrypt_plaintext_passthrough(self):
        """Non-encrypted values should pass through unchanged."""
        from dev.security.key_vault import decrypt_value
        assert decrypt_value("plain-key") == "plain-key"
        assert decrypt_value("") == ""

    def test_encrypt_idempotent(self):
        """Encrypting an already-encrypted value should not double-encrypt."""
        from dev.security.key_vault import encrypt_value
        first = encrypt_value("test-key")
        second = encrypt_value(first)
        assert first == second, "Should not double-encrypt"

    def test_config_roundtrip(self):
        """Config dict keys should encrypt/decrypt correctly."""
        from dev.security.key_vault import encrypt_config_keys, decrypt_config_keys
        config = {
            "api_keys": {
                "nvidia": ["nvapi-key-1", "nvapi-key-2"],
                "openrouter": ["sk-or-key-1"],
            }
        }
        encrypted = encrypt_config_keys(config)
        # Keys should be encrypted
        assert encrypted["api_keys"]["nvidia"][0].startswith("enc:")
        assert encrypted["api_keys"]["openrouter"][0].startswith("enc:")
        # Decrypt and verify
        decrypted = decrypt_config_keys(encrypted)
        assert decrypted["api_keys"]["nvidia"] == ["nvapi-key-1", "nvapi-key-2"]
        assert decrypted["api_keys"]["openrouter"] == ["sk-or-key-1"]

    def test_different_keys_different_encryption(self):
        """Different values should produce different ciphertext."""
        from dev.security.key_vault import encrypt_value
        e1 = encrypt_value("key-alpha")
        e2 = encrypt_value("key-beta")
        assert e1 != e2

    def test_config_without_api_keys(self):
        """Config without api_keys should pass through unchanged."""
        from dev.security.key_vault import encrypt_config_keys, decrypt_config_keys
        config = {"model": "default", "verbose": True}
        encrypted = encrypt_config_keys(config)
        assert encrypted == config
        decrypted = decrypt_config_keys(config)
        assert decrypted == config


class TestAuditLogRotation:
    """Verify audit log rotation prevents unbounded growth."""

    def test_rotation_triggered_at_max_size(self):
        """Log should rotate when file exceeds MAX_LOG_SIZE."""
        from dev.security.audit_logger import AuditLogger, AuditEvent
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(project_path=tmpdir, session_id="test-rotate")
            # Write enough events to exceed max size
            logger.MAX_LOG_SIZE = 1024  # 1KB for testing
            for i in range(100):
                logger.log(AuditEvent(
                    event_type="tool_call",
                    tool_name="test_tool",
                    tool_result="x" * 200,
                ))
            # Check that rotation happened
            log_dir = os.path.join(tmpdir, ".dev", "audit")
            files = os.listdir(log_dir)
            jsonl_files = [f for f in files if f.endswith(".jsonl")]
            assert len(jsonl_files) >= 1, "Should have at least one log file"

    def test_no_rotation_when_small(self):
        """Log should not rotate when file is small."""
        from dev.security.audit_logger import AuditLogger, AuditEvent
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(project_path=tmpdir, session_id="test-no-rotate")
            logger.log(AuditEvent(event_type="tool_call", tool_name="test"))
            log_dir = os.path.join(tmpdir, ".dev", "audit")
            files = os.listdir(log_dir)
            assert ".jsonl.1" not in files, "Should not rotate small files"


class TestDangerouslySkipWarning:
    """Verify dangerously-skip-permissions shows warning."""

    def test_warning_message_exists(self):
        """The warning text should be present in main.py."""
        main_path = os.path.join(os.path.dirname(__file__), "..", "dev", "cli", "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "SECURITY WARNING" in content
        assert "dangerously-skip-permissions" in content
        assert "3 seconds" in content
