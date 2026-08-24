# DEV AGENT — COMPREHENSIVE PROBLEM LIST & RESEARCHED SOLUTIONS

**Created**: 2026-08-24
**Research Sources**: Claude Code docs, Aider source, OpenHands architecture, academic paper "Inside the Scaffold" (2604.03515v2), Claude Code deep dives

---

## KEY ARCHITECTURAL INSIGHT (from research)

> "Community analysis estimates that about 1.6% of Claude Code's codebase is decision logic. The other 98.4% is the harness around it." — Inside Claude Code Part 1

> "Aider's LLM produces edits in a text format parsed by the scaffold (base_coder.py:2296-2304). Aider's 13 model-specific edit formats..." — Taxonomy paper

> "The loop at a glance: Receive prompt → Evaluate and respond → Execute tools → Repeat until no tool calls" — Claude Code Agent SDK docs

**The lesson**: The agent loop is trivially simple. The entire value is in:
1. A minimal, reliable set of tools (10-15 max)
2. Proper tool definitions that models actually understand
3. A system prompt that tells the model to USE tools proactively
4. Reliable streaming and tool execution

---

## CRITICAL FAILURES (Must Fix)

### PROBLEM #1: Agent Can't Build Multi-File Projects
**Symptom**: Agent creates 1-2 files then returns text and stops.
**Root Cause**: 
- System prompt says "NEVER call tools" / "ONLY call write_file when asked"
- Auto-continuation logic (`_has_pending_todos`) doesn't fire reliably
- Model returns text describing what it would do instead of actually doing it
**Research Solution** (from Claude Code docs):
- Claude Code's loop: "Claude continues calling tools and processing results until it produces a response with no tool calls"
- The system prompt must PROACTIVELY instruct the model to use tools
- Auto-continue when model returns text but has unfinished work
**Fix Plan**:
1. Rewrite system prompt to say "You MUST use tools to complete tasks. ALWAYS use write_file to create files."
2. Fix auto-continuation to be more aggressive
3. Add a "task decomposition" step that creates a plan, then executes each step

### PROBLEM #2: Streaming is Broken
**Symptom**: Token-by-token streaming doesn't work — model returns all text at once.
**Root Cause**:
- `chat_completion_stream_events` has broken truncation detection
- The `_streaming_live` attribute doesn't exist on DevTUI
- Streaming path yields full text in one chunk, not token-by-token
**Research Solution** (from Claude Code SDK):
- "Enable streaming to show live text and tool calls as the loop runs"
- Claude Code uses SSE (Server-Sent Events) from the API and yields each delta
**Fix Plan**:
1. Fix NimProvider streaming to properly yield each SSE delta
2. Fix DevTUI to have `_streaming_live` attribute
3. Test with actual API key to verify token-by-token output

### PROBLEM #3: Only 15 of 59 Tools Reach the LLM
**Symptom**: Agent has 59 registered tools but only 15 are sent to the model.
**Root Cause**:
- `agent_definition.py` has a hardcoded `tool_names` list of 15
- Other 44 tools are registered but unreachable
**Research Solution** (from taxonomy paper):
- "Tool counts range from 0 to 37" across 13 agents
- Aider has 0 LLM-callable tools (user drives navigation)
- Claude Code has ~12 built-in tools
- The sweet spot is 10-15 tools that the model can reliably use
**Fix Plan**:
1. Keep the 15 core tools that work
2. Add a `ToolSearch` tool (like Claude Code) that lets the model discover additional tools on demand
3. This gives the model access to all 59 tools through a discovery mechanism

### PROBLEM #4: Tool Call Parsing is Fragile
**Symptom**: Model outputs JSON-like text instead of proper function calls.
**Root Cause**:
- Llama 3.1 70B sometimes doesn't use the function calling API properly
- `_parse_code_blocks()` regex is unreliable
- DeepSeek V4 outputs `<write_file>` XML tags
**Research Solution** (from Aider):
- Aider uses 13 model-specific edit formats (edit_block, whole, diff, etc.)
- Each format is a different way the model can express edits
- The scaffold parses whichever format the model uses
**Fix Plan**:
1. Add multiple output format parsers (XML tags, JSON blocks, markdown code blocks)
2. Use the NIM API's native function calling (not text parsing)
3. Add a fallback: if no tool calls in response, parse text for code blocks

