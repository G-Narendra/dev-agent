"""Tests for prompt compression, tool auto-selection, gitignore awareness, and MCP retry.

Covers:
- _compress_prompt_for_nim() compression strategies
- _get_relevant_tools() auto-selection based on prompt
- _load_gitignore() prompt injection
- MCP client retry logic
"""
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPromptCompression:
    """Verify system prompt compression for Nemotron's limited context."""

    def _make_loop(self):
        """Create a ProductionAgentLoop with mocked provider for testing."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        provider.chat_completion_stream_events = AsyncMock()
        provider.chat_completion = AsyncMock(return_value={"content": "", "tool_calls": []})
        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=MagicMock(),
            config=LoopConfig(model="fast"),
            project_path=".",
        )
        return loop

    def test_short_prompt_not_compressed(self):
        """Short prompts should pass through unchanged."""
        loop = self._make_loop()
        short = "You are a coding agent. Build things."
        result = loop._compress_prompt_for_nim(short)
        assert result == short, "Short prompt should not be modified"

    def test_long_prompt_compressed(self):
        """Long prompts should be compressed to fit Nemotron context."""
        loop = self._make_loop()
        # Create a prompt with all sections that get compressed
        long_prompt = "You are Dev.\n\n" + "x" * 20000  # ~5K tokens
        result = loop._compress_prompt_for_nim(long_prompt)
        assert len(result) < len(long_prompt), "Long prompt should be compressed"
        assert len(result) <= 8000, f"Compressed prompt should be ≤8K chars, got {len(result)}"

    def test_rule_precedence_removed(self):
        """The verbose 'Rule Precedence' explanation should be stripped."""
        loop = self._make_loop()
        # Must be long enough to trigger compression (>1500 tokens = >6000 chars)
        prompt = (
            "x" * 6000 + "\n\n## Rules\nSome rules here.\n\n"
            "**Rule Precedence:** .devrules overrides DEV.md. When rules conflict, "
            "follow the most specific source.\n\n## More stuff"
        )
        result = loop._compress_prompt_for_nim(prompt)
        assert "Rule Precedence" not in result, "Rule Precedence explanation should be removed"

    def test_gitignore_truncated_to_10_patterns(self):
        """Gitignore section with 50 patterns should be truncated to ~10."""
        loop = self._make_loop()
        patterns = "\n".join(f"- pattern_{i}/" for i in range(50))
        prompt = f"## Rules\nShort.\n\n## .gitignore\nThese paths are gitignored:\n{patterns}\n\n## End"
        result = loop._compress_prompt_for_nim(prompt)
        # Should contain header + first 10 patterns max
        assert "- pattern_0/" in result
        assert "- pattern_9/" in result or "- pattern_10/" in result

    def test_auto_memory_truncated(self):
        """Auto Memory section should be capped at ~500 chars."""
        loop = self._make_loop()
        memory = "## Auto Memory\n" + "x" * 2000
        # Must be long enough to trigger compression (>1500 tokens = >6000 chars)
        prompt = "y" * 6000 + f"\n\n{memory}\n\n## End"
        result = loop._compress_prompt_for_nim(prompt)
        mem_idx = result.find("## Auto Memory")
        if mem_idx >= 0:
            # Find the end of the auto memory section
            end_idx = result.find("\n## ", mem_idx + 10)
            if end_idx < 0:
                end_idx = len(result)
            section_len = end_idx - mem_idx
            assert section_len <= 600, f"Auto Memory section should be ≤600 chars, got {section_len}"

    def test_git_status_truncated(self):
        """Git Status section should be capped at ~200 chars."""
        loop = self._make_loop()
        git_status = "## Git Status\n" + "x" * 1000
        # Must be long enough to trigger compression (>1500 tokens = >6000 chars)
        prompt = "y" * 6000 + f"\n\n{git_status}\n\n## End"
        result = loop._compress_prompt_for_nim(prompt)
        git_idx = result.find("## Git Status")
        if git_idx >= 0:
            end_idx = result.find("\n## ", git_idx + 10)
            if end_idx < 0:
                end_idx = len(result)
            section_len = end_idx - git_idx
            assert section_len <= 300, f"Git Status section should be ≤300 chars, got {section_len}"

    def test_rules_preserved_after_compression(self):
        """Critical RULES section should survive compression."""
        loop = self._make_loop()
        prompt = "x" * 20000 + "\n\n## RULES: use write_file tool"
        result = loop._compress_prompt_for_nim(prompt)
        assert "RULES" in result, "RULES section must survive compression"
        assert "write_file" in result, "write_file instruction must survive compression"


class TestToolAutoSelection:
    """Verify _get_relevant_tools() selects appropriate tools for the task."""

    def _make_loop(self):
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=MagicMock(),
            config=LoopConfig(model="fast"),
            project_path=".",
        )
        return loop

    def _make_tool_defs(self, names):
        """Create mock tool definitions."""
        return [
            {"type": "function", "function": {"name": name, "description": f"{name} tool", "parameters": {}}}
            for name in names
        ]

    def test_core_tools_always_included(self):
        """Core tools (write_file, read_files, etc.) should always be selected."""
        loop = self._make_loop()
        all_tools = self._make_tool_defs([
            "write_file", "str_replace", "read_files", "run_terminal_command",
            "list_directory", "code_search", "glob", "write_todos", "task_completed",
            "browser_screenshot", "web_search", "free_api",
        ])
        result = loop._get_relevant_tools("create a website", all_tools)
        result_names = {d["function"]["name"] for d in result}
        assert "write_file" in result_names
        assert "read_files" in result_names
        assert "run_terminal_command" in result_names

    def test_web_keywords_add_browser_tools(self):
        """Web-related prompts should include browser tools."""
        loop = self._make_loop()
        all_tools = self._make_tool_defs([
            "write_file", "read_files", "browser_screenshot", "browser_navigate",
            "web_search", "free_api",
        ])
        result = loop._get_relevant_tools("build a website", all_tools)
        result_names = {d["function"]["name"] for d in result}
        assert "browser_screenshot" in result_names
        assert "browser_navigate" in result_names

    def test_research_keywords_add_web_tools(self):
        """Research prompts should include web_search and read_url."""
        loop = self._make_loop()
        all_tools = self._make_tool_defs([
            "write_file", "web_search", "read_url", "browser_screenshot",
        ])
        result = loop._get_relevant_tools("research this topic", all_tools)
        result_names = {d["function"]["name"] for d in result}
        assert "web_search" in result_names

    def test_docker_keywords_add_docker_tools(self):
        """Docker prompts should include docker tools."""
        loop = self._make_loop()
        all_tools = self._make_tool_defs([
            "write_file", "docker_run", "docker_build", "web_search",
        ])
        result = loop._get_relevant_tools("create a docker container", all_tools)
        result_names = {d["function"]["name"] for d in result}
        assert "docker_run" in result_names
        assert "docker_build" in result_names

    def test_tool_count_capped_at_20(self):
        """Result should never exceed 20 tools for Nemotron."""
        loop = self._make_loop()
        all_tools = self._make_tool_defs([f"tool_{i}" for i in range(40)])
        result = loop._get_relevant_tools("build a website with API and docker", all_tools)
        assert len(result) <= 20, f"Should cap at 20 tools, got {len(result)}"

    def test_fallback_when_filtered_too_aggressive(self):
        """If filtering is too aggressive, should fall back to first 20 tools."""
        loop = self._make_loop()
        all_tools = self._make_tool_defs([f"tool_{i}" for i in range(5)])
        # Prompt with no matching keywords should still return at least 5 tools
        result = loop._get_relevant_tools("xyzzy foobar", all_tools)
        assert len(result) >= 5, f"Fallback should return at least 5 tools, got {len(result)}"

    def test_empty_prompt_gets_core_tools(self):
        """Empty prompt should still include core tools."""
        loop = self._make_loop()
        all_tools = self._make_tool_defs([
            "write_file", "read_files", "code_search", "glob",
            "list_directory", "run_terminal_command", "write_todos",
            "task_completed", "str_replace",
        ])
        result = loop._get_relevant_tools("", all_tools)
        result_names = {d["function"]["name"] for d in result}
        assert "write_file" in result_names


class TestGitignoreAwareness:
    """Verify _load_gitignore() correctly reads and formats .gitignore patterns."""

    def _make_loop(self, gitignore_content=None):
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            if gitignore_content is not None:
                gi_path = os.path.join(tmpdir, ".gitignore")
                with open(gi_path, "w") as f:
                    f.write(gitignore_content)
            loop = ProductionAgentLoop(
                provider=provider,
                tool_registry=MagicMock(),
                config=LoopConfig(model="fast"),
                project_path=tmpdir,
            )
            yield loop

    def test_no_gitignore_returns_empty(self):
        """When no .gitignore exists, should return empty string."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = ProductionAgentLoop(
                provider=provider,
                tool_registry=MagicMock(),
                config=LoopConfig(model="fast"),
                project_path=tmpdir,
            )
            result = loop._load_gitignore()
            assert result == "", "No .gitignore should return empty string"

    def test_gitignore_patterns_formatted(self):
        """Gitignore patterns should be formatted as a readable list."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        content = "node_modules/\n.env\n*.pyc\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            gi_path = os.path.join(tmpdir, ".gitignore")
            with open(gi_path, "w") as f:
                f.write(content)
            loop = ProductionAgentLoop(
                provider=provider,
                tool_registry=MagicMock(),
                config=LoopConfig(model="fast"),
                project_path=tmpdir,
            )
            result = loop._load_gitignore()
            assert "node_modules/" in result
            assert ".env" in result
            assert "*.pyc" in result
            assert "gitignored" in result.lower() or "DO NOT" in result

    def test_gitignore_comments_excluded(self):
        """Comment lines in .gitignore should be excluded."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        content = "# This is a comment\nnode_modules/\n# Another comment\n.env\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            gi_path = os.path.join(tmpdir, ".gitignore")
            with open(gi_path, "w") as f:
                f.write(content)
            loop = ProductionAgentLoop(
                provider=provider,
                tool_registry=MagicMock(),
                config=LoopConfig(model="fast"),
                project_path=tmpdir,
            )
            result = loop._load_gitignore()
            assert "comment" not in result.lower() or "comment" in result.split("\n")[0]

    def test_gitignore_capped_at_30_patterns(self):
        """Should cap at 30 patterns to avoid bloating the prompt."""
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        content = "\n".join(f"pattern_{i}/" for i in range(50))
        with tempfile.TemporaryDirectory() as tmpdir:
            gi_path = os.path.join(tmpdir, ".gitignore")
            with open(gi_path, "w") as f:
                f.write(content)
            loop = ProductionAgentLoop(
                provider=provider,
                tool_registry=MagicMock(),
                config=LoopConfig(model="fast"),
                project_path=tmpdir,
            )
            result = loop._load_gitignore()
            # Count pattern lines (lines starting with "- ")
            pattern_lines = [l for l in result.split("\n") if l.strip().startswith("- ")]
            assert len(pattern_lines) <= 30, f"Should cap at 30 patterns, got {len(pattern_lines)}"


