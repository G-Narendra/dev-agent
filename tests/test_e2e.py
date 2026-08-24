"""
End-to-end tests for Dev agent.
Tests that the agent can actually create files and execute tools.
"""
import asyncio
import json
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestToolSearch:
    """Test the ToolSearch meta-tool."""

    def test_tool_search_imports(self):
        from dev.tools.tool_search import ToolSearchTool, _build_catalog
        tool = ToolSearchTool()
        assert tool.name == "tool_search"

    def test_tool_search_catalog(self):
        from dev.tools.tool_search import _build_catalog
        catalog = _build_catalog()
        assert len(catalog) > 30, f"Expected 30+ tools in catalog, got {len(catalog)}"
        # Check some expected tools exist
        names = [t["name"] for t in catalog]
        assert "write_file" in names
        assert "read_files" in names
        assert "run_terminal_command" in names
        assert "web_search" in names

    def test_tool_search_find_write(self):
        from dev.tools.tool_search import ToolSearchTool, _build_catalog
        _build_catalog()  # Ensure catalog is built
        tool = ToolSearchTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute({"query": "write"})
        )
        assert result["matches"] > 0
        tool_names = [t["name"] for t in result["tools"]]
        assert "write_file" in tool_names

    def test_tool_search_find_pdf(self):
        from dev.tools.tool_search import ToolSearchTool, _build_catalog
        _build_catalog()
        tool = ToolSearchTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute({"query": "pdf"})
        )
        assert result["matches"] > 0

    def test_tool_search_no_results_shows_all(self):
        from dev.tools.tool_search import ToolSearchTool, _build_catalog
        _build_catalog()
        tool = ToolSearchTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute({"query": "xyznonexistent"})
        )
        assert result["matches"] == 0
        assert "all_tools" in result


class TestAgentDefinition:
    """Test agent definitions are correct."""

    def test_coder_agent_has_tool_search(self):
        from dev.agents.agent_definition import get_agent
        agent = get_agent("coder")
        assert "tool_search" in agent.tool_names
        assert "write_file" in agent.tool_names
        assert "read_files" in agent.tool_names

    def test_coder_agent_system_prompt_mentions_tools(self):
        from dev.agents.agent_definition import get_agent
        agent = get_agent("coder")
        prompt = agent.system_prompt.lower()
        assert "write_file" in prompt
        assert "tool" in prompt
        assert "create" in prompt

    def test_all_agents_exist(self):
        from dev.agents.agent_definition import list_agents
        agents = list_agents()
        assert "coder" in agents
        assert "researcher" in agents
        assert "reviewer" in agents


class TestProductionLoop:
    """Test production loop core functionality."""

    def test_loop_config_defaults(self):
        from dev.agents.production_loop import LoopConfig
        config = LoopConfig()
        assert config.max_context_tokens == 128_000
        assert config.approval_mode == "auto-edit"
        assert config.auto_lint is True
        assert config.auto_commit is True

    def test_message_estimated_tokens(self):
        from dev.agents.production_loop import Message
        msg = Message(role="user", content="Hello world " * 100)
        tokens = msg.estimated_tokens()
        assert tokens > 0
        assert tokens < 1000  # Should be reasonable

    def test_parse_code_blocks(self):
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from dev.providers.nim_provider import NimProvider, RateLimitConfig
        from dev.agents.runtime import ToolRegistry

        provider = NimProvider(keys=["test"], config=RateLimitConfig(rpm=100))
        registry = ToolRegistry()
        loop = ProductionAgentLoop(provider=registry, tool_registry=registry, config=LoopConfig())

        # Test markdown code block parsing
        text = """
Here is the file:

```filename: portfolio/index.html
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body><h1>Hello</h1></body>
</html>
```
"""
        calls = loop._parse_code_blocks(text)
        assert len(calls) >= 1
        assert calls[0]["function"]["name"] == "write_file"
        args = json.loads(calls[0]["function"]["arguments"])
        assert "portfolio/index.html" in args["path"]

    def test_has_pending_todos(self):
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig, LoopState, Message
        from dev.agents.runtime import ToolRegistry

        registry = ToolRegistry()
        loop = ProductionAgentLoop(provider=None, tool_registry=registry, config=LoopConfig())

        # Add a write_todos result with incomplete items
        todos_data = json.dumps({
            "todos": [
                {"task": "Create file 1", "completed": True},
                {"task": "Create file 2", "completed": False},
            ],
            "display": "...",
            "completed_count": 1,
            "total_count": 2,
        })
        loop._state.cur_messages.append(
            Message(role="tool", name="write_todos", content=todos_data)
        )

        assert loop._has_pending_todos("response") is True

    def test_has_pending_todos_all_done(self):
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig, Message
        from dev.agents.runtime import ToolRegistry

        registry = ToolRegistry()
        loop = ProductionAgentLoop(provider=None, tool_registry=registry, config=LoopConfig())

        todos_data = json.dumps({
            "todos": [
                {"task": "Create file 1", "completed": True},
                {"task": "Create file 2", "completed": True},
            ],
            "display": "...",
            "completed_count": 2,
            "total_count": 2,
        })
        loop._state.cur_messages.append(
            Message(role="tool", name="write_todos", content=todos_data)
        )

        assert loop._has_pending_todos("response") is False