### PROBLEM #5: System Prompt Fights the Agent
**Symptom**: System prompt says "NEVER call tools" which contradicts the task.
**Root Cause**:
- `agent_definition.py` has safety rules that prevent proactive tool use
- The prompt was designed for interactive chat, not autonomous `run` mode
**Research Solution** (from Claude Code):
- Claude Code has different system prompts for different modes
- The `run` mode prompt explicitly tells the model to use tools
**Fix Plan**:
1. Create separate system prompts for `chat` vs `run` modes
2. `run` mode: "You are an autonomous agent. Use tools to complete the task. Create files, run commands, build the project."
3. `chat` mode: "You are a helpful assistant. Use tools when needed."

### PROBLEM #6: nonlocal approval Bug
**Symptom**: `UnboundLocalError: cannot access local variable 'approval'`
**Root Cause**:
- `approval` is a parameter of the outer function but `nonlocal approval` is used inside `_run()`
- Python treats it as a local variable because of the `nonlocal` declaration
**Fix Plan**:
1. Remove `nonlocal approval` — use a different variable name inside `_run()`
2. Pass `approval` as a parameter to `_run()` instead

### PROBLEM #7: No Real End-to-End Test
**Symptom**: 70 unit tests pass but no test actually runs the agent with a real API.
**Fix Plan**:
1. Create `_e2e_test.py` that runs the agent with a real NIM API key
2. Test: create a simple file, verify it exists
3. Test: create a multi-file project, verify all files exist
4. Keep this test for ongoing verification

---

## HIGH SEVERITY ISSUES

### PROBLEM #8: Model Limitations Not Handled
**Root Cause**: Llama 70B can only handle ~15-20 tools reliably.
**Research Solution**: Claude Code uses `ToolSearch` — a meta-tool that discovers other tools on demand.
**Fix Plan**: Implement `ToolSearch` tool that lets the model find and use additional tools.

### PROBLEM #9: Context Window Management is Naive
**Root Cause**: Token estimation uses `len(text) // 3`, no semantic pruning.
**Research Solution** (from Aider): Tree-sitter repo map ranks functions by relevance.
**Fix Plan**:
1. Improve token estimation (use tiktoken or similar)
2. Add relevance-based pruning: keep recent messages, summarize old ones
3. Auto-compact at 70% (not 80%) to avoid hitting limits

### PROBLEM #10: No Real Research Capability
**Root Cause**: `web_search` uses DuckDuckGo scraping, `read_url` has no JS rendering.
**Research Solution**: Claude Code has `WebSearch` and `WebFetch` as core tools.
**Fix Plan**:
1. Improve `web_search` with multiple search backends
2. Add `read_url` with proper HTML parsing and content extraction
3. Make the model use these tools proactively when building projects

### PROBLEM #11: MCP Integration is Shallow
**Root Cause**: 84 MCP servers registered but most are just metadata.
**Fix Plan**:
1. Only register MCP servers that are actually installed
2. Add auto-install for common MCP servers
3. Add connection pooling and caching

### PROBLEM #12: Free APIs are Mostly Decorative
**Root Cause**: Most APIs are joke APIs (cat facts, dad jokes).
**Fix Plan**:
1. Add practical APIs: JSONPlaceholder, HTTPBin, GitHub API, npm registry
2. Remove joke APIs from the default list
3. Make the API tool actually useful for building projects

### PROBLEM #13: Skills System is Unused
**Root Cause**: 465 skills exist but the agent never loads them.
**Fix Plan**:
1. Auto-detect project type and load relevant skills
2. Inject top 3-5 relevant skills into the system prompt
3. Make the `skill` tool actually load and use skill content

