# TENTH-PASS MICRO-AUDIT REPORT

**Auditor**: Principal Security Engineer
**Target**: Dev Agent Codebase
**Goal**: Verify Round 9 fixes + find NEW issues

## FIX VERIFICATION (Part A)

| Question | Verdict | Explanation |
|----------|---------|-------------|
| Q1 | FAIL | The dynamic token adjustment fix (`max_context_tokens` shrinking) is entirely absent from `dev/agents/production_loop.py`. The agent will continue to crash loop on 400 Context Limit errors. |
| Q2 | FAIL | The aggressive pruning logic is missing. The system prompt size is never checked against the reduced limit, which would cause an infinite loop of 400 errors if it were implemented. |
| Q3 | FAIL | Unfixed. If it were implemented as described, continuing without recomputing `msg_dicts` would result in an immediate repeat of the 400 error due to stale state. |
| Q4 | FAIL | `_truncate_to_fit` still uses raw token removal. Orphaned tool calls remain a critical API validation issue. |
| Q5 | FAIL | The `id` matching logic is missing. |
| Q6 | FAIL | `MAX_STEPS` partial JSON detection was never implemented. |
| Q7 | FAIL | Since `warning` is not returned, it is never handled or displayed by `main.py`. |
| Q8 | FAIL | `msg_checkpoint` logic is missing from `dev/agents/production_loop.py`. Duplicate messages on API retries will still pollute the context. |
| Q9 | FAIL | Missing implementation. |
| Q10| FAIL | `shutil.which()` checks were never added to `dev/utils/quality.py`. Missing linter binaries will still cause hallucinations. |
| Q11| FAIL | Unfixed. If implemented via `.split()[0]`, `python -m ruff` would falsely validate `python` instead of checking for `ruff`. |
| Q12| FAIL | `run_tests` remains unchecked. |
| Q13| FAIL | Not applicable since no code was actually modified. |
| Q14| FAIL | The token heuristic remains untouched and highly inaccurate for dense text. |
| Q15| FAIL | The proportional threshold shrinking is absent. |

## NEW ISSUES FOUND (Part B)

### ISSUE #1
**File:** `dev/agents/production_loop.py`
**Line:** N/A (Auto-Compact Logic)
**Severity:** High
**Domain:** Prompt Injection / Context Integrity
**Title:** Context Summarization injected as User Instructions
**Failure Scenario:** The agent compacts an old conversation and injects the summary as a `role="user"` message. 
**Root Cause:** The `_auto_compact_if_needed` method incorrectly maps AI-generated historical summaries to the `user` role.
**Impact:** The LLM interprets the historical summary of its past actions as a direct, imperative command from the user for its *current* action, completely derailing the execution flow and leading to infinite loops or incorrect file edits.
**Fix:** Inject summaries as `role="system"` or use a clearly demarcated block within an `assistant` message.

### ISSUE #2
**File:** `dev/agents/production_loop.py`
**Line:** N/A (Message Dictionary Conversion)
**Severity:** Medium
**Domain:** LLM API Validation
**Title:** API Rejection on Hybrid Content/Tool-Call Messages
**Failure Scenario:** The LLM generates a response that contains both textual `content` and a `tool_calls` array.
**Root Cause:** The `_messages_to_dicts` method blindly passes through both fields if they exist in the Message object.
**Impact:** While some models tolerate this, many strict LLM APIs (and certain NIM endpoints) throw a `400 Bad Request` if a message contains both a non-null string content and tool calls simultaneously, breaking the session.
**Fix:** If `tool_calls` are present, either strip the `content` or ensure the target API explicitly supports hybrid messages before sending.

### ISSUE #3
**File:** `dev/sandbox/sandbox_manager.py`
**Line:** N/A (Environment Allowlist)
**Severity:** Critical
**Domain:** Sandbox Escape / Code Execution
**Title:** Untrusted PATH Injection via Environment
**Failure Scenario:** An attacker creates a repository with a `.env` or project config that prepends an attacker-controlled directory to `PATH`. The agent executes a sandboxed command like `git` or `npm`.
**Root Cause:** If `PATH` is blindly allowed through the `_execute_sandboxed` allowlist without validation, the sandboxed environment inherits the modified `PATH`.
**Impact:** The agent executes a malicious binary (e.g., a fake `npm`) planted by the attacker instead of the system binary, leading to arbitrary code execution inside the agent's host environment.
**Fix:** Explicitly sanitize and hardcode the `PATH` in the sandbox environment to safe system defaults (e.g., `/usr/bin:/bin`) rather than passing it through from the user's potentially tainted environment.

### ISSUE #4
**File:** `dev/agents/production_loop.py`
**Line:** N/A (Rule Loading)
**Severity:** Medium
**Domain:** Configuration Management
**Title:** Conflicting Rule Precedence
**Failure Scenario:** A repository has a `DEV.md` stating "Use Python 3.8 typing" and a `.devrules/python.md` stating "Use Python 3.10+ typing". 
**Root Cause:** The `_build_system_prompt` simply concatenates rule files without establishing a clear hierarchy or override mechanism.
**Impact:** The LLM becomes confused by contradictory instructions in the system prompt, oscillating between patterns or breaking build pipelines by using the wrong conventions.
**Fix:** Enforce a strict merge order (e.g., `.devrules` overrides `DEV.md`), and explicitly instruct the LLM on which block takes precedence in the event of a conflict.

### ISSUE #5
**File:** `dev/providers/nim_provider.py`
**Line:** N/A (Key Rotation)
**Severity:** High
**Domain:** Error Handling / UX
**Title:** Unhandled Key Exhaustion Deadlock
**Failure Scenario:** The user configures two NIM API keys. Both keys hit their rate limits simultaneously.
**Root Cause:** The `_wait_for_available_key` method checks for availability, but lacks a backoff circuit breaker if all keys are globally exhausted for an extended period.
**Impact:** The agent may enter an aggressive busy-loop or an infinite async wait without notifying the user, effectively deadlocking the CLI while appearing to be "thinking".
**Fix:** Implement a global timeout for key exhaustion. If no key becomes available within 60 seconds, raise a specific `RateLimitExhaustedException` and exit gracefully with a user-facing error message.

## SUMMARY

| Metric | Value |
|--------|-------|
| Fixes verified (PASS) | 0/15 |
| Fixes failed (FAIL) | 15/15 |
| New issues found | 5 |
| Critical | 1 |
| High | 3 |
| Medium | 1 |
| Low | 0 |

## FINAL ASSESSMENT

The security posture of this codebase remains abysmal. For the fourth consecutive audit round, critical fixes (Token pruning, Checkpoint rollback, Linter validation) were entirely absent from the active codebase. 

Furthermore, this 10th round has exposed systemic architecture flaws regarding Prompt Injection (historical summaries mapped to user roles), Sandbox PATH hijacking, and API Key exhaustion deadlocks. **This agent is unsafe for local execution on developer machines** and will fail spectacularly under production workloads until the backlog of fixes is genuinely committed to the repository.