class TestNimProvider:
    """Test NIM provider configuration."""

    def test_models_exist(self):
        from dev.providers.nim_provider import NimProvider
        assert "coding" in NimProvider.MODELS
        assert "fast" in NimProvider.MODELS
        assert "vision" in NimProvider.MODELS

    def test_model_resolution(self):
        from dev.providers.nim_provider import NimProvider
        provider = NimProvider(keys=["test"])
        resolved = provider._resolve_model("default", has_tools=True)
        assert "llama" in resolved.lower() or "nemotron" in resolved.lower()


class TestFreeApis:
    """Test free API registry."""

    def test_has_apis(self):
        from dev.apis.free_apis import get_free_apis
        apis = get_free_apis()
        assert len(apis) > 100

    def test_has_categories(self):
        from dev.apis.free_apis import get_categories
        cats = get_categories()
        assert len(cats) > 20


class TestMcpRegistry:
    """Test MCP server registry."""

    def test_has_mcps(self):
        from dev.mcp.registry import get_free_mcps
        mcps = get_free_mcps()
        assert len(mcps) > 40


class TestSkills:
    """Test skills integration."""

    def test_skill_integration_loads(self):
        from dev.agents.skill_integration import SkillIntegration
        si = SkillIntegration()
        roles = si.get_all_roles()
        assert len(roles) > 100, f"Expected 100+ roles, got {len(roles)}"

    def test_skill_prompt_generation(self):
        from dev.agents.skill_integration import SkillIntegration
        si = SkillIntegration()
        prompt = si.build_skill_prompt("build a web application")
        assert len(prompt) > 100


class TestFileOperations:
    """Test actual file operations in a temp directory."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_write_and_read_file(self):
        from dev.tools.real_tools import RealWriteFileTool, RealReadFilesTool

        write_tool = RealWriteFileTool()
        read_tool = RealReadFilesTool()

        # Write a file
        result = asyncio.get_event_loop().run_until_complete(
            write_tool.execute(
                {"path": os.path.join(self.test_dir, "test.txt"), "content": "Hello, Dev!"},
                None,
                self.test_dir,
            )
        )
        assert "error" not in result

        # Read it back
        result = asyncio.get_event_loop().run_until_complete(
            read_tool.execute(
                {"paths": [{"path": os.path.join(self.test_dir, "test.txt")}]},
                None,
                self.test_dir,
            )
        )
        assert "Hello, Dev!" in str(result)

    def test_str_replace(self):
        from dev.tools.real_tools import RealWriteFileTool, RealStrReplaceTool

        write_tool = RealWriteFileTool()
        replace_tool = RealStrReplaceTool()
        test_file = os.path.join(self.test_dir, "replace.txt")

        # Write initial content
        asyncio.get_event_loop().run_until_complete(
            write_tool.execute(
                {"path": test_file, "content": "Hello World"},
                None,
                self.test_dir,
            )
        )

        # Replace
        result = asyncio.get_event_loop().run_until_complete(
            replace_tool.execute(
                {"path": test_file, "replacements": [{"oldString": "World", "newString": "Dev", "allowMultiple": False}]},
                None,
                self.test_dir,
            )
        )
        assert "error" not in result

        # Verify
        with open(test_file) as f:
            assert f.read() == "Hello Dev"

    def test_run_terminal_command(self):
        from dev.tools.real_tools import RealRunTerminalCommand

        tool = RealRunTerminalCommand()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(
                {"command": "echo hello"},
                None,
                self.test_dir,
            )
        )
        assert "hello" in str(result).lower()

    def test_glob(self):
        from dev.tools.real_tools import RealGlobTool

        # Create some files
        for name in ["a.py", "b.py", "c.txt"]:
            with open(os.path.join(self.test_dir, name), "w") as f:
                f.write("test")

        tool = RealGlobTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(
                {"pattern": "*.py", "cwd": self.test_dir},
                None,
                self.test_dir,
            )
        )
        assert "a.py" in str(result)
        assert "b.py" in str(result)
        assert "c.txt" not in str(result)