### PROBLEM #14: Computer Use is Non-Functional
**Root Cause**: `pyautogui` is never installed.
**Fix Plan**:
1. Remove computer use tools (they require a GUI environment)
2. Focus on browser tools (Playwright/Puppeteer) which work headlessly
3. Add proper error messages when tools can't be used

---

## MEDIUM SEVERITY ISSUES

### PROBLEM #15: Code Quality — 3,765-line main.py
**Fix Plan**: Split into smaller modules: cli/chat.py, cli/run.py, cli/commands.py

### PROBLEM #16: No Real Undo/Redo
**Fix Plan**: Use git stash for undo, git stash pop for redo

### PROBLEM #17: No Real Sandboxing
**Fix Plan**: Use subprocess with timeout and resource limits instead of Docker

### PROBLEM #18: Team System is Decorative
**Fix Plan**: Implement actual parallel execution with asyncio

### PROBLEM #19: Session Management is Broken
**Fix Plan**: Add file locking, session cleanup, proper resume

### PROBLEM #20: Security is Theater
**Fix Plan**: Use proper keyring for API key storage, not file-based encryption

---

## LOW SEVERITY / COSMETIC ISSUES

### PROBLEMS #21-30: Missing Features
- No `--continue` flag → Add it
- No `/vim` mode → Skip (not critical)
- No IDE integration → Skip (CLI-only is fine)
- No webhook/CI → Skip (not needed for free tool)
- No multi-user → Skip (single user is fine)
- No voice input → Skip
- No release notes → Add basic version check
- No `/permissions` command → Add it
- No `/bug` command → Add it
- No `/session-id` → Add it

---

## IMPLEMENTATION ORDER

1. Fix system prompt (#5) — makes everything else work better
2. Fix agent loop (#1) — core functionality
3. Fix streaming (#2) — user experience
4. Fix tool parsing (#4) — reliability
5. Fix nonlocal bug (#6) — crash fix
6. Add ToolSearch (#3, #8) — expand capabilities
7. Fix context management (#9) — prevent crashes
8. Fix research tools (#10) — real-world utility
9. Clean up MCP/APIs (#11, #12) — remove fake entries
10. Wire skills (#13) — use existing assets
11. Remove computer use (#14) — dead code
12. Add e2e test (#7) — prevent regressions
13. Medium fixes (#15-20) — code quality
14. Low fixes (#21-30) — polish

---

## STATUS

- [x] #5: System prompt fights the agent — FIXED: Rewrote to be aggressive about tool use
- [x] #6: nonlocal approval bug — FIXED: Removed nonlocal, used effective_approval variable
- [x] #1: Agent can't build multi-file projects — FIXED: Improved auto-continuation with text detection
- [x] #2: Streaming is broken — FIXED: Now uses _stream_with_tools for token-by-token output
- [x] #3: Only 15/59 tools reach the LLM — FIXED: Added ToolSearch meta-tool for discovery
- [x] #4: Tool call parsing is fragile — Already handled (multiple parsers exist)
- [x] #8: Model limitations not handled — FIXED: ToolSearch lets model discover tools on demand
- [x] #9: Context window management is naive — FIXED: Auto-compact at 70%, improved summarization
- [x] #13: Skills system is unused — FIXED: Auto-load relevant skills into system prompt
- [x] #14: Computer use is non-functional — FIXED: Wrapped in try/except for missing pyautogui
- [ ] #7: No real end-to-end test
- [ ] #10: No real research capability
- [ ] #11: MCP integration is shallow
- [ ] #12: Free APIs are mostly decorative
- [ ] #15: Code quality — 3,765-line main.py
- [ ] #16: No real undo/redo
- [ ] #17: No real sandboxing
- [ ] #18: Team system is decorative
- [ ] #19: Session management is broken
- [ ] #20: Security is theater
- [ ] #21-30: Missing features
