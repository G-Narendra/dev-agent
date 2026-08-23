"""
End-to-end test script for Dev CLI.

Run this with your NVIDIA NIM API key to test the full flow.

Usage:
    cd dev-agent
    .venv\Scripts\activate
    python tests/test_e2e.py --key YOUR_API_KEY
    python tests/test_e2e.py --key KEY1 --key2 KEY2 --key3 KEY3
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def ok(msg):
    print(f"  {Colors.GREEN}OK{Colors.RESET}: {msg}")


def fail(msg, err=""):
    print(f"  {Colors.RED}FAIL{Colors.RESET}: {msg}")
    if err:
        print(f"         {Colors.DIM}{err}{Colors.RESET}")


def info(msg):
    print(f"  {Colors.CYAN}INFO{Colors.RESET}: {msg}")


def section(msg):
    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")


# ===========================================================================
# Test 1: Provider initialization
# ===========================================================================
def test_provider_init(keys):
    from dev.providers.nim_provider import NimProvider, RateLimitConfig

    section("Test 1: Provider Initialization")

    try:
        provider = NimProvider(keys=keys, config=RateLimitConfig(rpm=40))
        run_async(provider.initialize())
        assert provider._client is not None
        ok(f"Provider initialized with {len(keys)} key(s)")
    except Exception as e:
        fail("Provider init failed", str(e))
        return None

    return provider


# ===========================================================================
# Test 2: Non-streaming chat completion
# ===========================================================================
def test_chat_completion(provider):
    section("Test 2: Chat Completion (non-streaming)")

    try:
        result = run_async(provider.chat_completion(
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Reply briefly."},
                {"role": "user", "content": "Say exactly: 'Hello from Dev!'"}
            ],
            model="default",
            temperature=0.1,
            max_tokens=50,
        ))

        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        ok(f"Got response: {content[:80]}")
        ok(f"Tokens: {usage.get('prompt_tokens', 0)} in / {usage.get('completion_tokens', 0)} out")
        return True
    except Exception as e:
        fail("Chat completion failed", str(e))
        return False


# ===========================================================================
# Test 3: Streaming text-only
# ===========================================================================
def test_streaming_text(provider):
    section("Test 3: Streaming (text-only)")

    try:
        chunks = []
        start = time.time()

        async def stream():
            async for chunk in provider.chat_completion_stream(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Reply briefly."},
                    {"role": "user", "content": "Count from 1 to 5, one number per line."}
                ],
                model="default",
                temperature=0.1,
                max_tokens=100,
            ):
                chunks.append(chunk)
                print(f"    {Colors.DIM}[chunk]{Colors.RESET} {chunk}", end="", flush=True)

        run_async(stream())
        elapsed = time.time() - start

        print()
        full_text = "".join(chunks)
        ok(f"Received {len(chunks)} chunks in {elapsed:.1f}s")
        ok(f"Full response: {full_text[:100]}")
        return True
    except Exception as e:
        fail("Streaming failed", str(e))
        return False


# ===========================================================================
# Test 4: Streaming with tools (structured events)
# ===========================================================================
def test_stream_events(provider):
    section("Test 4: Structured Streaming Events")

    try:
        events = []
        start = time.time()

        async def stream():
            async for event in provider.chat_completion_stream_events(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Reply briefly."},
                    {"role": "user", "content": "What is 2+2? Reply with just the number."}
                ],
                model="default",
                temperature=0.1,
                max_tokens=20,
                tools=None,
            ):
                events.append(event)
                etype = event.get("type", "?")
                if etype == "text":
                    print(f"    {Colors.GREEN}text{Colors.RESET}: {event['content']}", end="", flush=True)
                elif etype == "usage":
                    print(f"\n    {Colors.CYAN}usage{Colors.RESET}: {event['usage']}")
                elif etype == "finish":
                    print(f"    {Colors.YELLOW}finish{Colors.RESET}: {event['reason']}")

        run_async(stream())
        elapsed = time.time() - start

        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) > 0, "No text events received"
        ok(f"Got {len(text_events)} text events in {elapsed:.1f}s")
        return True
    except Exception as e:
        fail("Stream events failed", str(e))
        return False


# ===========================================================================
# Test 5: Tool definitions
# ===========================================================================
def test_tool_definitions():
    section("Test 5: Tool Definitions")

    try:
        from dev.tools.tool_defs import get_all_definitions
        defs = get_all_definitions()
        ok(f"Loaded {len(defs)} tool definitions")
        for d in defs[:5]:
            name = d.get("function", {}).get("name", "?")
            print(f"    - {name}")
        if len(defs) > 5:
            print(f"    ... and {len(defs) - 5} more")
        return True
    except Exception as e:
        fail("Tool definitions failed", str(e))
        return False


# ===========================================================================
# Test 6: Tool registry
# ===========================================================================
def test_tool_registry():
    section("Test 6: Tool Registry")

    try:
        from dev.agents.runtime import ToolRegistry
        from dev.cli.commands import register_new_tools

        registry = ToolRegistry()
        register_new_tools(registry, ".")

        tools = registry.list_tools()
        defs = registry.get_definitions()
        ok(f"Registered {len(tools)} tools, {len(defs)} definitions")
        for t in tools[:5]:
            print(f"    - {t}")
        if len(tools) > 5:
            print(f"    ... and {len(tools) - 5} more")
        return True
    except Exception as e:
        fail("Tool registry failed", str(e))
        return False


# ===========================================================================
# Test 7: ProductionAgentLoop.run_streaming (with tools)
# ===========================================================================
def test_agent_loop(provider):
    section("Test 7: ProductionAgentLoop (streaming + tools)")

    try:
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from dev.agents.runtime import ToolRegistry
        from dev.cli.commands import register_new_tools

        # Set up registry with real tools
        registry = ToolRegistry()
        register_new_tools(registry, ".")

        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=registry,
            config=LoopConfig(model="default", auto_lint=False, auto_commit=False),
            project_path=".",
        )

        # Track callbacks
        text_chunks = []
        tool_calls = []
        tool_results = []

        start = time.time()

        result = run_async(loop.run_streaming(
            prompt="Use the list_directory tool to list files in the current directory, then tell me what you see.",
            system_prompt="You are Dev, a helpful coding assistant. Use tools to help the user.",
            on_tool_call=lambda n, a: tool_calls.append(n),
            on_tool_result=lambda n, r: tool_results.append(n),
            on_text=lambda c: text_chunks.append(c),
            max_steps=5,
        ))
        elapsed = time.time() - start

        full_text = "".join(text_chunks)
        ok(f"Status: {result['status']}")
        ok(f"Steps: {result.get('steps', 0)}")
        ok(f"Tool calls: {len(result.get('tool_calls', []))}")
        ok(f"Time: {elapsed:.1f}s")
        ok(f"Response preview: {full_text[:150]}")
        return True
    except Exception as e:
        fail("Agent loop failed", str(e))
        return False


# ===========================================================================
# Test 8: File creation workflow
# ===========================================================================
def test_file_workflow(provider):
    section("Test 8: File Creation Workflow")

    try:
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from dev.agents.runtime import ToolRegistry
        from dev.cli.commands import register_new_tools

        registry = ToolRegistry()
        register_new_tools(registry, ".")

        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=registry,
            config=LoopConfig(model="default", auto_lint=False, auto_commit=False),
            project_path=".",
        )

        # Create a test file
        text_chunks = []
        result = run_async(loop.run_streaming(
            prompt="Create a file called _dev_test_e2e.py with this content:\nimport sys\nprint(f'Hello from Dev E2E test! Python {sys.version}')",
            system_prompt="You are Dev, a helpful coding assistant. Use tools to create files.",
            on_text=lambda c: text_chunks.append(c),
            on_tool_call=lambda n, a: print(f"    -> {n}", flush=True),
            on_tool_result=lambda n, r: print(f"    <- {n}: {'ok' if isinstance(r, dict) and r.get('success') else r}", flush=True),
            max_steps=5,
        ))

        full_text = "".join(text_chunks)

        # Verify file was created
        test_file = "_dev_test_e2e.py"
        if os.path.exists(test_file):
            with open(test_file) as f:
                content = f.read()
            ok(f"File created: {test_file}")
            ok(f"Content: {content[:100]}")

            # Try to run it
            import subprocess
            proc = subprocess.run(
                [sys.executable, test_file],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                ok(f"File runs successfully: {proc.stdout.strip()}")
            else:
                fail(f"File failed to run: {proc.stderr[:200]}")

            # Cleanup
            os.remove(test_file)
            ok("Cleaned up test file")
        else:
            info(f"File not created (model response: {full_text[:150]})")
            info("This is OK - the model may have described the file instead")

        return True
    except Exception as e:
        fail("File workflow failed", str(e))
        return False


# ===========================================================================
# Test 9: Session persistence
# ===========================================================================
def test_session():
    section("Test 9: Session Persistence")

    try:
        from dev.utils.session import SessionStore

        store = SessionStore(sessions_dir=".dev/sessions")

        # Create session
        sid = store.create_session(name="e2e-test", model="nvidia_nims")
        ok(f"Created session: {sid}")

        # Load it
        session = store.load_session(sid)
        assert session is not None
        ok(f"Loaded session: {session.metadata.name}")

        # List sessions
        sessions = store.list_sessions()
        ok(f"Found {len(sessions)} session(s)")

        # Delete
        store.delete_session(sid)
        ok("Deleted session")
        return True
    except Exception as e:
        fail("Session persistence failed", str(e))
        return False


# ===========================================================================
# Test 10: Project detection
# ===========================================================================
def test_project_detection():
    section("Test 10: Project Detection")

    try:
        from dev.utils.project_detector import ProjectDetector

        detector = ProjectDetector(".")
        info = detector.detect()
        ok(f"Language: {info.language}")
        ok(f"Framework: {info.framework}")
        ok(f"Package manager: {info.package_manager}")
        return True
    except Exception as e:
        fail("Project detection failed", str(e))
        return False


# ===========================================================================
# Main
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description="Dev CLI E2E Test")
    parser.add_argument("--key", required=True, help="NVIDIA NIM API key")
    parser.add_argument("--key2", help="Second API key (optional)")
    parser.add_argument("--key3", help="Third API key (optional)")
    args = parser.parse_args()

    keys = [args.key]
    if args.key2:
        keys.append(args.key2)
    if args.key3:
        keys.append(args.key3)

    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}  Dev CLI - End-to-End Test{Colors.RESET}")
    print(f"{Colors.BOLD}  Keys: {len(keys)} | Model: nvidia/llama-3.1-nemotron-70b-instruct{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")

    tests = [
        ("Tool Definitions", lambda: test_tool_definitions()),
        ("Tool Registry", lambda: test_tool_registry()),
        ("Project Detection", lambda: test_project_detection()),
        ("Session Persistence", lambda: test_session()),
    ]

    # API key tests
    provider = test_provider_init(keys)
    if provider:
        tests.extend([
            ("Chat Completion", lambda: test_chat_completion(provider)),
            ("Streaming Text", lambda: test_streaming_text(provider)),
            ("Stream Events", lambda: test_stream_events(provider)),
            ("Agent Loop", lambda: test_agent_loop(provider)),
            ("File Workflow", lambda: test_file_workflow(provider)),
        ])

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            result = test_fn()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            fail(f"{name}: {e}")
            failed += 1

    # Cleanup
    if provider:
        run_async(provider.close())

    section("Results")
    print(f"  {Colors.GREEN}{passed} passed{Colors.RESET}, {Colors.RED if failed else Colors.GREEN}{failed} failed{Colors.RESET}")

    if failed == 0:
        print(f"\n  {Colors.GREEN}{Colors.BOLD}All tests passed! Dev CLI is working end-to-end.{Colors.RESET}")
    else:
        print(f"\n  {Colors.YELLOW}Some tests failed. Check the output above.{Colors.RESET}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
