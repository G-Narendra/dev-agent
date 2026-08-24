#!/usr/bin/env python3
"""Continue building the portfolio — create missing files."""
import os, sys, json, asyncio
os.environ["PYTHONUTF8"] = "1"

PROJECT = os.path.dirname(os.path.abspath(__file__))

TASK = """Continue building the Narendra Modi portfolio website in portfolio_narendra/. The package.json, server.js, layout.ejs exist but need more work. The CSS is empty and index.ejs, about.ejs, projects.ejs, contact.ejs are MISSING. Create ALL of them now:

1. Overwrite portfolio_narendra/public/css/style.css with COMPLETE modern responsive CSS. Indian flag colors (saffron #FF9933, white #FFFFFF, green #138808). CSS Grid, Flexbox, animations, mobile-first. At least 200 lines of production CSS.

2. Create portfolio_narendra/views/index.ejs - Hero with name, biography, achievements timeline, featured projects. Use HYPERLINKED images from Wikipedia Commons (img src=url). Complete HTML.

3. Create portfolio_narendra/views/about.ejs - Detailed bio, early life, career timeline, milestones. Hyperlinked images.

4. Create portfolio_narendra/views/projects.ejs - Grid of govt initiatives: Smart Cities, Digital India, Make in India, Swachh Bharat, Ayushman Bharat. Cards with hyperlinked images, titles, descriptions, stats.

5. Create portfolio_narendra/views/contact.ejs - Contact form, social links, office address. Form validation.

6. After ALL files created, run: cd portfolio_narendra && npm install

Use write_file for EVERY file. Complete production code, no placeholders. Hyperlinked images only."""

async def main():
    config_path = os.path.expanduser("~/.dev/config.json")
    with open(config_path) as f:
        config = json.load(f)
    keys = config.get("api_keys", [])

    from dev.providers.nim_provider import NimProvider, RateLimitConfig
    provider = NimProvider(keys=keys, config=RateLimitConfig(rpm=40))

    from dev.agents.runtime import ToolRegistry, AgentRuntime
    from dev.cli.commands import register_new_tools
    registry = ToolRegistry()
    register_new_tools(registry, PROJECT)
    runtime = AgentRuntime(provider=provider, tool_registry=registry)

    from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
    from dev.utils.error_recovery import ErrorRecovery
    loop_config = LoopConfig(
        auto_commit=False, auto_test=False, verbose=True,
        approval_mode="full-auto", max_tokens=4096, show_diffs=False,
    )
    loop = ProductionAgentLoop(
        provider=provider, tool_registry=runtime.tools,
        config=loop_config, project_path=PROJECT,
    )
    loop.set_error_recovery(ErrorRecovery(PROJECT))

    def on_call(name, args):
        print(f"  -> {name}({str(args)[:120]})", flush=True)
    def on_result(name, result):
        print(f"  <- {name}: {str(result)[:120]}", flush=True)

    result = await loop.run(
        prompt=TASK, max_steps=30,
        on_tool_call=on_call, on_tool_result=on_result,
    )
    print(f"\nStatus: {result.get('status')} Steps: {result.get('steps')}")
    await provider.close()

if __name__ == "__main__":
    asyncio.run(main())