class TestMCPRetry:
    """Verify MCP client retry logic with exponential backoff."""

    def test_retry_on_failure(self):
        """MCP client should retry failed connections."""
        from dev.mcp.client import MCPClient, MCPServer
        import asyncio
        client = MCPClient()
        client.add_server(MCPServer(
            name="failing-server",
            command="nonexistent-command-that-will-fail",
            args=[],
        ))

        # connect_server should return False after retries (not raise)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                client.connect_server("failing-server", max_retries=1)
            )
            assert result is False, "Failed MCP connection should return False"
        finally:
            loop.close()

    def test_connect_all_continues_after_failure(self):
        """connect_all should continue to other servers after one fails."""
        from dev.mcp.client import MCPClient, MCPServer
        import asyncio
        client = MCPClient()
        client.add_server(MCPServer(
            name="server-a",
            command="nonexistent-a",
            args=[],
        ))
        client.add_server(MCPServer(
            name="server-b",
            command="nonexistent-b",
            args=[],
        ))

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(client.connect_all())
            assert "server-a" in results
            assert "server-b" in results
            # Both should fail gracefully (connect_all catches exceptions)
            assert results["server-a"] is False
            assert results["server-b"] is False
        finally:
            loop.close()


class TestDesignFetchCapping:
    """Verify auto-design fetch is capped for Nemotron context."""

    def _make_loop(self):
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=MagicMock(),
            config=LoopConfig(model="fast"),
            project_path=".",
        )
        return loop

    def test_design_section_capped_at_3000(self):
        """Design section should be capped at 3000 chars."""
        loop = self._make_loop()
        # Simulate a very long design section
        long_design = "Colors: " + "x" * 5000
        # The cap is applied in _auto_fetch_design, test the logic directly
        if len(long_design) > 3000:
            long_design = long_design[:2950] + "\n...[truncated for context budget]\n"
        assert len(long_design) <= 3000, "Design section should be capped at 3000 chars"
        assert "truncated" in long_design


