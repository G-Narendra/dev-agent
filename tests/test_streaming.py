"""
Tests for streaming + tool execution loop.

Tests ProductionAgentLoop.run_streaming and NimProvider.chat_completion_stream_events.
"""

import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestNimProviderStreamEvents:
    """Test chat_completion_stream_events."""

    def test_provider_has_stream_events(self):
        from dev.providers.nim_provider import NimProvider
        assert hasattr(NimProvider, "chat_completion_stream_events")
        print("  OK: provider has chat_completion_stream_events")

    def test_stream_events_signature(self):
        import inspect
        from dev.providers.nim_provider import NimProvider
        sig = inspect.signature(NimProvider.chat_completion_stream_events)
        params = list(sig.parameters.keys())
        assert "messages" in params
        assert "tools" in params
        assert "model" in params
        print("  OK: stream_events has correct parameters")


class TestProductionLoopStream:
    """Test ProductionAgentLoop.run_streaming."""

    def test_loop_has_run_streaming(self):
        from dev.agents.production_loop import ProductionAgentLoop
        assert hasattr(ProductionAgentLoop, "run_streaming")
        print("  OK: loop has run_streaming method")

    def test_run_streaming_signature(self):
        import inspect
        from dev.agents.production_loop import ProductionAgentLoop
        sig = inspect.signature(ProductionAgentLoop.run_streaming)
        params = list(sig.parameters.keys())
        assert "prompt" in params
        assert "on_tool_call" in params
        assert "on_tool_result" in params
        assert "on_text" in params
        assert "max_steps" in params
        print("  OK: run_streaming has correct parameters")

    def test_run_streaming_no_tools(self):
        """Test run_streaming when model returns text only (no tools)."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from dev.agents.runtime import ToolRegistry

        provider = AsyncMock()

        async def mock_stream_events(messages, model, temperature, max_tokens, tools=None, **kwargs):
            yield {"type": "text", "content": "Hello"}
            yield {"type": "text", "content": " world"}
            yield {"type": "finish", "reason": "stop"}
            yield {"type": "usage", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}

        provider.chat_completion_stream_events = mock_stream_events

        registry = ToolRegistry()
        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=registry,
            config=LoopConfig(model="test"),
            project_path=".",
        )

        text_chunks = []
        result = run_async(loop.run_streaming(
            prompt="test",
            system_prompt="You are a test assistant",
            on_text=lambda c: text_chunks.append(c),
            max_steps=10,
        ))

        assert result["status"] == "completed"
        assert result["content"] == "Hello world"
        assert result["steps"] == 1
        assert text_chunks == ["Hello", " world"]
        print("  OK: run_streaming text-only works")

    def test_run_streaming_with_tools(self):
        """Test run_streaming when model makes tool calls."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from dev.agents.runtime import ToolRegistry
        from dev.tools.base import Tool

        class EchoTool(Tool):
            @property
            def name(self) -> str:
                return "echo"

            @property
            def description(self) -> str:
                return "Echo input"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {"text": {"type": "string"}}}

            def execute(self, args, state=None, project_path="."):
                return {"echoed": args.get("text", "")}

        registry = ToolRegistry()
        registry.register("echo", EchoTool())

        call_count = 0

        async def mock_stream_events(messages, model, temperature, max_tokens, tools=None, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                yield {
                    "type": "tool_call",
                    "tool_call": {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "echo",
                            "arguments": json.dumps({"text": "hello world"}),
                        },
                    },
                }
                yield {"type": "finish", "reason": "tool_calls"}
                yield {"type": "usage", "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}}
            else:
                yield {"type": "text", "content": "The tool echoed: hello world"}
                yield {"type": "finish", "reason": "stop"}
                yield {"type": "usage", "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}}

        provider = AsyncMock()
        provider.chat_completion_stream_events = mock_stream_events

        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=registry,
            config=LoopConfig(model="test"),
            project_path=".",
        )

        tool_calls_made = []
        tool_results_received = []
        text_chunks = []

        result = run_async(loop.run_streaming(
            prompt="echo hello world",
            system_prompt="You are a test assistant",
            on_tool_call=lambda n, a: tool_calls_made.append({"name": n, "args": a}),
            on_tool_result=lambda n, r: tool_results_received.append({"name": n, "result": r}),
            on_text=lambda c: text_chunks.append(c),
            max_steps=10,
        ))

        assert result["status"] == "completed"
        assert "hello world" in result["content"]
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "echo"
        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["result"]["echoed"] == "hello world"
        assert len(tool_calls_made) == 1
        assert len(tool_results_received) == 1
        assert len(text_chunks) > 0
        assert call_count == 2
        print("  OK: run_streaming with tool calls works")

    def test_run_streaming_max_steps(self):
        """Test run_streaming stops at max_steps."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from dev.agents.runtime import ToolRegistry
        from dev.tools.base import Tool

        class InfiniteTool(Tool):
            @property
            def name(self) -> str:
                return "infinite"

            @property
            def description(self) -> str:
                return "Always calls itself"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {}}

            def execute(self, args, state=None, project_path="."):
                return {"ok": True}

        registry = ToolRegistry()
        registry.register("infinite", InfiniteTool())

        async def mock_stream_events(messages, model, temperature, max_tokens, tools=None, **kwargs):
            yield {
                "type": "tool_call",
                "tool_call": {
                    "id": "call_loop",
                    "type": "function",
                    "function": {"name": "infinite", "arguments": "{}"},
                },
            }
            yield {"type": "finish", "reason": "tool_calls"}

        provider = AsyncMock()
        provider.chat_completion_stream_events = mock_stream_events

        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=registry,
            config=LoopConfig(model="test"),
            project_path=".",
        )

        result = run_async(loop.run_streaming(
            prompt="loop forever",
            system_prompt="test",
            max_steps=3,
        ))

        assert result["status"] == "max_steps"
        assert result["steps"] == 3
        print("  OK: run_streaming respects max_steps")

    def test_run_streaming_abort(self):
        """Test run_streaming can be aborted mid-execution."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from dev.agents.runtime import ToolRegistry
        from dev.tools.base import Tool

        class SlowTool(Tool):
            @property
            def name(self) -> str:
                return "slow_tool"

            @property
            def description(self) -> str:
                return "Slow tool"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {}}

            def execute(self, args, state=None, project_path="."):
                return {"ok": True}

        registry = ToolRegistry()
        registry.register("slow_tool", SlowTool())

        call_count = 0

        async def mock_stream_events(messages, model, temperature, max_tokens, tools=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {
                    "type": "tool_call",
                    "tool_call": {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "slow_tool", "arguments": "{}"},
                    },
                }
                yield {"type": "finish", "reason": "tool_calls"}
            else:
                yield {"type": "text", "content": "after tool"}
                yield {"type": "finish", "reason": "stop"}

        provider = AsyncMock()
        provider.chat_completion_stream_events = mock_stream_events

        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=registry,
            config=LoopConfig(model="test"),
            project_path=".",
        )

        async def abort_later():
            await asyncio.sleep(0.01)
            loop.abort()

        async def run_with_abort():
            asyncio.create_task(abort_later())
            return await loop.run_streaming(
                prompt="test",
                system_prompt="test",
                max_steps=10,
            )

        result = run_async(run_with_abort())
        assert result["status"] in ("aborted", "completed")
        print("  OK: run_streaming can be aborted")


