"""
End-to-end test script for Dev CLI.

Run this with your NVIDIA NIM API key to test the full flow.

Usage:
    cd Dev
    .venv\Scripts\activate
    python tests/run_e2e_test.py --key YOUR_API_KEY
    python tests/run_e2e_test.py --key KEY1 --key2 KEY2 --key3 KEY3
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
# Test 1: Tool Definitions
# ===========================================================================
def test_tool_definitions():
    section("Test 1: Tool Definitions")

    try:
        from dev.tools.real_tools import TOOL_DEFINITIONS
        assert len(TOOL_DEFINITIONS) > 0
        ok(f"Found {len(TOOL_DEFINITIONS)} tool definitions")
        for t in TOOL_DEFINITIONS[:5]:
            info(f"  Tool: {t.get('function', {}).get('name', 'unknown')}")
        return True
    except Exception as e:
        fail("Tool definitions failed", str(e))
        return False


# ===========================================================================
# Test 2: Tool Registry
# ===========================================================================
def test_tool_registry():
    section("Test 2: Tool Registry")

    try:
        from dev.tools.real_tools import build_tool_registry
        registry = build_tool_registry()
        assert len(registry) > 0
        ok(f"Registered {len(registry)} tools")
        for name in list(registry.keys())[:5]:
            info(f"  Registered: {name}")
        return True
    except Exception as e:
        fail("Tool registry failed", str(e))
        return False


# ===========================================================================
# Test 3: Provider initialization
# ===========================================================================
def test_provider_init(keys):
    from dev.providers.nim_provider import NimProvider, RateLimitConfig

    section("Test 3: Provider Initialization")

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
# Test 4: Non-streaming chat completion
# ===========================================================================
def test_chat_completion(provider):
    section("Test 4: Chat Completion (non-streaming)")

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
# Test 5: Streaming text
# ===========================================================================
def test_streaming_text(provider):
    section("Test 5: Streaming Text")

    try:
        chunks = []
        async def collect():
            async for chunk in provider.chat_completion_stream(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Count from 1 to 5, one number per line."}
                ],
                model="default",
                temperature=0.1,
                max_tokens=100,
            ):
                chunks.append(chunk)

        run_async(collect())

        full = "".join(chunks)
        ok(f"Got {len(chunks)} chunks, {len(full)} chars total")
        ok(f"Response: {full[:100]}")
        assert len(chunks) > 1, "Expected multiple chunks for streaming"
        return True
    except Exception as e:
        fail("Streaming failed", str(e))
        return False


# ===========================================================================
# Test 6: Stream events (with tools)
# ===========================================================================
def test_stream_events(provider):
    section("Test 6: Stream Events (with tool definitions)")

    try:
        from dev.tools.real_tools import TOOL_DEFINITIONS

        events = []
        async def collect():
            async for event in provider.chat_completion_stream_events(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "What files are in the current directory?"}
                ],
                model="default",
                temperature=0.1,
                max_tokens=200,
                tools=TOOL_DEFINITIONS,
            ):
                events.append(event)

        run_async(collect())

        ok(f"Got {len(events)} events")
        text_events = [e for e in events if e.get("type") == "text"]
        tool_events = [e for e in events if e.get("type") == "tool_call"]
        info(f"  Text events: {len(text_events)}")
        info(f"  Tool events: {len(tool_events)}")

        full_text = "".join(e.get("content", "") for e in text_events)
        if full_text:
            ok(f"Text: {full_text[:100]}")

        return True
    except Exception as e:
        fail("Stream events failed", str(e))
        return False


# ===========================================================================
# Test 7: Agent Loop
# ===========================================================================
def test_agent_loop(provider):
    section("Test 7: Agent Loop (ProductionAgentLoop)")

    try:
        from dev.agents.production_loop import ProductionAgentLoop, LoopConfig
        from dev.tools.real_tools import build_tool_registry

        registry = build_tool_registry()
        loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=registry,
            config=LoopConfig(
                model="default",
                temperature=0.1,
                max_tokens=500,
                max_steps=3,
                auto_lint=False,
                auto_commit=False,
                verbose=False,
            ),
        )

        result = run_async(loop.run(
            prompt="Create a file called test_hello.txt with the content 'Hello from Dev!'",
            max_steps=3,
        ))

        ok(f"Agent status: {result.get('status')}")
        ok(f"Steps: {result.get('steps', 0)}")
        tool_calls = result.get("tool_calls", [])
        ok(f"Tool calls: {len(tool_calls)}")
        for tc in tool_calls:
            info(f"  Called: {tc.get('name', 'unknown')}")
        return True
    except Exception as e:
        fail("Agent loop failed", str(e))
        return False


# ===========================================================================
# Test 8: File Workflow
# ===========================================================================
def test_file_workflow(provider):
    section("Test 8: File Workflow (create + read + verify)")

    try:
        from dev.tools.real_tools import build_tool_registry

        registry = build_tool_registry()
        test_path = "_e2e_test_output.txt"
        test_content = "This is a test file created by Dev E2E test."

        # Write
        write_handler = registry.get("write_file")
        assert write_handler, "write_file tool not found"
        write_result = run_async(write_handler.execute(
            {"path": test_path, "content": test_content, "instructions": "Create test file"},
            None, ".",
        ))
        ok(f"Write result: {write_result}")

        # Read
        read_handler = registry.get("read_files")
        assert read_handler, "read_files tool not found"
        read_result = run_async(read_handler.execute(
            {"paths": [{"path": test_path}]},
            None, ".",
        ))
        ok(f"Read result success: {read_result.get('success', False)}")

        # Verify content
        files = read_result.get("files", [])
        if files:
            content = files[0].get("content", "")
            assert test_content in content, f"Content mismatch: {content[:100]}"
            ok("Content verified!")

        # Cleanup
        os.remove(test_path)
        ok("Cleanup done")

        return True
    except Exception as e:
        fail("File workflow failed", str(e))
        # Cleanup on error
        try:
            os.remove("_e2e_test_output.txt")
        except Exception:
            pass
        return False


# ===========================================================================
# Test 9: Session Persistence
# ===========================================================================
def test_session():
    section("Test 9: Session Persistence")

    try:
        from dev.utils.sessions import SessionStore

        store = SessionStore(".dev/sessions")
        sid = store.create_session({"test": True})
        ok(f"Created session: {sid}")

        store.save_message(sid, {"role": "user", "content": "test message"})
        store.save_message(sid, {"role": "assistant", "content": "test response"})
        ok("Saved messages")

        loaded = store.load_session(sid)
        assert loaded is not None, "Session not found"
        ok(f"Loaded session with {len(loaded.get('messages', []))} messages")

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
        info_result = detector.detect()
        ok(f"Language: {info_result.language}")
        ok(f"Framework: {info_result.framework}")
        ok(f"Package manager: {info_result.package_manager}")
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