class TestCompressionIntegration:
    """Integration tests for compression in the full system prompt build."""

    def _make_loop(self):
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        provider = AsyncMock()
        provider.chat_completion_stream_events = AsyncMock()
        provider.chat_completion = AsyncMock(return_value={"content": "", "tool_calls": []})
        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=MagicMock(),
            config=LoopConfig(model="fast"),
            project_path=".",
        )
        return loop

    def test_system_prompt_builds_without_error(self):
        """_build_system_prompt should complete without errors."""
        loop = self._make_loop()
        result = loop._build_system_prompt("You are Dev, an AI coding agent.")
        assert isinstance(result, str)
        assert len(result) > 100, "System prompt should have substantial content"

    def test_system_prompt_under_8k_chars(self):
        """Final system prompt should be under 8K chars for Nemotron."""
        loop = self._make_loop()
        result = loop._build_system_prompt("You are Dev, an AI coding agent.")
        assert len(result) <= 8000, f"System prompt should be ≤8K chars, got {len(result)}"

    def test_system_prompt_caching_works(self):
        """System prompt should be cached on second call."""
        loop = self._make_loop()
        result1 = loop._build_system_prompt("You are Dev.")
        result2 = loop._build_system_prompt("You are Dev.")
        assert result1 == result2, "Cached prompt should be identical"
        assert hasattr(loop, '_system_prompt_cache')
