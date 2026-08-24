#!/usr/bin/env python3
"""E2E test: Run Dev agent to build Narendra Modi portfolio website."""
import os, sys, json, asyncio, time, traceback
os.environ["PYTHONUTF8"] = "1"

PROJECT = os.path.dirname(os.path.abspath(__file__))
TASK = (
    "Create a complete portfolio website for Narendra Modi in the portfolio_narendra folder. "
    "Use Node.js with Express and EJS. Include: "
    "1. package.json with express and ejs dependencies "
    "2. server.js with routes for home, about, projects, contact "
    "3. views/index.ejs with a hero section, biography, achievements timeline "
    "4. views/about.ejs with detailed about page "
    "5. views/projects.ejs showcasing government projects "
    "6. views/contact.ejs with a contact form "
    "7. public/css/style.css with modern responsive design "
    "8. Run npm install after creating files "
    "Make it production-ready with proper error handling."
)

async def main():
    print("=" * 60)
    print("E2E TEST: Building Narendra Modi Portfolio Website")
    print("=" * 60)
    print(f"Task: {TASK[:100]}...")
    print(f"Project: {PROJECT}")
    print()
    
    # Load config
    config_path = os.path.expanduser("~/.dev/config.json")
    if not os.path.exists(config_path):
        print("ERROR: No config.json found. Run 'narendra setup' first.")
        return
    
    with open(config_path) as f:
        config = json.load(f)
    
    keys = config.get("api_keys", [])
    if not keys:
        print("ERROR: No API keys configured.")
        return
    
    print(f"API Keys: {len(keys)}")
    
    # Initialize provider
    from dev.providers.nim_provider import NimProvider, RateLimitConfig
    provider = NimProvider(keys=keys, config=RateLimitConfig(rpm=40))
    print("Provider initialized")
    
    # Initialize tool registry
    from dev.agents.runtime import ToolRegistry, AgentRuntime
    from dev.cli.commands import register_new_tools
    registry = ToolRegistry()
    register_new_tools(registry, PROJECT)
    print(f"Tools registered: {len(registry._tools)}")
    
    # Create runtime (wraps registry)
    runtime = AgentRuntime(provider=provider, tool_registry=registry)
    
    # Initialize production loop
    from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
    
    loop_config = LoopConfig(
        auto_commit=False,
        auto_test=False,
        verbose=True,
        approval_mode="full-auto",
        max_tokens=4096,
    )
    
    loop = ProductionAgentLoop(
        provider=provider,
        tool_registry=runtime.tools,
        config=loop_config,
        project_path=PROJECT,
    )
    
    print("Production loop initialized")
    print("-" * 60)
    print("STARTING AGENT...")
    print("-" * 60)
    
    start_time = time.time()
    
    try:
        result = await loop.run(
            prompt=TASK,
            max_steps=50,
            on_tool_call=lambda name, args: print(f"  → {name}({str(args)[:100]})"),
            on_tool_result=lambda name, result: print(f"  ← {name}: {str(result)[:100]}"),
        )
        
        elapsed = time.time() - start_time
        
        print()
        print("=" * 60)
        print("AGENT FINISHED")
        print("=" * 60)
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Steps: {result.get('steps', 0)}")
        print(f"Tool calls: {result.get('tool_calls', 0)}")
        print(f"Time: {elapsed:.1f}s")
        
        if result.get("error"):
            print(f"Error: {result['error']}")
        
        # Check what files were created
        portfolio_dir = os.path.join(PROJECT, "portfolio_narendra")
        if os.path.exists(portfolio_dir):
            files = []
            for root, dirs, fnames in os.walk(portfolio_dir):
                for fname in fnames:
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, portfolio_dir)
                    size = os.path.getsize(fpath)
                    files.append((rel, size))
            
            print(f"\nFiles created: {len(files)}")
            for rel, size in sorted(files):
                print(f"  {rel} ({size} bytes)")
            
            # Verify key files exist
            required = ["package.json", "server.js"]
            for req in required:
                if os.path.exists(os.path.join(portfolio_dir, req)):
                    print(f"  ✅ {req}")
                else:
                    print(f"  ❌ {req} MISSING")
            
            # Verify node_modules (npm install ran)
            if os.path.exists(os.path.join(portfolio_dir, "node_modules")):
                print("  ✅ node_modules (npm install ran)")
            else:
                print("  ⚠️ node_modules missing (npm install may not have run)")
        else:
            print("\n❌ portfolio_narendra folder NOT created!")
        
    except Exception as e:
        elapsed = time.time() - start_time
        print()
        print("=" * 60)
        print("AGENT CRASHED")
        print("=" * 60)
        print(f"Time: {elapsed:.1f}s")
        print(f"Error: {e}")
        traceback.print_exc()
    
    finally:
        await provider.close()

if __name__ == "__main__":
    asyncio.run(main())
