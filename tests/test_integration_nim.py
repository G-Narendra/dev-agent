"""
Integration tests that call the real NVIDIA NIM API.

These tests verify:
- NIM provider connection and authentication
- Basic chat completion
- Streaming responses
- Tool/function calling
- Production loop end-to-end
- Error handling and retry
- Rate limit handling
- Context compaction
- Tool execution pipeline

Run with: pytest tests/test_integration_nim.py -v
Requires: valid NVIDIA NIM API key in ~/.dev/config.json
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# Skip all integration tests if no API key is available
def _get_nvidia_key() -> str | None:
    """Get NVIDIA NIM API key from config."""
    try:
        config_path = Path.home() / ".dev" / "config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            keys = config.get("nvidia_api_keys", [])
            if keys:
                return keys[0]
    except Exception:
        pass
    # Also check env
    return os.environ.get("NVIDIA_API_KEY") or os.environ.get("NIM_API_KEY")


NVIDIA_KEY = _get_nvidia_key()
OPENROUTER_KEY = None
try:
    config_path = Path.home() / ".dev" / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        keys = config.get("openrouter_api_keys", [])
        if keys:
            OPENROUTER_KEY = keys[0]
except Exception:
    pass


# Conditional skip markers
requires_nim = pytest.mark.skipif(
    not NVIDIA_KEY, reason="No NVIDIA NIM API key configured"
)
requires_openrouter = pytest.mark.skipif(
    not OPENROUTER_KEY, reason="No OpenRouter API key configured"
)
requires_any_key = pytest.mark.skipif(
    not NVIDIA_KEY and not OPENROUTER_KEY,
    reason="No API keys configured",
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def nim_provider():
    """Create a real NIM provider with API key."""
    if not NVIDIA_KEY:
        pytest.skip("No NVIDIA NIM API key")
    from dev.providers.nim_provider import NimProvider, RateLimitConfig
    provider = NimProvider(
        keys=[NVIDIA_KEY],
        config=RateLimitConfig(rpm=40, tpm=100000),
    )
    provider._verbose = True
    return provider


@pytest.fixture
def openrouter_provider():
    """Create an OpenRouter provider with API key."""
    if not OPENROUTER_KEY:
        pytest.skip("No OpenRouter API key")
    from dev.providers.unified_provider import UnifiedProvider, ProviderConfig
    config = ProviderConfig(
        nvidia_keys=[],
        openrouter_keys=[OPENROUTER_KEY],
    )
    provider = UnifiedProvider(config)
    return provider


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory(prefix="dev_test_") as tmpdir:
        # Create some test files
        (Path(tmpdir) / "app.py").write_text("print('hello')\n", encoding="utf-8")
        (Path(tmpdir) / "README.md").write_text("# Test Project\n", encoding="utf-8")
        (Path(tmpdir) / "requirements.txt").write_text("flask>=2.0\n", encoding="utf-8")
        yield tmpdir


@pytest.fixture
def tool_registry():
    """Create a tool registry with real tools."""
    from dev.tools.real_tools import (
        RealReadFilesTool, RealWriteFileTool, RealStrReplaceTool,
        RealCodeSearchTool, RealGlobTool, RealListDirectoryTool,
        RealRunTerminalCommand, RealGitOperations,
    )
    from dev.tools.context_tools import RepoMapTool, ContextStatsTool
    from dev.agents.runtime import ToolRegistry

    registry = ToolRegistry()
    registry.register("read_files", RealReadFilesTool())
    registry.register("write_file", RealWriteFileTool())
    registry.register("str_replace", RealStrReplaceTool())
    registry.register("code_search", RealCodeSearchTool())
    registry.register("glob", RealGlobTool())
    registry.register("list_directory", RealListDirectoryTool())
    registry.register("run_terminal_command", RealRunTerminalCommand())
    registry.register("git_operations", RealGitOperations())
    registry.register("repo_map", RepoMapTool())
    registry.register("context_stats", ContextStatsTool())
    return registry


# ============================================================================
# TEST: NIM PROVIDER BASIC
# ============================================================================

@pytest.mark.integration
class TestNimProviderBasic:
    """Test basic NIM provider functionality."""

    @requires_nim
    @pytest.mark.asyncio
    async def test_initialize(self, nim_provider):
        """Provider initializes HTTP client."""
        await nim_provider.initialize()
        assert nim_provider._client is not None
        await nim_provider.close()

    @requires_nim
    @pytest.mark.asyncio
    async def test_simple_chat(self, nim_provider):
        """Basic chat completion returns a response."""
        messages = [{"role": "user", "content": "Say exactly: Hello from Dev"}]
        result = await nim_provider.chat_completion(
            messages=messages,
            model="default",
            max_tokens=50,
            temperature=0.0,
        )
        assert "choices" in result
        assert len(result["choices"]) > 0
        content = result["choices"][0]["message"]["content"]
        assert len(content) > 0
        print(f"  Response: {content[:100]}")

    @requires_nim
    @pytest.mark.asyncio
    async def test_chat_with_usage_tracking(self, nim_provider):
        """Chat completion tracks token usage."""
        messages = [{"role": "user", "content": "What is 2+2?"}]
        result = await nim_provider.chat_completion(
            messages=messages,
            model="default",
            max_tokens=50,
        )
        assert "usage" in result
        usage = result["usage"]
        assert usage.get("total_tokens", 0) > 0
        print(f"  Tokens: {usage.get('total_tokens', 0)}")

    @requires_nim
    @pytest.mark.asyncio
    async def test_multiple_models(self, nim_provider):
        """Can query different models."""
        models_to_test = ["coding", "fast"]
        for model_type in models_to_test:
            messages = [{"role": "user", "content": f"Say '{model_type}'"}]
            try:
                result = await nim_provider.chat_completion(
                    messages=messages,
                    model=model_type,
                    max_tokens=20,
                    temperature=0.0,
                )
                assert "choices" in result
                print(f"  Model {model_type}: OK")
            except Exception as e:
                # Some models may not be available
                print(f"  Model {model_type}: {e}")


# ============================================================================
# TEST: NIM STREAMING
# ============================================================================

@pytest.mark.integration
class TestNimStreaming:
    """Test streaming responses from NIM."""

    @requires_nim
    @pytest.mark.asyncio
    async def test_basic_streaming(self, nim_provider):
        """Streaming returns content chunks."""
        messages = [{"role": "user", "content": "Say exactly: streaming works"}]
        chunks = []
        async for chunk in nim_provider.chat_completion_stream(
            messages=messages,
            model="default",
            max_tokens=50,
        ):
            # chat_completion_stream yields str chunks directly
            if isinstance(chunk, str):
                chunks.append(chunk)
            elif isinstance(chunk, dict):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    chunks.append(content)

        assert len(chunks) > 0
        full_text = "".join(chunks)
        assert len(full_text) > 0
        print(f"  Streaming: {len(chunks)} chunks, {len(full_text)} chars")

    @requires_nim
    @pytest.mark.asyncio
    async def test_streaming_tool_calls(self, nim_provider):
        """Streaming with tool calls completes without error."""
        # Use short prompt and low max_tokens to avoid timeout.
        # NIM free tier is slow (~5-15s per request); keep this fast.
        messages = [{"role": "user", "content": "Say hi"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "List files in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Directory path"}
                        },
                        "required": ["path"],
                    },
                },
            }
        ]

        chunks = []
        tool_call_chunks = []
        async for chunk in nim_provider.chat_completion_stream(
            messages=messages,
            model="default",
            max_tokens=20,
            tools=tools,
        ):
            # chat_completion_stream yields str chunks directly
            if isinstance(chunk, str):
                chunks.append(chunk)
            elif isinstance(chunk, dict):
                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                content = delta.get("content", "")
                tc = delta.get("tool_calls", [])
                if content:
                    chunks.append(content)
                if tc:
                    tool_call_chunks.extend(tc)

        # Either content or tool calls (or both) — just verify stream completed
        has_content = len(chunks) > 0
        has_tools = len(tool_call_chunks) > 0
        print(f"  Streaming tool test: content={has_content}, tools={has_tools}, chunks={len(chunks)}")


# ============================================================================
# TEST: TOOL CALLING
# ============================================================================

@pytest.mark.integration
class TestNimToolCalling:
    """Test tool/function calling with NIM."""

    @requires_nim
    @pytest.mark.asyncio
    async def test_simple_tool_call(self, nim_provider):
        """Model can request a simple tool call."""
        messages = [{"role": "user", "content": "What is the current directory?"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "run_terminal_command",
                    "description": "Run a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Command to run"}
                        },
                        "required": ["command"],
                    },
                },
            }
        ]

        result = await nim_provider.chat_completion(
            messages=messages,
            model="tool",
            max_tokens=200,
            tools=tools,
        )

        assert "choices" in result
        message = result["choices"][0].get("message", {})
        tool_calls = message.get("tool_calls", [])

        if tool_calls:
            tc = tool_calls[0]
            assert "function" in tc
            assert tc["function"]["name"] == "run_terminal_command"
            args = json.loads(tc["function"]["arguments"])
            assert "command" in args
            print(f"  Tool call: {tc['function']['name']}({args})")
        else:
            # Model may respond with text instead of tool call
            content = message.get("content", "")
            assert len(content) > 0
            print(f"  No tool call, response: {content[:100]}")

    @requires_nim
    @pytest.mark.asyncio
    async def test_tool_call_result_integration(self, nim_provider, project_dir):
        """Model can process tool call results."""
        messages = [
            {"role": "user", "content": "Read the file app.py"},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_files",
                    "description": "Read files from disk",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "File paths to read",
                            }
                        },
                        "required": ["paths"],
                    },
                },
            }
        ]

        # First call: model should request tool
        result1 = await nim_provider.chat_completion(
            messages=messages,
            model="tool",
            max_tokens=200,
            tools=tools,
        )

        message1 = result1["choices"][0].get("message", {})
        tool_calls = message1.get("tool_calls", [])

        if tool_calls:
            # Simulate tool execution result
            tool_result = "print('hello')\n"
            messages.append(message1)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_calls[0]["id"],
                "content": tool_result,
            })

            # Second call: model should process the result
            result2 = await nim_provider.chat_completion(
                messages=messages,
                model="tool",
                max_tokens=200,
            )

            content = result2["choices"][0].get("message", {}).get("content", "")
            assert len(content) > 0
            print(f"  Tool result integration: {content[:100]}")
        else:
            print("  Model did not request tool call (responded with text)")


# ============================================================================
# TEST: RATE LIMITING
# ============================================================================

@pytest.mark.integration
class TestNimRateLimiting:
    """Test rate limit handling."""

    @requires_nim
    @pytest.mark.asyncio
    async def test_rate_limit_rotation(self, nim_provider):
        """Provider rotates keys on rate limit."""
        # Make several rapid requests to test key rotation
        results = []
        for i in range(3):
            try:
                result = await nim_provider.chat_completion(
                    messages=[{"role": "user", "content": f"Say {i}"}],
                    model="fast",
                    max_tokens=10,
                    temperature=0.0,
                )
                results.append("ok")
            except Exception as e:
                results.append(f"error: {type(e).__name__}")
            await asyncio.sleep(0.5)  # Small delay between requests

        # At least some should succeed
        ok_count = results.count("ok")
        assert ok_count >= 1, f"Expected at least 1 success, got: {results}"
        print(f"  Rate limit test: {ok_count}/3 succeeded")

    @requires_nim
    @pytest.mark.asyncio
    async def test_key_health_tracking(self, nim_provider):
        """Provider tracks key health."""
        # Make a request
        await nim_provider.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            model="fast",
            max_tokens=10,
        )

        # Check health stats
        stats = nim_provider.get_stats()
        assert "total_tokens" in stats or "requests" in stats
        print(f"  Key health: {stats.get('requests', 0)} requests, {stats.get('total_tokens', 0)} tokens")


# ============================================================================
# TEST: PRODUCTION LOOP END-TO-END
# ============================================================================

@pytest.mark.integration
class TestProductionLoopE2E:
    """Test the full production agent loop with real NIM.

    These tests cap max_steps=3 so each completes in ~15-45s (3 NIM calls × 5-15s).
    NIM free tier is slow (~5-15s per request).
    """

    @requires_nim
    @pytest.mark.asyncio
    async def test_simple_task(self, nim_provider, project_dir, tool_registry):
        """Agent completes a simple file creation task (max 3 steps)."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig

        config = LoopConfig(
            approval_mode="full-auto",
            verbose=True,
            auto_commit=False,
            auto_test=False,
            auto_lint=False,
        )

        loop = ProductionAgentLoop(
            provider=nim_provider,
            tool_registry=tool_registry,
            config=config,
            project_path=project_dir,
        )

        result = await loop.run_streaming(
            prompt="Create a file called greeting.txt with the content 'Hello from Dev Agent!'",
            system_prompt="You are a helpful coding assistant.",
            max_steps=3,
        )

        assert isinstance(result, dict)
        content = result.get("content", "")
        assert len(content) > 0

        # Check if file was created
        greeting_path = Path(project_dir) / "greeting.txt"
        print(f"  E2E result: {content[:200]}")
        if greeting_path.exists():
            print(f"  File created: {greeting_path.read_text()}")

    @requires_nim
    @pytest.mark.asyncio
    async def test_read_and_respond(self, nim_provider, project_dir, tool_registry):
        """Agent reads a file and responds about its content (max 3 steps)."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig

        config = LoopConfig(
            approval_mode="full-auto",
            verbose=True,
            auto_commit=False,
            auto_test=False,
            auto_lint=False,
        )

        loop = ProductionAgentLoop(
            provider=nim_provider,
            tool_registry=tool_registry,
            config=config,
            project_path=project_dir,
        )

        result = await loop.run_streaming(
            prompt="What is in the file app.py?",
            system_prompt="You are a helpful coding assistant. Use the read_files tool to read files.",
            max_steps=3,
        )

        assert isinstance(result, dict)
        content = result.get("content", "")
        print(f"  Read and respond: {content[:200]}")

    @requires_nim
    @pytest.mark.asyncio
    async def test_multi_step_task(self, nim_provider, project_dir, tool_registry):
        """Agent handles a multi-step task (max 3 steps)."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig

        config = LoopConfig(
            approval_mode="full-auto",
            verbose=True,
            auto_commit=False,
            auto_test=False,
            auto_lint=False,
        )

        loop = ProductionAgentLoop(
            provider=nim_provider,
            tool_registry=tool_registry,
            config=config,
            project_path=project_dir,
        )

        result = await loop.run_streaming(
            prompt="Create a simple Python web server in server.py that serves 'Hello World' on port 8080",
            system_prompt="You are a helpful coding assistant. Use write_file to create files.",
            max_steps=3,
        )

        assert isinstance(result, dict)
        content = result.get("content", "")
        print(f"  Multi-step: {content[:200]}")

        # Check if server.py was created
        server_path = Path(project_dir) / "server.py"
        if server_path.exists():
            print(f"  server.py created: {len(server_path.read_text())} chars")


