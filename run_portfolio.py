"""Run Dev agent to build Narendra Modi portfolio website."""
import asyncio
import sys
import os

sys.path.insert(0, '.')
os.environ['PYTHONUTF8'] = '1'

from dev.cli.main import get_runtime, load_config
from dev.agents.production_loop import ProductionAgentLoop, LoopConfig


async def main():
    config = load_config()
    keys = config.get("api_keys", [])
    if not keys:
        print("ERROR: No API keys found. Run: python -m dev setup")
        return

    from dev.providers.nim_provider import NimProvider, RateLimitConfig
    rate_config = RateLimitConfig(rpm=config.get("rpm", 40))
    provider = NimProvider(keys=keys, config=rate_config)
    await provider.initialize()

    project = os.path.abspath('.')
    runtime = get_runtime(provider, project)

    loop_config = LoopConfig(
        model="meta/llama-3.1-8b-instruct",
        temperature=0.3,
        max_tokens=4096,
        approval_mode="full-auto",
        verbose=True,
    )

    loop = ProductionAgentLoop(
        provider=runtime.provider,
        tool_registry=runtime.tools,
        config=loop_config,
        project_path=project,
    )

    prompt = """Build a complete portfolio website for Narendra Modi in the 'portfolio' folder.

Do these steps ONE AT A TIME. After each write_file, immediately move to the next.

1. write_todos with this list:
   [{"task":"Create portfolio/package.json","completed":false},{"task":"Create portfolio/server.js","completed":false},{"task":"Create portfolio/public/index.html","completed":false},{"task":"Create portfolio/public/about.html","completed":false},{"task":"Create portfolio/public/achievements.html","completed":false},{"task":"Create portfolio/public/gallery.html","completed":false},{"task":"Create portfolio/public/contact.html","completed":false},{"task":"Create portfolio/public/css/style.css","completed":false},{"task":"Create portfolio/public/js/script.js","completed":false}]

2. write_file portfolio/package.json: {"name":"modi-portfolio","version":"1.0.0","scripts":{"start":"node server.js"},"dependencies":{"express":"^4.18.0"}}

3. write_file portfolio/server.js: Express server with GET routes for /, /about, /achievements, /gallery, /contact. Serves static from public/. POST /contact saves to contacts.json.

4. write_file portfolio/public/index.html: Full HTML page with nav (Home/About/Achievements/Gallery/Contact), hero section with saffron #FF9933 and green #138808 colors, footer.

5. write_file portfolio/public/about.html: Full HTML page about Narendra Modi biography.

6. write_file portfolio/public/achievements.html: Full HTML page listing achievements.

7. write_file portfolio/public/gallery.html: Full HTML page with image placeholders.

8. write_file portfolio/public/contact.html: Full HTML page with name/email/message form that POSTs to /contact.

9. write_file portfolio/public/css/style.css: Complete CSS with Indian flag colors, responsive design, nav styling, hero section, cards, form styling. MUST be real CSS code with selectors and properties, NOT comments.

10. write_file portfolio/public/js/script.js: Real JavaScript for nav toggle and form validation. MUST be real JS code, NOT comments.

11. run_terminal_command "cd portfolio && npm install"

IMPORTANT: Every write_file must contain REAL CODE. CSS must have selectors like body{} .nav{} etc. JS must have functions. NEVER write comments like "Add your code here"."""

    def on_text(text):
        print(text, end='', flush=True)

    def on_tool_call(name, args):
        print(f"\n  -> {name}", flush=True)

    def on_tool_result(name, result):
        if isinstance(result, dict) and 'error' in result:
            print(f"  <- {name}: ERROR: {result['error']}", flush=True)
        else:
            print(f"  <- {name}: ok", flush=True)

    result = await loop.run_streaming(
        prompt=prompt,
        on_text=on_text,
        on_tool_call=on_tool_call,
        on_tool_result=on_tool_result,
        max_steps=30,
    )

    print(f"\n\n{'='*60}")
    print(f"Status: {result['status']}")
    print(f"Steps: {result.get('steps', 0)}")
    print(f"Tools used: {len(result.get('tool_calls', []))}")

    # Check what was created
    print(f"\n{'='*60}")
    print("Files created:")
    for root, dirs, files in os.walk('portfolio'):
        dirs[:] = [d for d in dirs if d != 'node_modules']
        for f in files:
            fpath = os.path.join(root, f)
            size = os.path.getsize(fpath)
            print(f"  {fpath} ({size} bytes)")

    await provider.close()


if __name__ == '__main__':
    asyncio.run(main())
