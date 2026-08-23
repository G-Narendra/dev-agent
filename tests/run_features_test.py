"""
Tests for new features: approval modes, checkpoints, headless, teams, modes, rules, etc.
"""
import sys
import os
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = 0
failed = 0


def test(name, func):
    global passed, failed
    try:
        func()
        print(f"  OK: {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {name} - {e}")
        failed += 1


# ============================================================================
# Approval Mode Tests
# ============================================================================

print("\n--- Approval Modes ---")


def test_approval_modes():
    from dev.utils.approval import ApprovalManager, ApprovalMode, get_mode_description
    mgr = ApprovalManager()
    assert mgr.mode == ApprovalMode.SUGGEST
    new_mode = mgr.set_mode("full-auto")
    assert new_mode == ApprovalMode.FULL_AUTO
    assert mgr.mode == ApprovalMode.FULL_AUTO
    desc = get_mode_description(new_mode)
    assert "FULL-AUTO" in desc


def test_approval_needs_approval():
    from dev.utils.approval import ApprovalManager, ApprovalMode
    mgr = ApprovalManager()
    mgr.set_mode("suggest")
    assert mgr.needs_approval("file_edit") is True  # Suggest: ask everything
    
    mgr2 = ApprovalManager()
    mgr2.set_mode("auto-edit")
    assert mgr2.needs_approval("file_edit") is False  # Auto-edit: auto file edits
    assert mgr2.needs_approval("shell_exec") is True  # But ask commands
    
    mgr3 = ApprovalManager()
    mgr3.set_mode("full-auto")
    assert mgr3.needs_approval("file_edit") is False  # Full auto: auto everything
    assert mgr3.needs_approval("shell_exec") is False


def test_approval_auto_approve_patterns():
    from dev.utils.approval import ApprovalManager, ApprovalMode
    mgr = ApprovalManager()
    mgr.set_mode("full-auto")
    # In full-auto, dangerous ops still need approval unless pattern matches
    mgr.add_auto_approve_pattern("pip install")
    # shell_exec is not in dangerous list, so full-auto auto-approves
    assert mgr.needs_approval("shell_exec", "pip install httpx") is False
    # git_push IS in dangerous list
    assert mgr.needs_approval("git_push", "git push origin main") is True


def test_approval_stats():
    from dev.utils.approval import ApprovalManager
    mgr = ApprovalManager()
    stats = mgr.get_stats()
    assert stats["total_requests"] == 0
    assert stats["mode"] == "suggest"


test("approval modes", test_approval_modes)
test("approval needs_approval", test_approval_needs_approval)
test("approval patterns", test_approval_auto_approve_patterns)
test("approval stats", test_approval_stats)


# ============================================================================
# Checkpoint Tests
# ============================================================================

print("\n--- Checkpoints ---")


def test_checkpoint_create():
    from dev.utils.checkpoints import CheckpointManager
    tmp = tempfile.mkdtemp()
    try:
        mgr = CheckpointManager(project_root=tmp, checkpoint_dir=".dev/checkpoints")
        # Create a test file
        test_file = os.path.join(tmp, "test.txt")
        with open(test_file, "w") as f:
            f.write("original")
        
        cp = mgr.create_checkpoint("test edit", ["test.txt"])
        assert cp.id == 1
        assert len(cp.changes) == 1
        assert cp.changes[0].action == "modify"
    finally:
        shutil.rmtree(tmp)


def test_checkpoint_undo():
    from dev.utils.checkpoints import CheckpointManager
    tmp = tempfile.mkdtemp()
    try:
        mgr = CheckpointManager(project_root=tmp, checkpoint_dir=".dev/checkpoints")
        test_file = os.path.join(tmp, "test.txt")
        
        # Create file
        with open(test_file, "w") as f:
            f.write("original")
        
        # Create checkpoint
        cp = mgr.create_checkpoint("edit", ["test.txt"])
        
        # Modify file
        with open(test_file, "w") as f:
            f.write("modified")
        mgr.record_after(cp.id, ["test.txt"])
        
        # Undo
        assert mgr.undo() is True
        with open(test_file) as f:
            assert f.read() == "original"
    finally:
        shutil.rmtree(tmp)