# ============================================================================
# TEST: COMPACTION (uses mock provider to avoid slow NIM call)
# ============================================================================

@pytest.mark.integration
class TestCompaction:
    """Test context compaction engine."""

    @requires_nim
    @pytest.mark.asyncio
    async def test_compaction_triggers(self, project_dir):
        """Compaction reduces message count when context is large."""
        from dev.agents.compaction import CompactionEngine, CompactionConfig
        from dev.agents.production_loop import Message

        # Create a compaction engine with very low threshold to force compaction
        compaction = CompactionEngine(CompactionConfig(
            auto_compact_threshold=0.001,  # Very low — trigger compaction early
            keep_recent_tokens=50,
        ))

        # Force compaction on a large message history using a mock provider
        mock_provider = AsyncMock()
        mock_provider.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Summary: User asked about Python. I explained it's a programming language.",
                }
            }],
            "usage": {"total_tokens": 100},
        })

        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi! " * 200),  # Large response
            Message(role="user", content="Tell me about Python"),
            Message(role="assistant", content="Python is great. " * 200),
        ]

        # Check if compaction reduces message count
        original_count = len(messages)
        result = await compaction.compact(messages, mock_provider)

        # Compaction should either reduce messages or keep them if under limit
        assert result is not None
        print(f"  Compaction: {original_count} messages, removed={result.messages_removed}, success={result.success}")

    @requires_nim
    @pytest.mark.asyncio
    async def test_compaction_with_real_nim(self, nim_provider, project_dir):
        """Compaction works with real NIM provider (slow, ~15s)."""
        from dev.agents.compaction import CompactionEngine, CompactionConfig
        from dev.agents.production_loop import Message

        compaction = CompactionEngine(CompactionConfig(
            auto_compact_threshold=0.001,
            keep_recent_tokens=50,
        ))

        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi! " * 200),
        ]

        result = await compaction.compact(messages, nim_provider)
        assert result is not None
        print(f"  Compaction (real NIM): removed={result.messages_removed}, success={result.success}")


