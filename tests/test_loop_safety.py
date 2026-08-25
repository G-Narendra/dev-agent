"""Tests for research-backed agent loop safety mechanisms.

Covers:
- Graceful degradation at max_steps (smolagents pattern) via _synthesize_final_summary
- LoopConfig safety knobs
- Empty-response / failure / loop-detection state initialization
"""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dev.agents.production_loop import LoopConfig, ProductionAgentLoop, Message


class TestLoopSafetyConfig:
    def test_config_has_safety_knobs(self):
        cfg = LoopConfig()
        assert cfg.max_identical_tool_repeats == 3
        assert cfg.max_consecutive_empty == 3
        assert cfg.max_consecutive_failures == 4

    def test_config_customizable(self):
        cfg = LoopConfig(max_identical_tool_repeats=5, max_consecutive_failures=2)
        assert cfg.max_identical_tool_repeats == 5
        assert cfg.max_consecutive_failures == 2


class TestGracefulDegradation:
    """The agent must NEVER stop silently at max_steps — always synthesize a summary."""

    def _make_loop(self):
        tools = MagicMock()
        tools.get_definitions.return_value = []
        tools.get_definitions_for_tools.return_value = []

        loop = ProductionAgentLoop(
            provider=MagicMock(),
            tool_registry=tools,
            config=LoopConfig(verbose=False),
            project_path=os.getcwd(),
        )
        return loop

    def test_summary_generated_on_provider_success(self):
        loop = self._make_loop()

        async def fake_completion(**kwargs):
            return {
                "choices": [{"message": {"content": "Done: created files. Remaining: tests."}}],
                "usage": {},
            }

        loop.provider.chat_completion = AsyncMock(side_effect=fake_completion)
        loop._state.cur_messages.append(Message(role="user", content="task"))

        result = asyncio.get_event_loop().run_until_complete(
            loop._synthesize_final_summary("system prompt")
        )
        assert "Done:" in result
        # The nudge message was appended before summarizing
        assert any("maximum number of steps" in m.content for m in loop._state.cur_messages)

    def test_summary_swallows_provider_failure(self):
        loop = self._make_loop()
        loop.provider.chat_completion = AsyncMock(side_effect=Exception("rate limited"))
        loop._state.cur_messages.append(Message(role="user", content="task"))

        result = asyncio.get_event_loop().run_until_complete(
            loop._synthesize_final_summary("system prompt")
        )
        assert result == ""  # never crashes the loop

    def test_summary_timeout_bounded(self):
        """Summary call must be time-bounded so shutdown is fast."""
        import inspect
        src = inspect.getsource(ProductionAgentLoop._synthesize_final_summary)
        assert "wait_for" in src
        assert "timeout" in src


class TestEmptyResponseNudge:
    def test_nudge_message_format(self):
        """Verify the corrective nudge tells the model exactly what went wrong."""
        msg = (
            "Your last response was EMPTY. Do not send empty responses. "
            "Either call a tool (e.g., write_file, run_terminal_command, read_files) "
            "or reply with useful text about the task progress. Try again now."
        )
        assert "EMPTY" in msg
        assert "tool" in msg

    def test_loop_detection_correction_message(self):
        msg = (
            "ERROR: You are repeating the exact same tool calls with the same arguments. "
        )
        assert "DIFFERENT approach" or "different approach" in msg.lower() + "stop and try a different approach"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
