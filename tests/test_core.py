"""
Core tests for Dev.

Tests for:
- Provider initialization
- Agent definitions
- Tool execution
- Config loading
- Error handling
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_import():
    """Test that all modules can be imported."""
    from dev import __version__
    assert __version__ == "1.0.0"
    print("✓ Module import")


def test_agent_definitions():
    """Test agent definitions."""
    from dev.agents.agent_definition import (
        get_agent, list_agents, get_coder_agent,
        get_researcher_agent, get_reviewer_agent, get_planner_agent,
    )
    
    # Test list agents
    agents = list_agents()
    assert len(agents) >= 5
    assert "coder" in agents
    assert "researcher" in agents
    assert "reviewer" in agents
    assert "planner" in agents
    print(f"✓ Agent definitions ({len(agents)} agents)")
    
    # Test get agent
    coder = get_coder_agent()
    assert coder.id == "coder"
    assert "read_files" in coder.tool_names
    assert "write_file" in coder.tool_names
    print("✓ Agent definitions - coder")
    
    researcher = get_researcher_agent()
    assert researcher.id == "researcher"
    assert "web_search" in researcher.tool_names
    print("✓ Agent definitions - researcher")


def test_tool_registry():
    """Test tool registry."""
    from dev.agents.runtime import ToolRegistry
    from dev.tools.base import Tool
    
    registry = ToolRegistry()
    
    # Register a test tool
    class TestTool(Tool):
        name = "test_tool"
        description = "Test tool"
        parameters = {"type": "object", "properties": {}}
        
        async def execute(self, input_data, state, project_path):
            return {"success": True}
    
    tool = TestTool()
    registry.register("test_tool", tool)
    
    assert registry.get("test_tool") is tool
    assert "test_tool" in registry.list_tools()
    print("✓ Tool registry")


def test_config_loading():
    """Test configuration loading."""
    from dev.config.settings import DevConfig, ProviderConfig
    
    # Test default config
    config = DevConfig()
    assert config.provider.type == "nvidia_nims"
    assert config.agent.max_steps == 50
    assert config.sandbox.mode == "default"
    print("✓ Config - default")
    
    # Test config from dict
    config = DevConfig()
    config._apply_dict({
        "provider": {"model": "test-model"},
        "agent": {"max_steps": 100},
    })
    assert config.provider.model == "test-model"
    assert config.agent.max_steps == 100
    print("✓ Config - apply dict")


def test_error_handling():
    """Test error handling system."""
    from dev.utils.errors import (
        ErrorHandler, DevError, ToolExecutionError,
        TokenLimitError, RateLimitError, ErrorSeverity,
    )
    
    handler = ErrorHandler()
    
    # Test basic error
    error = DevError("test error")
    result = handler.handle(error)
    assert result["type"] == "DevError"
    assert "test error" in result["message"]
    print("✓ Error handling - basic")
    
    # Test tool error
    error = ToolExecutionError("test_tool", "something went wrong")
    result = handler.handle(error)
    assert result["tool"] == "test_tool"
    print("✓ Error handling - tool error")
    
    # Test token limit error
    error = TokenLimitError(50000, 40000)
    result = handler.handle(error)
    assert result["recoverable"] == True
    print("✓ Error handling - token limit")


def test_repo_map():
    """Test repo map generation."""
    from dev.utils.repo_map import RepoMap
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        test_file = os.path.join(tmpdir, "test.py")
        with open(test_file, "w") as f:
            f.write("def hello():\n    pass\n\ndef world():\n    pass\n")
        
        mapper = RepoMap(root=tmpdir, max_map_tokens=1024)
        repo_map = mapper.get_repo_map()
        
        assert isinstance(repo_map, str)
        print("✓ Repo map generation")


def test_context_pruner():
    """Test context pruning."""
    from dev.utils.context_pruner import ContextPruner, estimate_tokens
    
    # Test token estimation
    tokens = estimate_tokens("hello world")
    assert tokens > 0
    print("✓ Context pruner - token estimation")
    
    # Test pruning
    pruner = ContextPruner(max_tokens=1000)
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello " * 1000},
        {"role": "assistant", "content": "Hi there!"},
    ]
    
    stats = pruner.get_context_stats(messages)
    assert "current_tokens" in stats
    print("✓ Context pruner - stats")


def test_budget_manager():
    """Test budget management."""
    from dev.utils.budget import BudgetManager, BudgetConfig
    
    config = BudgetConfig(max_tokens_per_session=10000)
    manager = BudgetManager(config)
    
    # Record usage
    manager.record_usage(100, 50, "test-model")
    
    stats = manager.get_stats()
    assert stats["tokens_in"] == 100
    assert stats["tokens_out"] == 50
    assert stats["request_count"] == 1
    print("✓ Budget manager")


def test_free_apis():
    """Test free API registry."""
    from dev.apis.free_apis import get_free_apis, search_apis, get_categories
    
    # Get all APIs
    apis = get_free_apis()
    assert len(apis) >= 20
    print(f"✓ Free APIs ({len(apis)} APIs)")
    
    # Search APIs
    results = search_apis("json")
    assert len(results) > 0
    print("✓ Free APIs - search")
    
    # Get categories
    cats = get_categories()
    assert "development" in cats
    print(f"✓ Free APIs - categories ({len(cats)} categories)")


def test_mcp_registry():
    """Test MCP server registry."""
    from dev.mcp.registry import get_free_mcps, search_mcps, get_mcp_categories
    
    # Get all MCPs
    mcps = get_free_mcps()
    assert len(mcps) >= 10
    print(f"✓ MCP registry ({len(mcps)} servers)")
    
    # Search MCPs
    results = search_mcps("database")
    assert len(results) > 0
    print("✓ MCP registry - search")


def test_skills():
    """Test skills system."""
    from dev.skills.loader import SkillLoader, BUILTIN_SKILLS
    
    # Test built-in skills
    assert len(BUILTIN_SKILLS) >= 5
    assert "python" in BUILTIN_SKILLS
    assert "javascript" in BUILTIN_SKILLS
    print(f"✓ Skills ({len(BUILTIN_SKILLS)} built-in)")
    
    # Test loader
    loader = SkillLoader()
    skills = loader.list_skills()
    assert len(skills) >= 5
    print("✓ Skills - loader")


def test_sandbox():
    """Test sandbox system."""
    from dev.sandbox.exec_policy import (
        ExecPolicy, create_default_policy, create_strict_policy,
        CommandRule, Decision,
    )
    
    # Test default policy
    policy = create_default_policy()
    match = policy.evaluate_command("ls")
    assert match.decision == Decision.ALLOW
    print("✓ Sandbox - default policy")
    
    # Test strict policy - dangerous commands need approval
    policy = create_strict_policy()
    match = policy.evaluate_command("rm -rf /")
    assert match.decision in (Decision.FORBIDDEN, Decision.PROMPT)
    print("✓ Sandbox - strict policy")


def test_workflow_builder():
    """Test workflow builder."""
    from dev.agents.workflow import WorkflowBuilder, WorkflowOrchestrator
    
    builder = WorkflowBuilder("test-workflow")
    step1 = builder.add_step("coder", "Write the code")
    step2 = builder.add_step("reviewer", "Review the code", depends_on=[step1])
    
    workflow = builder.build()
    assert len(workflow.steps) == 2
    assert workflow.steps[1].depends_on == [step1]
    print("✓ Workflow builder")


def test_team():
    """Test team system."""
    from dev.agents.team import Team, TeamRole
    
    # Create a mock runtime
    class MockRuntime:
        async def run_agent(self, **kwargs):
            return {"output": {"content": "done"}}
    
    team = Team("test-team")
    team.add_agent("leader", TeamRole.LEADER, ["planning"])
    team.add_agent("coder", TeamRole.SPECIALIST, ["python", "typescript"])
    
    leader = team.get_leader()
    assert leader is not None
    assert leader.agent_id == "leader"
    
    specialists = team.get_specialists()
    assert len(specialists) == 1
    print("✓ Team system")


def test_patch_tools():
    """Test patch tools."""
    from dev.tools.patch_tools import ApplyPatchTool, EditBlockTool
    
    # Test apply_patch tool exists
    tool = ApplyPatchTool()
    assert tool.name == "apply_patch"
    print("✓ Patch tools - apply_patch")
    
    # Test edit_block tool exists
    tool = EditBlockTool()
    assert tool.name == "edit_block"
    print("✓ Patch tools - edit_block")


def test_quality_checker():
    """Test quality checker."""
    from dev.utils.quality import QualityChecker
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a Python file
        test_file = os.path.join(tmpdir, "test.py")
        with open(test_file, "w") as f:
            f.write("def hello():\n    pass\n")
        
        checker = QualityChecker(tmpdir)
        result = asyncio.run(
            checker.lint_file("test.py")
        )
        assert result is not None
        print("✓ Quality checker")


if __name__ == "__main__":
    tests = [
        test_import,
        test_agent_definitions,
        test_tool_registry,
        test_config_loading,
        test_error_handling,
        test_repo_map,
        test_context_pruner,
        test_budget_manager,
        test_free_apis,
        test_mcp_registry,
        test_skills,
        test_sandbox,
        test_workflow_builder,
        test_team,
        test_patch_tools,
        test_quality_checker,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")
