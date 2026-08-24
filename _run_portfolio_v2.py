"""Run Dev Agent to build portfolio - using non-streaming run() which works better."""
import asyncio, os, sys, json, time
sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dev.providers.nim_provider import NimProvider, RateLimitConfig
from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
from dev.agents.runtime import ToolRegistry
from dev.cli.commands import register_new_tools
from dev.agents.agent_definition import get_agent

PROMPT = """Build a complete portfolio website for Narendra Modi in the "portfolio_narendra" folder.

Step-by-step instructions — follow EXACTLY:

STEP 1: Create package.json
Use write_file to create portfolio_narendra/package.json with Express + EJS dependencies.

STEP 2: Create server.js  
Use write_file to create portfolio_narendra/server.js with Express server, EJS templating, routes for /, /about, /achievements, /gallery, /timeline, /contact, /projects, /news. Contact form saves to data/messages.json.

STEP 3: Create data files
Use write_file for each:
- portfolio_narendra/data/projects.json (government schemes data)
- portfolio_narendra/data/timeline.json (career timeline 1950-present)
- portfolio_narendra/data/news.json (latest news)

STEP 4: Create views
Use write_file for each:
- portfolio_narendra/views/layout.ejs (shared layout with header/footer/nav)
- portfolio_narendra/views/index.ejs (homepage with hero, highlights)
- portfolio_narendra/views/about.ejs (biography, education)
- portfolio_narendra/views/achievements.ejs (major reforms with cards)
- portfolio_narendra/views/gallery.ejs (photo gallery with lightbox)
- portfolio_narendra/views/timeline.ejs (interactive timeline)
- portfolio_narendra/views/contact.ejs (contact form with validation)
- portfolio_narendra/views/projects.ejs (government schemes)
- portfolio_narendra/views/news.ejs (latest news)
- portfolio_narendra/views/404.ejs (error page)

STEP 5: Create CSS
Use write_file for portfolio_narendra/public/css/style.css — modern responsive design with Indian flag colors (saffron #FF9933, white, green #138808), Google Fonts (Poppins), animations, dark/light mode toggle.

STEP 6: Install and test
Use run_terminal_command: cd portfolio_narendra && npm install

IMPORTANT RULES:
- Call write_file tool for EACH file — one file per tool call
- Do NOT describe files in text — actually create them with write_file
- Every file must have REAL content, not placeholders
- Use the write_file tool, not bash commands to create files"""

async def main():
    config_data = json.load(open(os.path.expanduser('~/.dev/config.json')))
    keys = config_data.get('api_keys', [])
    p = NimProvider(keys=keys, config=RateLimitConfig(rpm=40))
    await p.initialize()
    
    registry = ToolRegistry()
    register_new_tools(registry, os.getcwd())
    agent = get_agent('coder')
    
    loop = ProductionAgentLoop(
        provider=p,
        tool_registry=registry,
        config=LoopConfig(
            model='default', temperature=0.3, max_tokens=8192,
            verbose=True, approval_mode='full-auto', max_retries=8,
        ),
        project_path=os.getcwd(),
    )
    loop.set_tool_names(agent.tool_names)
    
    def on_call(name, args):
        print(f'  -> {name}({str(args)[:120]})', flush=True)
    def on_result(name, result):
        print(f'  <- {name}: {str(result)[:120]}', flush=True)
    
    start = time.time()
    result = await loop.run(
        prompt=PROMPT,
        max_steps=50,
        on_tool_call=on_call,
        on_tool_result=on_result,
    )
    elapsed = time.time() - start
    
    print(f'\n{"="*60}')
    print(f'Status: {result.get("status")}')
    print(f'Steps: {result.get("steps", 0)}')
    print(f'Tool calls: {len(result.get("tool_calls", []))}')
    print(f'Time: {elapsed:.1f}s')
    print(f'{"="*60}')
    
    # List files
    for f in sorted(os.listdir('portfolio_narendra')) if os.path.exists('portfolio_narendra') else []:
        fpath = os.path.join('portfolio_narendra', f)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath)
            lines = sum(1 for _ in open(fpath, encoding='utf-8', errors='ignore'))
            print(f'  {f}: {lines} lines, {size} bytes')
    
    await p.close()

if __name__ == '__main__':
    asyncio.run(main())
