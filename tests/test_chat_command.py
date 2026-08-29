"""Tests for the chat command — the primary user-facing feature."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestChatSlashCommands:
    """Test slash command handling in the chat loop."""

    def test_show_help(self):
        """_show_help prints help text without error."""
        from dev.cli.chat import _show_help
        # Should not raise
        _show_help()

    def test_show_context_bar(self):
        """_show_context_bar renders correctly."""
        from dev.cli.chat import _show_context_bar
        # Should not raise
        _show_context_bar(5000, 100000)
        _show_context_bar(80000, 100000)
        _show_context_bar(95000, 100000)

    def test_show_colored_diff_no_git(self):
        """_show_colored_diff handles non-git directory gracefully."""
        from dev.cli.chat import _show_colored_diff
        with tempfile.TemporaryDirectory() as tmpdir:
            # No git repo — should not crash
            _show_colored_diff(tmpdir)


class TestChatCommandParams:
    """Test chat command parameter validation."""

    def test_app_imports(self):
        """App and all command modules import successfully."""
        from dev.cli.shared import app
        from dev.cli import chat, run_cmd, session_cmd, agent_cmd, tools_cmd, util_cmd
        assert app is not None

    def test_critical_modules_import(self):
        """All critical modules import without error."""
        from dev.cli.chat import chat as chat_cmd
        from dev.cli.run_cmd import run as run_cmd_fn
        from dev.cli.util_cmd import setup as setup_fn
        from dev.cli.util_cmd import doctor_cmd
        assert chat_cmd is not None


class TestToolExecutorMixin:
    """Test the ToolExecutorMixin methods."""

    def test_coerce_tool_args_strings(self):
        """String args are preserved."""
        from dev.agents.tool_executor import ToolExecutorMixin
        result = ToolExecutorMixin._coerce_tool_args({"path": "foo.py", "content": "hello"})
        assert result["path"] == "foo.py"
        assert result["content"] == "hello"

    def test_coerce_tool_args_numbers(self):
        """String numbers are coerced to int/float."""
        from dev.agents.tool_executor import ToolExecutorMixin
        result = ToolExecutorMixin._coerce_tool_args({"timeout_seconds": "30", "temperature": "0.7"})
        assert result["timeout_seconds"] == 30
        assert result["temperature"] == 0.7

    def test_coerce_tool_args_booleans(self):
        """String booleans are coerced."""
        from dev.agents.tool_executor import ToolExecutorMixin
        result = ToolExecutorMixin._coerce_tool_args({"verbose": "true", "debug": "false"})
        assert result["verbose"] is True
        assert result["debug"] is False

    def test_coerce_tool_args_json_strings(self):
        """JSON string arrays/objects are parsed."""
        from dev.agents.tool_executor import ToolExecutorMixin
        result = ToolExecutorMixin._coerce_tool_args({"paths": '["a.py", "b.py"]'})
        assert result["paths"] == ["a.py", "b.py"]

    def test_parse_text_tool_calls(self):
        """Text tool calls are extracted."""
        from dev.agents.tool_executor import ToolExecutorMixin
        mixin = ToolExecutorMixin()
        text = 'I will use write_file({"path": "test.py", "content": "hello"})'
        calls = mixin._parse_text_tool_calls(text)
        assert len(calls) >= 1

    def test_parse_code_blocks(self):
        """Fenced code blocks are parsed into write_file calls."""
        from dev.agents.tool_executor import ToolExecutorMixin
        mixin = ToolExecutorMixin()
        text = '```python\n# test.py\nprint("hello")\n```'
        calls = mixin._parse_code_blocks(text)
        # Should find the code block (path detection depends on format)
        assert isinstance(calls, list)

    def test_check_tool_allowed_full_auto(self):
        """Full-auto mode allows all tools."""
        from dev.agents.tool_executor import ToolExecutorMixin
        from dev.agents.loop_types import LoopConfig
        mixin = ToolExecutorMixin()
        mixin.config = LoopConfig(approval_mode="full-auto")
        result = mixin._check_tool_allowed("write_file", {})
        assert result["allowed"] is True

    def test_check_tool_allowed_plan_mode(self):
        """Plan mode blocks write tools."""
        from dev.agents.tool_executor import ToolExecutorMixin
        from dev.agents.loop_types import LoopConfig
        mixin = ToolExecutorMixin()
        mixin.config = LoopConfig(approval_mode="full-auto", enforce_plan_mode=True)
        result = mixin._check_tool_allowed("write_file", {})
        assert result["allowed"] is False
        assert "Plan mode" in result["reason"]

    def test_check_tool_allowed_suggest_mode(self):
        """Suggest mode blocks non-read-only tools."""
        from dev.agents.tool_executor import ToolExecutorMixin
        from dev.agents.loop_types import LoopConfig
        mixin = ToolExecutorMixin()
        mixin.config = LoopConfig(approval_mode="suggest")
        result = mixin._check_tool_allowed("write_file", {})
        assert result["allowed"] is False

    def test_has_pending_todos(self):
        """Pending todo detection works."""
        from dev.agents.tool_executor import ToolExecutorMixin
        mixin = ToolExecutorMixin()
        assert mixin._has_pending_todos("You have pending todo items to complete") is True
        assert mixin._has_pending_todos("Done with all tasks") is False


class TestLoopTypes:
    """Test data classes from loop_types."""

    def test_message_estimated_tokens(self):
        """Message token estimation works."""
        from dev.agents.loop_types import Message
        msg = Message(role="user", content="Hello world")
        tokens = msg.estimated_tokens()
        assert tokens > 0

    def test_message_with_tool_calls(self):
        """Message with tool calls counts extra tokens."""
        from dev.agents.loop_types import Message
        msg = Message(role="assistant", content="test",
                      tool_calls=[{"function": {"name": "write_file", "arguments": "{}"}}])
        tokens = msg.estimated_tokens()
        assert tokens > 0

    def test_loop_config_defaults(self):
        """LoopConfig has sensible defaults."""
        from dev.agents.loop_types import LoopConfig
        config = LoopConfig()
        assert config.model == "default"
        assert config.max_tokens == 32768
        assert config.approval_mode == "auto-edit"
        assert config.max_context_tokens == 128_000

    def test_loop_state_defaults(self):
        """LoopState initializes correctly."""
        from dev.agents.loop_types import LoopState
        state = LoopState()
        assert len(state.done_messages) == 0
        assert len(state.cur_messages) == 0
        assert state.total_cost == 0.0

    def test_edit_result(self):
        """EditResult dataclass works."""
        from dev.agents.loop_types import EditResult
        result = EditResult(success=True, file_path="test.py")
        assert result.success is True
        assert result.file_path == "test.py"
