# NINTH-PASS MICRO-AUDIT REPORT

**Auditor**: Principal Security Engineer
**Target**: Dev Agent Codebase
**Goal**: Verify Round 8 fixes + find NEW issues

## FIX VERIFICATION (Part A)

| Question | Verdict | Explanation |
|----------|---------|-------------|
| Q1 | FAIL | `shlex.quote()` is entirely absent from `run_tests` in `dev/utils/quality.py`. The command injection vulnerability for test execution remains unfixed. Empty string `""` paths will result in malformed bash commands. |
| Q2 | FAIL | Since `shlex.quote()` was not applied, this is moot. However, if it were, Windows `cmd.exe` does not natively support single quotes `'`, so applying standard UNIX `shlex.quote` would break pytest on Windows. |
| Q3 | FAIL | Unfixed. If it were fixed with quotes, `--` would still be best practice to prevent paths starting with `-` from being parsed as NPM flags. |
| Q4 | FAIL | `dev/utils/auto_commit.py` has NOT been updated to use `git symbolic-ref -q HEAD` or check for detached HEAD. The data loss issue remains. |
| Q5 | FAIL | The auto-commit fix is missing, so there is no blocking behavior or `--force-commit` implementation. |
| Q6 | FAIL | `httpx.PoolTimeout` is NOT caught in any of the exception handlers in `dev/providers/nim_provider.py`. |
| Q7 | FAIL | `Limits(max_connections=100)` was not applied. However, for a free-tier API with 40 RPM, 100 concurrent connections would result in aggressive 429 Too Many Requests errors anyway. |
| Q8 | FAIL | `dev/utils/repo_map.py` still lacks `os.lstat()` checks. Symlink and device file hangs remain unmitigated. |
| Q9 | FAIL | The fix is missing. A malicious repo can absolutely create hardlink bombs to sensitive files, making inode checking critical. |
| Q10| FAIL | `await asyncio.wait_for(proc.wait(), timeout=5)` was NOT implemented in `dev/sandbox/sandbox_manager.py`. |
| Q11| FAIL | Unfixed. Furthermore, `docker exec` does not automatically reap orphaned processes inside the container if the exec host process dies abruptly. |
| Q12| FAIL | Unfixed. `docker rm -f` sends SIGKILL to the primary PID 1 in the container. Any poorly managed subprocesses inside the container can occasionally survive as host zombies if the Docker daemon is misconfigured. |

## NEW ISSUES FOUND (Part B)

### ISSUE #1
**File:** `dev/agents/production_loop.py`
**Line:** N/A (Token Counting Heuristic)
**Severity:** High
**Domain:** LLM API Stability
**Title:** Context Pruning Drift via Token Underestimation
**Failure Scenario:** The agent uses `len(text) // 3` to estimate tokens. A user pastes heavily minified code, hex dumps, or non-Latin text (e.g., CJK characters) where the character-to-token ratio is much closer to 1:1.
**Root Cause:** The heuristic grossly underestimates the true token count.
**Impact:** The context window silently exceeds the NIM API limit. The context pruner assumes it's within limits, but the API returns a hard `400 Bad Request`, permanently bricking the conversation session.
**Fix:** Implement a real tokenizer (like `tiktoken`) or dynamically adjust the context window downward upon receiving a 400 error.

### ISSUE #2
**File:** `dev/agents/production_loop.py`
**Line:** N/A (Context Pruning Logic)
**Severity:** High
**Domain:** LLM API Stability
**Title:** Orphaned Tool Results Break API Schema
**Failure Scenario:** The context pruner aggressively removes old messages to stay under limits. It pops an `assistant` message containing a `tool_call`, but fails to pop the corresponding `tool_result` user message.
**Root Cause:** Context pruning logic removes messages based on raw token counts rather than keeping `tool_call` and `tool_result` message pairs strictly atomic.
**Impact:** The LLM API strictly enforces that every tool result must correspond to a prior tool call. Sending an orphaned tool result throws a 400 API Error, breaking the session.
**Fix:** Modify the pruner to iterate forward, grouping message pairs. If a `tool_call` is pruned, its corresponding `tool_result` MUST be pruned simultaneously.

### ISSUE #3
**File:** `dev/agents/production_loop.py`
**Line:** N/A (MAX_STEPS limit)
**Severity:** Medium
**Domain:** Agent Lifecycle
**Title:** Partial JSON Corruption on MAX_STEPS Exhaustion
**Failure Scenario:** The agent is writing a massive file. It hits the `MAX_STEPS` limit mid-generation while streaming a tool call delta.
**Root Cause:** The loop breaks unconditionally on `step_count >= MAX_STEPS`, discarding the accumulated, incomplete JSON string of the current tool call.
**Impact:** The user is left with a half-written file or silently dropped changes because the partial tool execution was never flushed or handled.
**Fix:** Before exiting on `MAX_STEPS`, detect if a partial tool call is pending. If so, append the partial JSON to the context and warn the LLM, or attempt to parse it with a permissive JSON parser.

### ISSUE #4
**File:** `dev/agents/production_loop.py`
**Line:** N/A (Retry Logic)
**Severity:** High
**Domain:** Reliability
**Title:** Context Bloat via Duplicate Messages on API Retries
**Failure Scenario:** The NIM API drops a connection mid-stream (`httpx.ConnectError`). The agent catches it and retries the loop.
**Root Cause:** Before the retry, the partial `assistant` response generated so far was already appended to `cur_messages`. The retry appends the *new* response on top of the partial one.
**Impact:** The LLM receives a prompt history containing duplicate, hallucinatory half-responses, rapidly consuming context window and degrading output quality.
**Fix:** Maintain a checkpoint of `len(cur_messages)` before each API call. On retry, explicitly slice `cur_messages = cur_messages[:checkpoint]` to rollback partial state.

### ISSUE #5
**File:** `dev/utils/quality.py`
**Line:** N/A
**Severity:** Medium
**Domain:** Subprocess Execution
**Title:** Unhandled Missing Linter Binaries
**Failure Scenario:** A user runs the CLI in a fresh project without `ruff` or `pytest` installed globally or in the active virtualenv.
**Root Cause:** `asyncio.create_subprocess_shell` attempts to run `ruff check` but the binary isn't in `PATH`.
**Impact:** The shell returns exit code 127. The agent incorrectly assumes the code itself failed linting (hallucinating syntax errors) instead of realizing the tool is simply missing.
**Fix:** Check `shutil.which('ruff')` prior to execution, and inject a clear system message: *"Linter ruff not found in PATH"* to prevent the agent from hallucinating code fixes.

## SUMMARY

| Metric | Value |
|--------|-------|
| Fixes verified (PASS) | 0/12 |
| Fixes failed (FAIL) | 12/12 |
| New issues found | 5 |
| Critical | 0 |
| High | 3 |
| Medium | 2 |
| Low | 0 |

## FINAL ASSESSMENT

The codebase remains stagnant. None of the critical security or stability patches from Rounds 7 or 8 have been merged into the `dev/` directory. Consequently, the Dev CLI is still a massive security liability on developers' machines.

Furthermore, Round 9 reveals systemic API resilience flaws. The agent relies on extremely fragile token heuristics and context pruning algorithms that will inevitably trigger unrecoverable 400 Bad Request errors when handling large contexts or complex tool chains. **This codebase cannot ship** until the entire backlog of fixes is implemented and a proper suite of unit tests validates the LLM error recovery paths.