def test_checkpoint_list():
    from dev.utils.checkpoints import CheckpointManager
    tmp = tempfile.mkdtemp()
    try:
        mgr = CheckpointManager(project_root=tmp, checkpoint_dir=".dev/checkpoints")
        test_file = os.path.join(tmp, "test.txt")
        with open(test_file, "w") as f:
            f.write("v1")
        mgr.create_checkpoint("first", ["test.txt"])
        
        with open(test_file, "w") as f:
            f.write("v2")
        mgr.create_checkpoint("second", ["test.txt"])
        
        cps = mgr.list_checkpoints()
        assert len(cps) == 2
        assert cps[0]["description"] == "second"  # Most recent first
    finally:
        shutil.rmtree(tmp)


test("checkpoint create", test_checkpoint_create)
test("checkpoint undo", test_checkpoint_undo)
test("checkpoint list", test_checkpoint_list)


# ============================================================================
# Headless Mode Tests
# ============================================================================

print("\n--- Headless Mode ---")


def test_headless_config():
    from dev.utils.headless import HeadlessConfig, OutputFormat, HeadlessRunner
    config = HeadlessConfig(output_format=OutputFormat.JSON, quiet=True)
    runner = HeadlessRunner(config)
    assert runner.config.output_format == OutputFormat.JSON
    assert runner.config.quiet is True


def test_headless_result():
    from dev.utils.headless import HeadlessResult
    result = HeadlessResult(success=True, prompt="test", response="hello")
    j = result.to_json(pretty=True)
    assert "test" in j
    assert result.success is True


test("headless config", test_headless_config)
test("headless result", test_headless_result)


# ============================================================================
# Team Tests
# ============================================================================

print("\n--- Teams ---")


def test_team_create():
    from dev.utils.teams import TeamManager
    tmp = tempfile.mkdtemp()
    try:
        mgr = TeamManager(project_root=tmp)
        team = mgr.create_team("test-team", "Build a web app")
        assert team.name == "test-team"
        assert len(team.agents) >= 4
        assert team.coordinator is not None
    finally:
        shutil.rmtree(tmp)


def test_team_tasks():
    from dev.utils.teams import TeamManager, AgentRole
    tmp = tempfile.mkdtemp()
    try:
        mgr = TeamManager(project_root=tmp)
        mgr.create_team("t1", "do stuff")
        subtasks = mgr.decompose_task("t1", "task-0", ["step 1", "step 2"])
        assert len(subtasks) == 2
        assert mgr.complete_task("t1", "task-0.0", "done")
        status = mgr.get_team_status("t1")
        assert status["completed"] >= 1
    finally:
        shutil.rmtree(tmp)


def test_team_list():
    from dev.utils.teams import TeamManager
    tmp = tempfile.mkdtemp()
    try:
        mgr = TeamManager(project_root=tmp)
        mgr.create_team("a", "task a")
        mgr.create_team("b", "task b")
        teams = mgr.list_teams()
        assert len(teams) == 2
    finally:
        shutil.rmtree(tmp)


test("team create", test_team_create)
test("team tasks", test_team_tasks)
test("team list", test_team_list)


# ============================================================================
# Mode Tests (Plan/Act)
# ============================================================================

print("\n--- Plan/Act Modes ---")


def test_mode_switch():
    from dev.utils.modes import ModeManager, AgentMode
    mgr = ModeManager()
    assert mgr.current_mode == AgentMode.ACT
    mgr.set_mode("plan")
    assert mgr.current_mode == AgentMode.PLAN
    assert mgr.is_plan_mode() is True
    mgr.set_mode("act")
    assert mgr.is_act_mode() is True


def test_mode_plan():
    from dev.utils.modes import ModeManager
    mgr = ModeManager()
    plan = mgr.create_plan("Build API")
    assert plan.goal == "Build API"
    step = mgr.add_step(plan.id, "Design schema")
    assert step.description == "Design schema"
    mgr.start_step(plan.id, 0)
    assert plan.status == "executing"
    mgr.complete_step(plan.id, 0)
    assert plan.status == "completed"


def test_mode_should_act():
    from dev.utils.modes import ModeManager, AgentMode
    mgr = ModeManager()
    mgr.set_mode("plan")
    assert mgr.should_act("read_files") is True
    assert mgr.should_act("write_file") is False
    
    mgr2 = ModeManager()
    mgr2.set_mode("act")
    assert mgr2.should_act("write_file") is True


test("mode switch", test_mode_switch)
test("mode plan", test_mode_plan)
test("mode should_act", test_mode_should_act)


# ============================================================================
# Rules Tests
# ============================================================================

print("\n--- Rules ---")


