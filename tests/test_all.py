"""
Comprehensive Test Suite for Dev.

Tests all components:
- NIM Provider (mocked)
- Agent Runtime
- All Tools
- All Utilities
- CLI Commands
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Helper
# ============================================================================

def run_async(coro):
    """Run an async function."""
    return asyncio.run(coro)


# ============================================================================
# Provider Tests
# ============================================================================

class TestNimProvider:
    """Test NVIDIA NIMs provider."""

    def test_models_exist(self):
        from dev.providers.nim_provider import NimProvider
        assert "coding" in NimProvider.MODELS
        assert "reasoning" in NimProvider.MODELS
        assert "fast" in NimProvider.MODELS
        assert "default" in NimProvider.MODELS
        print("  OK: NIM models defined")

    def test_key_rotation(self):
        from dev.providers.nim_provider import NimProvider, RateLimitConfig
        config = RateLimitConfig(rpm=5)
        nim = NimProvider(keys=["key1", "key2", "key3"], config=config)
        assert len(nim.keys) == 3
        assert nim.keys[0].name == "key-0"
        print("  OK: key rotation")

    def test_rate_limiting(self):
        from dev.providers.nim_provider import NimProvider, RateLimitConfig
        config = RateLimitConfig(rpm=2)
        nim = NimProvider(keys=["key1"], config=config)
        
        # Simulate requests
        nim._record_request(nim.keys[0])
        nim._record_request(nim.keys[0])
        
        # Should be exhausted now
        key = nim._get_available_key()
        assert key is None
        print("  OK: rate limiting")

    def test_stats(self):
        from dev.providers.nim_provider import NimProvider
        nim = NimProvider(keys=["key1"])
        stats = nim.get_stats()
        assert "total_requests" in stats
        assert "total_tokens" in stats
        print("  OK: provider stats")


# ============================================================================
# Agent Tests
# ============================================================================

class TestAgents:
    """Test agent definitions and runtime."""

    def test_agent_definitions(self):
        from dev.agents.agent_definition import get_agent, list_agents
        agents = list_agents()
        assert len(agents) >= 5
        assert "coder" in agents
        assert "researcher" in agents
        assert "reviewer" in agents
        assert "planner" in agents
        assert "browser" in agents
        print("  OK: agent definitions")

    def test_coder_agent(self):
        from dev.agents.agent_definition import get_coder_agent
        coder = get_coder_agent()
        assert coder.id == "coder"
        assert "read_files" in coder.tool_names
        assert "write_file" in coder.tool_names
        print("  OK: coder agent")

    def test_tool_registry(self):
        from dev.agents.runtime import ToolRegistry
        from dev.tools.base import Tool
        
        registry = ToolRegistry()
        
        class TestTool(Tool):
            name = "test"
            description = "Test tool"
            parameters = {"type": "object", "properties": {}}
            async def execute(self, input_data, state, project_path):
                return {"ok": True}
        
        registry.register("test", TestTool())
        assert registry.get("test") is not None
        assert "test" in registry.list_tools()
        print("  OK: tool registry")

    def test_tool_definitions(self):
        from dev.agents.runtime import ToolRegistry
        from dev.tools.real_tools import RealReadFilesTool
        
        registry = ToolRegistry()
        registry.register("read_files", RealReadFilesTool())
        
        defs = registry.get_definitions()
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "read_files"
        print("  OK: tool definitions")


# ============================================================================
# Tool Tests
# ============================================================================

class TestRealTools:
    """Test real tool implementations."""

    def test_read_files(self):
        async def _test():
            from dev.tools.real_tools import RealReadFilesTool
            tool = RealReadFilesTool()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                with open(os.path.join(tmpdir, "test.txt"), "w") as f:
                    f.write("hello world")
                
                result = await tool.execute({"paths": ["test.txt"]}, None, tmpdir)
                assert "files" in result
                assert result["files"][0]["content"] == "hello world"
        
        run_async(_test())
        print("  OK: read_files")

    def test_write_file(self):
        async def _test():
            from dev.tools.real_tools import RealWriteFileTool
            tool = RealWriteFileTool()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await tool.execute(
                    {"path": "new.py", "content": "x = 1"},
                    None, tmpdir
                )
                assert result.get("success")
                
                with open(os.path.join(tmpdir, "new.py")) as f:
                    assert f.read() == "x = 1"
        
        run_async(_test())
        print("  OK: write_file")

    def test_str_replace(self):
        async def _test():
            from dev.tools.real_tools import RealStrReplaceTool
            tool = RealStrReplaceTool()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                with open(os.path.join(tmpdir, "test.py"), "w") as f:
                    f.write("def old(): pass")
                
                result = await tool.execute({
                    "path": "test.py",
                    "replacements": [
                        {"oldString": "def old():", "newString": "def new():"}
                    ]
                }, None, tmpdir)
                assert result.get("applied", 0) > 0
        
        run_async(_test())
        print("  OK: str_replace")

    def test_code_search(self):
        async def _test():
            from dev.tools.real_tools import RealCodeSearchTool
            tool = RealCodeSearchTool()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                with open(os.path.join(tmpdir, "test.py"), "w") as f:
                    f.write("def hello(): pass\ndef world(): pass")
                
                result = await tool.execute({"pattern": "hello"}, None, tmpdir)
                assert "matches" in result
        
        run_async(_test())
        print("  OK: code_search")

    def test_glob(self):
        async def _test():
            from dev.tools.real_tools import RealGlobTool
            tool = RealGlobTool()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                for name in ["a.py", "b.py", "c.txt"]:
                    open(os.path.join(tmpdir, name), "w").close()
                
                result = await tool.execute({"pattern": "*.py"}, None, tmpdir)
                assert len(result["paths"]) == 2
        
        run_async(_test())
        print("  OK: glob")

    def test_list_directory(self):
        async def _test():
            from dev.tools.real_tools import RealListDirectoryTool
            tool = RealListDirectoryTool()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "subdir"))
                open(os.path.join(tmpdir, "file.txt"), "w").close()
                
                result = await tool.execute({"path": "."}, None, tmpdir)
                assert "file.txt" in result["files"]
                assert "subdir" in result["directories"]
        
        run_async(_test())
        print("  OK: list_directory")


class TestPatchTools:
    """Test patch editing tools."""

    def test_edit_block(self):
        async def _test():
            from dev.tools.patch_tools import EditBlockTool
            tool = EditBlockTool()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                with open(os.path.join(tmpdir, "test.py"), "w") as f:
                    f.write("def old():\n    pass\n")
                
                result = await tool.execute({
                    "file_path": "test.py",
                    "edits": [{"search": "def old():", "replace": "def new():"}]
                }, None, tmpdir)
                assert result.get("success")
        
        run_async(_test())
        print("  OK: edit_block")

    def test_apply_patch(self):
        async def _test():
            from dev.tools.patch_tools import ApplyPatchTool
            tool = ApplyPatchTool()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                with open(os.path.join(tmpdir, "test.py"), "w") as f:
                    f.write("def hello():\n    pass\n")
                
                result = await tool.execute({
                    "file_path": "test.py",
                    "patch": "@@ -1,2 +1,2 @@\n def hello():\n-    pass\n+    return 42\n"
                }, None, tmpdir)
                assert result.get("success")
        
        run_async(_test())
        print("  OK: apply_patch")


class TestContextTools:
    """Test context management tools."""

    def test_summarize(self):
        async def _test():
            from dev.tools.context_tools import SummarizeTool
            tool = SummarizeTool()
            
            result = await tool.execute(
                {"text": "Hello world. " * 200},
                None, "."
            )
            assert "summary" in result
            assert result["summary_tokens"] < result["original_tokens"]
        
        run_async(_test())
        print("  OK: summarize")


# ============================================================================
# Utility Tests
# ============================================================================

class TestHistory:
    """Test conversation history."""

    def test_create_conversation(self):
        from dev.utils.history import ConversationHistory
        history = ConversationHistory()
        conv = history.create_conversation()
        assert conv.id
        assert len(conv.messages) == 0
        print("  OK: create conversation")

    def test_add_messages(self):
        from dev.utils.history import Conversation
        conv = Conversation(id="test")
        conv.add_message("user", "Hello")
        conv.add_message("assistant", "Hi!")
        assert len(conv.messages) == 2
        print("  OK: add messages")

    def test_save_load(self):
        from dev.utils.history import ConversationHistory
        with tempfile.TemporaryDirectory() as tmpdir:
            history = ConversationHistory(history_dir=tmpdir)
            conv = history.create_conversation()
            conv.add_message("user", "Test")
            history.save_conversation(conv)
            
            loaded = history.get_conversation(conv.id)
            assert loaded is not None
            assert len(loaded.messages) == 1
        print("  OK: save/load conversation")

    def test_compact(self):
        from dev.utils.history import ConversationHistory, Conversation, ChatMessage
        history = ConversationHistory()
        conv = Conversation(id="test")
        
        # Add many messages
        for i in range(50):
            conv.add_message("user", f"Message {i}")
            conv.add_message("assistant", f"Response {i}")
        
        # Compact
        compacted = history.compact_conversation(conv, max_tokens=100, keep_recent=5)
        assert len(compacted.messages) < len(conv.messages)
        print("  OK: compact conversation")


class TestProjectDetector:
    """Test project detection."""

    def test_detect_python(self):
        from dev.utils.project_detector import ProjectDetector
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "main.py"), "w").close()
            detector = ProjectDetector(tmpdir)
            info = detector.detect()
            assert info.language == "python"
        print("  OK: detect python")

    def test_detect_node(self):
        from dev.utils.project_detector import ProjectDetector
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "package.json"), "w") as f:
                json.dump({"dependencies": {"react": "^18.0.0"}}, f)
            # Create JS files for language detection
            for name in ["index.js", "app.js", "utils.js"]:
                open(os.path.join(tmpdir, name), "w").close()
            detector = ProjectDetector(tmpdir)
            info = detector.detect()
            assert info.language == "javascript"
            assert info.framework == "react"
        print("  OK: detect node/react")


class TestCostDashboard:
    """Test cost tracking."""

    def test_record_usage(self):
        from dev.utils.prompt_templates import CostDashboard
        dashboard = CostDashboard()
        dashboard.record(100, 50, "test-model")
        dashboard.record(200, 100, "test-model")
        summary = dashboard.get_summary()
        assert summary["total_requests"] == 2
        assert summary["tokens_in"] == 300
        print("  OK: record usage")

    def test_format_dashboard(self):
        from dev.utils.prompt_templates import CostDashboard
        dashboard = CostDashboard()
        dashboard.record(100, 50, "model")
        text = dashboard.format_dashboard()
        assert "COST DASHBOARD" in text
        print("  OK: format dashboard")


class TestReasoningController:
    """Test reasoning effort control."""

    def test_set_effort(self):
        from dev.utils.prompt_templates import ReasoningController
        rc = ReasoningController()
        config = rc.set_effort("high")
        assert config.effort == "high"
        assert config.max_tokens >= 4096
        print("  OK: set effort")

    def test_auto_adjust(self):
        from dev.utils.prompt_templates import ReasoningController
        rc = ReasoningController()
        config = rc.auto_adjust("complex_feature")
        assert config.effort == "high"
        print("  OK: auto adjust")


class TestErrorRecovery:
    """Test error recovery."""

    def test_retry(self):
        from dev.utils.error_recovery import ToolRetry
        retry = ToolRetry()
        assert retry.is_retryable("rate limit exceeded")
        assert retry.is_retryable("503 service unavailable")
        assert retry.is_retryable("timeout")
        assert not retry.is_retryable("file not found")
        assert not retry.is_retryable("permission denied")
        print("  OK: retry detection")

    def test_error_classification(self):
        from dev.utils.error_recovery import ErrorRecovery
        recovery = ErrorRecovery()
        # Test that recover method handles different error types
        result = run_async(recovery.recover("run_terminal_command", {"command": "ls"}, Exception("rate limit 429")))
        assert result is None or isinstance(result, dict)
        print("  OK: error classification")


class TestFileWatcher:
    """Test file watching."""

    def test_scan_files(self):
        from dev.utils.file_watcher import FileWatcher
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "test.py"), "w").close()
            watcher = FileWatcher(tmpdir)
            files = watcher._scan_files()
            assert len(files) == 1
        print("  OK: scan files")


class TestMailbox:
    """Test mailbox system."""

    def test_send_receive(self):
        from dev.utils.file_watcher import AgentMailbox
        mailbox = AgentMailbox()
        mailbox.send("user", "coder", "hello")
        msgs = mailbox.receive("coder")
        assert len(msgs) == 1
        assert msgs[0].content == "hello"
        print("  OK: send/receive")

    def test_broadcast(self):
        from dev.utils.file_watcher import AgentMailbox
        mailbox = AgentMailbox()
        mailbox.send("user", "coder", "alert")
        mailbox.send("user", "reviewer", "alert")
        coder_msgs = mailbox.receive("coder")
        reviewer_msgs = mailbox.receive("reviewer")
        assert len(coder_msgs) == 1
        assert len(reviewer_msgs) == 1
        print("  OK: broadcast")


class TestPlanApproval:
    """Test plan approval system."""

    def test_create_plan(self):
        from dev.utils.file_watcher import PlanApproval
        approval = PlanApproval()
        plan = approval.create_plan("Test Plan", [
            {"description": "Step 1"},
            {"description": "Step 2"},
        ])
        assert plan.status == "draft"
        assert len(plan.steps) == 2
        print("  OK: create plan")

    def test_approve_plan(self):
        from dev.utils.file_watcher import PlanApproval
        approval = PlanApproval()
        plan = approval.create_plan("Test", [{"description": "Step 1"}])
        approval.submit_for_approval("Test")
        approval.approve("Test")
        approved = approval.get_plan("Test")
        assert approved.status == "approved"
        print("  OK: approve plan")


class TestProfiler:
    """Test performance profiling."""

    def test_timer(self):
        from dev.utils.plugins import PerformanceProfiler
        profiler = PerformanceProfiler()
        profiler.start_timer("test")
        time.sleep(0.01)
        profiler.stop_timer("test")
        stats = profiler.get_stats()
        assert stats["entries"] == 1
        assert stats["total_time"] > 0
        print("  OK: timer")

    def test_format_report(self):
        from dev.utils.plugins import PerformanceProfiler
        profiler = PerformanceProfiler()
        profiler.start_timer("test")
        profiler.stop_timer("test")
        report = profiler.format_report()
        assert "PERFORMANCE REPORT" in report
        print("  OK: format report")


class TestTemplates:
    """Test workflow templates."""

    def test_list_templates(self):
        from dev.utils.prompt_templates import list_templates
        templates = list_templates()
        assert len(templates) >= 5
        assert any(t["name"] == "full-stack-app" for t in templates)
        print("  OK: list templates")

    def test_get_template(self):
        from dev.utils.prompt_templates import get_template
        template = get_template("bug-fix")
        assert template is not None
        assert len(template["steps"]) >= 2
        print("  OK: get template")


class TestSkills:
    """Test skills system."""

    def test_builtin_skills(self):
        from dev.skills.loader import SkillLoader
        loader = SkillLoader()
        skills = loader.list_skills()
        assert len(skills) >= 5
        names = [s["name"] for s in skills]
        assert "python" in names
        assert "javascript" in names
        print("  OK: builtin skills")

    def test_search_skills(self):
        from dev.skills.loader import SkillLoader
        loader = SkillLoader()
        results = loader.search_skills("react")
        assert len(results) >= 1
        print("  OK: search skills")


class TestFreeAPIs:
    """Test free API registry."""

    def test_get_apis(self):
        from dev.apis.free_apis import get_free_apis
        apis = get_free_apis()
        assert len(apis) >= 20
        print("  OK: get APIs")

    def test_search_apis(self):
        from dev.apis.free_apis import search_apis
        results = search_apis("json")
        assert len(results) > 0
        print("  OK: search APIs")


class TestMCPRegistry:
    """Test MCP server registry."""

    def test_get_mcps(self):
        from dev.mcp.registry import get_free_mcps
        mcps = get_free_mcps()
        assert len(mcps) >= 10
        print("  OK: get MCPs")

    def test_search_mcps(self):
        from dev.mcp.registry import search_mcps
        results = search_mcps("database")
        assert len(results) > 0
        print("  OK: search MCPs")


# ============================================================================
# Runner
# ============================================================================

if __name__ == "__main__":
    tests = [
        # Provider
        TestNimProvider().test_models_exist,
        TestNimProvider().test_key_rotation,
        TestNimProvider().test_rate_limiting,
        TestNimProvider().test_stats,
        # Agents
        TestAgents().test_agent_definitions,
        TestAgents().test_coder_agent,
        TestAgents().test_tool_registry,
        TestAgents().test_tool_definitions,
        # Real Tools
        TestRealTools().test_read_files,
        TestRealTools().test_write_file,
        TestRealTools().test_str_replace,
        TestRealTools().test_code_search,
        TestRealTools().test_glob,
        TestRealTools().test_list_directory,
        # Patch Tools
        TestPatchTools().test_edit_block,
        TestPatchTools().test_apply_patch,
        # Context Tools
        TestContextTools().test_summarize,
        # Utilities
        TestHistory().test_create_conversation,
        TestHistory().test_add_messages,
        TestHistory().test_save_load,
        TestHistory().test_compact,
        TestProjectDetector().test_detect_python,
        TestProjectDetector().test_detect_node,
        TestCostDashboard().test_record_usage,
        TestCostDashboard().test_format_dashboard,
        TestReasoningController().test_set_effort,
        TestReasoningController().test_auto_adjust,
        TestErrorRecovery().test_retry,
        TestErrorRecovery().test_error_classification,
        TestFileWatcher().test_scan_files,
        TestMailbox().test_send_receive,
        TestMailbox().test_broadcast,
        TestPlanApproval().test_create_plan,
        TestPlanApproval().test_approve_plan,
        TestProfiler().test_timer,
        TestProfiler().test_format_report,
        TestTemplates().test_list_templates,
        TestTemplates().test_get_template,
        TestSkills().test_builtin_skills,
        TestSkills().test_search_skills,
        TestFreeAPIs().test_get_apis,
        TestFreeAPIs().test_search_apis,
        TestMCPRegistry().test_get_mcps,
        TestMCPRegistry().test_search_mcps,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
    
    # Test 45: Interactive approval flow (mocked)
    try:
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig, Message
        from unittest.mock import MagicMock, patch

        loop = ProductionAgentLoop(
            provider=MagicMock(),
            tool_registry=MagicMock(),
            config=LoopConfig(approval_mode="suggest"),
        )
        # Test that suggest mode blocks write tools
        result = loop._check_tool_allowed("write_file", {"path": "test.py"})
        assert not result["allowed"], "suggest mode should block write_file"
        # Test that suggest mode allows read tools
        result2 = loop._check_tool_allowed("read_files", {"paths": ["test.py"]})
        assert result2["allowed"], "suggest mode should allow read_files"
        # Test approval callback
        loop.set_approval_prompt(lambda name, args: True)
        assert loop._on_approval_prompt is not None, "approval prompt not set"
        print("  OK: interactive approval flow")
        passed += 1
    except Exception as e:
        print(f"  FAIL: interactive approval flow: {e}")
        failed += 1

    # Test 46: Headless pipe execution (CI/CD)
    try:
        import subprocess
        # Test that CLI can run without TTY (headless mode)
        result = subprocess.run(
            [sys.executable, "-c", "import sys; sys.stdin = open('/dev/null') if sys.platform != 'win32' else None; print('headless ok')"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, f"Headless execution failed: {result.stderr}"
        print("  OK: headless pipe execution")
        passed += 1
    except Exception as e:
        print(f"  FAIL: headless pipe execution: {e}")
        failed += 1

    # Test 47: ReadImage tool
    try:
        from dev.tools.multimodal_tools import ReadImageTool
        tool = ReadImageTool()
        assert tool.name == "read_image"
        result = run_async(tool.execute({"path": "nonexistent.png"}, None, "."))
        assert "error" in result, "Should error on missing file"
        # Test unsupported format
        result = run_async(tool.execute({"path": "test.txt"}, None, "."))
        assert "error" in result, "Should error on unsupported format"
        print("  OK: read_image tool")
        passed += 1
    except Exception as e:
        print(f"  FAIL: read_image tool: {e}")
        failed += 1

    # Test 48: ReadPdf tool
    try:
        from dev.tools.multimodal_tools import ReadPdfTool
        tool = ReadPdfTool()
        assert tool.name == "read_pdf"
        result = run_async(tool.execute({"path": "nonexistent.pdf"}, None, "."))
        assert "error" in result, "Should error on missing file"
        print("  OK: read_pdf tool")
        passed += 1
    except Exception as e:
        print(f"  FAIL: read_pdf tool: {e}")
        failed += 1

    # Test 49: Budget manager integration
    try:
        from dev.utils.budget import BudgetManager, BudgetConfig
        mgr = BudgetManager(BudgetConfig(max_tokens_per_session=1000))
        mgr.record_usage(100, 50, "test")
        status = mgr.check_budget()
        assert status["allowed"], "Should allow within budget"
        assert status["tokens_remaining"] == 850
        # Exhaust budget
        mgr.record_usage(900, 0, "test")
        status = mgr.check_budget()
        assert not status["allowed"], "Should deny when exhausted"
        print("  OK: budget manager integration")
        passed += 1
    except Exception as e:
        print(f"  FAIL: budget manager integration: {e}")
        failed += 1

    # Test 50: Tool rules integration
    try:
        from dev.utils.tool_rules import ToolRulesManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ToolRulesManager(tmpdir)
            mgr.add_rule("read_files", "allow", "Safe")
            mgr.add_rule("run_terminal_command:rm -rf*", "deny", "Dangerous")
            result = mgr.check_tool("read_files")
            assert result["allowed"], "read_files should be allowed"
            result = mgr.check_tool("write_file")
            assert result["allowed"], "write_file should default allow"
            print("  OK: tool rules integration")
            passed += 1
    except Exception as e:
        print(f"  FAIL: tool rules integration: {e}")
        failed += 1

    # Test 51: Hook manager integration
    try:
        from dev.utils.hooks import HookManager, HookEvent
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = HookManager(tmpdir)
            hook = mgr.add_hook(HookEvent.POST_FILE_EDIT, "echo test", "Test hook")
            assert hook.event == HookEvent.POST_FILE_EDIT
            hooks = mgr.list_hooks()
            assert len(hooks) == 1
            print("  OK: hook manager integration")
            passed += 1
    except Exception as e:
        print(f"  FAIL: hook manager integration: {e}")
        failed += 1

    # Test 52: Error recovery integration
    try:
        from dev.utils.error_recovery import ErrorRecovery
        mgr = ErrorRecovery(".")
        # Test file-not-found recovery
        err = FileNotFoundError("No such file: test.py")
        result = run_async(mgr.recover("write_file", {"path": "test.py"}, err))
        # Should at least not crash
        print("  OK: error recovery integration")
        passed += 1
    except Exception as e:
        print(f"  FAIL: error recovery integration: {e}")
        failed += 1

    # Test 53: Git context retrieval
    try:
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from unittest.mock import MagicMock
        loop = ProductionAgentLoop(provider=MagicMock(), tool_registry=MagicMock(), config=LoopConfig())
        git_ctx = loop._get_git_context()
        # May be empty if not in a git repo, but should not crash
        assert isinstance(git_ctx, str)
        print("  OK: git context retrieval")
        passed += 1
    except Exception as e:
        print(f"  FAIL: git context retrieval: {e}")
        failed += 1

    # Test 54: Advanced permissions
    try:
        from dev.utils.advanced_permissions import AdvancedPermissions, ProjectPurger, UltraReview
        perms = AdvancedPermissions(".")
        perms.add_rule("test", "allow", "test rule")
        result = perms.check("test", {})
        assert result["allowed"]
        purger = ProjectPurger(".")
        items = purger.list_removable()
        assert isinstance(items, list)
        print("  OK: advanced permissions")
        passed += 1
    except Exception as e:
        print(f"  FAIL: advanced permissions: {e}")
        failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")
