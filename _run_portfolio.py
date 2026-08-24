"""
Run Dev Agent to build the Narendra Modi portfolio website.
Prompts the agent with a detailed task and monitors progress.
"""
import asyncio
import sys
import os
import time
import json
from pathlib import Path

# Ensure we're in the right directory
os.chdir(Path(__file__).parent)
sys.path.insert(0, os.getcwd())

from dev.providers.nim_provider import NimProvider, RateLimitConfig
from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
from dev.agents.runtime import AgentRuntime, ToolRegistry
from dev.cli.commands import register_new_tools
from dev.utils.error_recovery import ErrorRecovery
from dev.utils.budget import BudgetManager, BudgetConfig
from dev.utils.tool_rules import ToolRulesManager
from dev.utils.hooks import HookManager
from dev.cli.main import load_config, get_runtime


async def main():
    # Load task prompt
    task_prompt = Path("portfolio_task.txt").read_text(encoding="utf-8")

    # Load config and create provider
    config_data = load_config()
    keys = config_data.get("api_keys", [])
    if not keys:
        print("[ERROR] No API keys found. Run: dev setup")
        return

    rate_config = RateLimitConfig(rpm=config_data.get("rpm", 40))
    provider = NimProvider(keys=keys, config=rate_config)
    await provider.initialize()
    print(f"[OK] Loaded {len(keys)} API key(s)")

    # Create runtime with all tools
    project = os.getcwd()
    runtime = get_runtime(provider, project)

    # Detect project language
    from dev.utils.project_detector import ProjectDetector
    detector = ProjectDetector(project)
    info = detector.detect()
    lang = getattr(info, 'language', 'unknown') or 'unknown'
    fw = getattr(info, 'framework', 'unknown') or 'unknown'
    if lang != "unknown":
        print(f"[OK] Detected: {lang}/{fw}")

    # Create the agent loop
    loop_config = LoopConfig(
        model="default",
        temperature=0.3,
        max_tokens=8192,
        max_retries=8,
        verbose=True,
        auto_lint=False,
        auto_test=False,
        auto_commit=False,
        approval_mode="full-auto",
        diff_preview=False,
        enforce_plan_mode=False,
    )

    agent_loop = ProductionAgentLoop(
        provider=provider,
        tool_registry=runtime.tools,
        config=loop_config,
        project_path=project,
    )

    # Wire subsystems
    agent_loop.set_budget_manager(BudgetManager(BudgetConfig()))
    agent_loop.set_error_recovery(ErrorRecovery(project))
    try:
        agent_loop.set_tool_rules(ToolRulesManager(project))
    except Exception:
        pass
    try:
        agent_loop.set_hook_manager(HookManager(project))
    except Exception:
        pass

    # Callbacks
    def on_tool_call(name, args):
        args_str = str(args)[:120]
        print(f"  -> {name}({args_str})", flush=True)

    def on_tool_result(name, result):
        result_str = str(result)[:120]
        print(f"  <- {name}: {result_str}", flush=True)

    # Run
    print("\n" + "=" * 60)
    print("  DEV AGENT — Building Narendra Modi Portfolio")
    print("=" * 60)
    print(f"  Model: {loop_config.model}")
    print(f"  Mode:  {loop_config.approval_mode}")
    print(f"  Max steps: 50")
    print("=" * 60 + "\n")

    start = time.time()

    try:
        result = await agent_loop.run(
            prompt=task_prompt,
            max_steps=50,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
        )
    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        await provider.close()

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("  AGENT FINISHED")
    print("=" * 60)
    print(f"  Status:  {result.get('status', 'unknown')}")
    print(f"  Steps:   {result.get('steps', 0)}")
    print(f"  Tools:   {result.get('tool_count', 0)}")
    print(f"  Time:    {elapsed:.1f}s")
    print(f"  Content: {len(result.get('content', ''))} chars")
    print("=" * 60)

    # List created files
    portfolio_dir = Path("portfolio_narendra")
    if portfolio_dir.exists():
        print("\n  FILES CREATED:")
        total_lines = 0
        for f in sorted(portfolio_dir.rglob("*")):
            if f.is_file() and "node_modules" not in str(f):
                size = f.stat().st_size
                try:
                    lines = sum(1 for _ in open(f, encoding="utf-8", errors="ignore"))
                    total_lines += lines
                except Exception:
                    lines = 0
                print(f"    {f.relative_to('.')}  ({size:,} bytes, {lines} lines)")
        print(f"\n  Total: {total_lines} lines across {len(list(portfolio_dir.rglob('*')))} files")
    else:
        print("\n  WARNING: portfolio_narendra folder not created!")

    print("\n  To run: cd portfolio_narendra && npm install && node server.js")


if __name__ == "__main__":
    asyncio.run(main())