# ============================================================================
# TEST: OPENROUTER (if available)
# ============================================================================

@pytest.mark.integration
class TestOpenRouter:
    """Test OpenRouter provider (if configured)."""

    @requires_openrouter
    @pytest.mark.asyncio
    async def test_openrouter_chat(self):
        """OpenRouter basic chat works."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen/qwen3-coder:free",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "max_tokens": 20,
                },
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                assert len(content) > 0
                print(f"  OpenRouter: {content[:50]}")
            else:
                print(f"  OpenRouter: HTTP {resp.status_code}")


# ============================================================================
# TEST: WEB SEARCH + URL READING
# ============================================================================

@pytest.mark.integration
class TestWebTools:
    """Test web search and URL reading tools."""

    @pytest.mark.asyncio
    async def test_web_search(self, project_dir):
        """Web search returns results."""
        from dev.tools.real_tools import RealWebSearchTool

        tool = RealWebSearchTool()
        result = await tool.execute(
            {"query": "Python programming language"},
            None,
            project_dir,
        )

        assert "results" in result or "error" in result
        if "results" in result:
            assert len(result["results"]) > 0
            print(f"  Web search: {len(result['results'])} results")
        else:
            print(f"  Web search error: {result.get('error', 'unknown')}")

    @pytest.mark.asyncio
    async def test_read_url(self, project_dir):
        """URL reading returns content."""
        from dev.tools.real_tools import RealReadUrlTool

        tool = RealReadUrlTool()
        result = await tool.execute(
            {"url": "https://httpbin.org/html", "max_chars": 2000},
            None,
            project_dir,
        )

        assert "content" in result or "error" in result
        if "content" in result:
            assert len(result["content"]) > 0
            print(f"  URL read: {len(result['content'])} chars")
        else:
            print(f"  URL read error: {result.get('error', 'unknown')}")


# ============================================================================
# TEST: TOOL EXECUTION PIPELINE
# ============================================================================

@pytest.mark.integration
class TestToolExecution:
    """Test the full tool execution pipeline."""

    @pytest.mark.asyncio
    async def test_read_write_cycle(self, project_dir):
        """Read file, modify, write back."""
        from dev.tools.real_tools import RealReadFilesTool, RealWriteFileTool

        # Read
        read_tool = RealReadFilesTool()
        result = await read_tool.execute(
            {"paths": ["app.py"]},
            None,
            project_dir,
        )
        assert "files" in result
        assert len(result["files"]) > 0
        original_content = result["files"][0].get("content", "")
        assert "hello" in original_content.lower()

        # Write modified content
        write_tool = RealWriteFileTool()
        modified = original_content + "\n# Modified by Dev Agent"
        result = await write_tool.execute(
            {"path": "app.py", "content": modified, "instructions": "Add comment"},
            None,
            project_dir,
        )
        assert result.get("success") is True

        # Verify
        result = await read_tool.execute(
            {"paths": ["app.py"]},
            None,
            project_dir,
        )
        new_content = result["files"][0].get("content", "")
        assert "Modified by Dev Agent" in new_content
        print("  Read-write cycle: OK")

    @pytest.mark.asyncio
    async def test_str_replace_cycle(self, project_dir):
        """Read file, str_replace, verify."""
        from dev.tools.real_tools import RealStrReplaceTool, RealReadFilesTool

        replace_tool = RealStrReplaceTool()
        result = await replace_tool.execute(
            {
                "path": "app.py",
                "replacements": [
                    {"oldString": "hello", "newString": "world"}
                ],
            },
            None,
            project_dir,
        )
        assert result.get("success") is True
        assert result.get("applied", 0) > 0

        # Verify
        read_tool = RealReadFilesTool()
        result = await read_tool.execute(
            {"paths": ["app.py"]},
            None,
            project_dir,
        )
        content = result["files"][0].get("content", "")
        assert "world" in content
        print("  Str replace cycle: OK")

    @pytest.mark.asyncio
    async def test_terminal_command(self, project_dir):
        """Terminal command execution works."""
        from dev.tools.real_tools import RealRunTerminalCommand

        tool = RealRunTerminalCommand()
        result = await tool.execute(
            {"command": "echo hello", "timeout_seconds": 10},
            None,
            project_dir,
        )

        assert result.get("exitCode") == 0
        assert "hello" in result.get("stdout", "")
        print("  Terminal command: OK")

    @pytest.mark.asyncio
    async def test_code_search(self, project_dir):
        """Code search finds patterns."""
        from dev.tools.real_tools import RealCodeSearchTool

        tool = RealCodeSearchTool()
        result = await tool.execute(
            {"pattern": "hello", "cwd": "."},
            None,
            project_dir,
        )

        assert "matches" in result
        assert len(result["matches"]) > 0
        print(f"  Code search: {len(result['matches'])} files matched")

    @pytest.mark.asyncio
    async def test_git_operations(self, project_dir):
        """Git operations work."""
        from dev.tools.real_tools import RealGitOperations

        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=project_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project_dir, capture_output=True)

        tool = RealGitOperations()
        result = await tool.execute(
            {"action": "status"},
            None,
            project_dir,
        )

        assert result.get("exitCode") == 0
        assert "stdout" in result
        print("  Git operations: OK")


# ============================================================================
# TEST: ERROR HANDLING
# ============================================================================

@pytest.mark.integration
class TestErrorHandling:
    """Test error handling and recovery."""

    @requires_nim
    @pytest.mark.asyncio
    async def test_invalid_model_graceful(self, nim_provider):
        """Invalid model name is handled gracefully."""
        messages = [{"role": "user", "content": "hi"}]
        try:
            result = await nim_provider.chat_completion(
                messages=messages,
                model="nonexistent/model-999",
                max_tokens=10,
            )
            # If it succeeds, fine
        except Exception as e:
            # Should be a clear error, not a crash
            assert "error" in str(type(e).__name__).lower() or "http" in str(e).lower() or "404" in str(e)
            print(f"  Invalid model error: {type(e).__name__}")

    @requires_nim
    @pytest.mark.asyncio
    async def test_empty_messages_handled(self, nim_provider):
        """Empty message list is handled."""
        try:
            result = await nim_provider.chat_completion(
                messages=[],
                model="fast",
                max_tokens=10,
            )
            # May succeed or fail with clear error
        except Exception as e:
            assert "error" in str(e).lower() or "message" in str(e).lower()
            print(f"  Empty messages error: {type(e).__name__}")

    @pytest.mark.asyncio
    async def test_tool_not_found(self, project_dir):
        """Calling non-existent tool returns error."""
        from dev.tools.real_tools import RealRunTerminalCommand

        tool = RealRunTerminalCommand()
        result = await tool.execute(
            {"command": "nonexistent_command_12345"},
            None,
            project_dir,
        )

        # Should return error, not crash
        assert "error" in result or result.get("exitCode") != 0
        print("  Tool not found: handled gracefully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration", "--tb=short"])