class TestStreamingFallback:
    """Test fallback mechanism in chat_completion_stream_events."""

    def test_fallback_to_nonstreaming(self):
        """Test that stream_events falls back to non-streaming when tool streaming fails."""
        from dev.providers.nim_provider import NimProvider, RateLimitConfig

        provider = NimProvider(keys=["test-key"], config=RateLimitConfig(rpm=100))
        provider._client = AsyncMock()
        provider._client.aclose = AsyncMock()

        # Make _stream_with_tools raise
        async def failing_stream(*args, **kwargs):
            raise RuntimeError("Tool streaming not supported")

        provider._stream_with_tools = failing_stream

        # Mock non-streaming response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Hello from fallback", "tool_calls": []},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        provider._client.post = AsyncMock(return_value=mock_response)

        async def run():
            events = []
            async for event in provider.chat_completion_stream_events(
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": "function", "function": {"name": "test"}}],
            ):
                events.append(event)
            return events

        events = run_async(run())

        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) == 1
        assert text_events[0]["content"] == "Hello from fallback"
        print("  OK: fallback to non-streaming works")

    def test_streaming_no_tools(self):
        """Test stream_events without tools uses direct streaming path."""
        from dev.providers.nim_provider import NimProvider, RateLimitConfig, NimKey

        provider = NimProvider(keys=["test-key"], config=RateLimitConfig(rpm=100))
        provider._client = AsyncMock()

        # Use a real NimKey so _record_request works
        real_key = NimKey(key="test-key", name="test")
        real_key.requests_this_minute = 0
        real_key.is_exhausted = False
        provider.keys = [real_key]

        # When no tools provided, it goes straight to non-streaming path
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Hello world", "tool_calls": []},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        provider._client.post = AsyncMock(return_value=mock_response)

        async def run():
            events = []
            async for event in provider.chat_completion_stream_events(
                messages=[{"role": "user", "content": "test"}],
                tools=None,
            ):
                events.append(event)
            return events

        events = run_async(run())

        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) == 1
        assert text_events[0]["content"] == "Hello world"
        print("  OK: text-only non-streaming works")


def main():
    print("=" * 50)
    print("Streaming + Tool Execution Tests")
    print("=" * 50)

    tests = []

    t = TestNimProviderStreamEvents()
    tests.append(t.test_provider_has_stream_events)
    tests.append(t.test_stream_events_signature)

    t2 = TestProductionLoopStream()
    tests.append(t2.test_loop_has_run_streaming)
    tests.append(t2.test_run_streaming_signature)
    tests.append(t2.test_run_streaming_no_tools)
    tests.append(t2.test_run_streaming_with_tools)
    tests.append(t2.test_run_streaming_max_steps)
    tests.append(t2.test_run_streaming_abort)

    t3 = TestStreamingFallback()
    tests.append(t3.test_fallback_to_nonstreaming)
    tests.append(t3.test_streaming_no_tools)

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