def test_rules_load():
    from dev.utils.rules import RulesLoader
    tmp = tempfile.mkdtemp()
    try:
        # Create .devrules
        rules_path = os.path.join(tmp, ".devrules")
        with open(rules_path, "w") as f:
            f.write("## Code Style [high]\nUse type hints\n\n## Testing [critical]\nWrite tests\n")
        
        loader = RulesLoader(tmp)
        config = loader.load()
        assert len(config.project_rules) == 2
        assert config.project_rules[0].name == "Code Style"
        assert config.project_rules[0].priority == "high"
    finally:
        shutil.rmtree(tmp)


def test_rules_prompt():
    from dev.utils.rules import RulesConfig, Rule
    config = RulesConfig()
    config.project_rules = [
        Rule(name="Style", content="Use black", priority="high", category="style"),
        Rule(name="Security", content="No secrets", priority="critical", category="security"),
    ]
    prompt = config.to_prompt()
    assert "Project Rules" in prompt
    assert "Style" in prompt
    assert "Security" in prompt


def test_rules_create_default():
    from dev.utils.rules import RulesLoader
    tmp = tempfile.mkdtemp()
    try:
        loader = RulesLoader(tmp)
        loader.create_default_rules()
        assert os.path.exists(os.path.join(tmp, ".devrules"))
    finally:
        shutil.rmtree(tmp)


test("rules load", test_rules_load)
test("rules prompt", test_rules_prompt)
test("rules create default", test_rules_create_default)


# ============================================================================
# Input Manager Tests
# ============================================================================

print("\n--- Inputs ---")


def test_input_parse():
    from dev.utils.inputs import InputManager
    refs = InputManager.parse_image_refs("Look at @image screenshot.png please")
    assert "screenshot.png" in refs
    
    urls = InputManager.parse_url_refs("Check https://example.com for info")
    assert "https://example.com" in urls


def test_input_manager():
    from dev.utils.inputs import InputManager
    mgr = InputManager()
    mgr.add_url("https://example.com")
    inputs = mgr.list_inputs()
    assert len(inputs) == 1
    assert inputs[0]["type"] == "url"
    mgr.clear()
    assert len(mgr.list_inputs()) == 0


test("input parse", test_input_parse)
test("input manager", test_input_manager)


# ============================================================================
# Scheduler Tests
# ============================================================================

print("\n--- Scheduler ---")


def test_scheduler_create():
    from dev.utils.scheduler import AgentScheduler
    tmp = tempfile.mkdtemp()
    try:
        mgr = AgentScheduler(project_root=tmp)
        task = mgr.create_task("daily-check", "Run tests", "every 1d")
        assert task.name == "daily-check"
        assert task.cron_expression == "every 1d"
        tasks = mgr.list_tasks()
        assert len(tasks) == 1
    finally:
        shutil.rmtree(tmp)


def test_scheduler_pause():
    from dev.utils.scheduler import AgentScheduler, ScheduleStatus
    tmp = tempfile.mkdtemp()
    try:
        mgr = AgentScheduler(project_root=tmp)
        task = mgr.create_task("t1", "prompt", "every 1h")
        mgr.pause_task(task.id)
        assert mgr.tasks[task.id].status == ScheduleStatus.PAUSED
        mgr.resume_task(task.id)
        assert mgr.tasks[task.id].status == ScheduleStatus.ACTIVE
    finally:
        shutil.rmtree(tmp)


def test_scheduler_due():
    from dev.utils.scheduler import AgentScheduler, SimpleCron
    from dev.utils.scheduler import ScheduledTask, ScheduleStatus
    from datetime import datetime
    
    task = ScheduledTask(id="t1", name="test", prompt="x", cron_expression="every 1s")
    assert SimpleCron.should_run(task) is True  # Never ran, so should run
    
    task.last_run = datetime.now().isoformat()
    assert SimpleCron.should_run(task) is False  # Just ran


test("scheduler create", test_scheduler_create)
test("scheduler pause", test_scheduler_pause)
test("scheduler due", test_scheduler_due)


# ============================================================================
# Messaging Tests
# ============================================================================

print("\n--- Messaging ---")


def test_messaging_manager():
    from dev.utils.messaging import MessagingManager, Platform
    tmp = tempfile.mkdtemp()
    try:
        mgr = MessagingManager(project_root=tmp)
        # Can't actually connect, but can configure
        assert mgr.list_bots() == []
    finally:
        shutil.rmtree(tmp)


test("messaging manager", test_messaging_manager)


# ============================================================================
# Summary
# ============================================================================

print(f"\n{'=' * 50}")
print(f"Results: {passed} passed, {failed} failed")
print(f"{'=' * 50}")


if __name__ == "__main__":
    sys.exit(1 if failed else 0)
