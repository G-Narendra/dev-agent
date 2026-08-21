# FOURTH-PASS MICRO-AUDIT REPORT

**Auditor**: Staff SRE
**Target**: Dev Agent Codebase
**Goal**: 15+ NEW Deep Failure Domain Issues (Fourth Audit)

---

### DEEP ISSUE #1
**File:** `dev/utils/history.py`
**Domain:** Security
**Severity:** Critical
**Title:** Conversation history saved with world-readable permissions (0644)

**Failure Scenario:**
On a shared Linux/macOS server, the agent saves conversation history to `~/.dev/conversations/`. Because the files are created with default `umask` (022), the resulting JSON files are readable by any other user on the system (0644).
**Root Cause:**
The agent does not explicitly set `os.chmod` when writing session JSON files, which often contain pasted API keys, proprietary code, or passwords.
**Impact:**
Massive credential and IP exfiltration risk in shared environments.
**Fix:**
```python
# Before
        with open(temp_fpath, "w", encoding="utf-8") as f:

# After
        import stat
        # Create with strict permissions (0600)
        fd = os.open(temp_fpath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
```
**Verification:**
Run the agent, check `ls -l ~/.dev/conversations/`, and assert permissions are `-rw-------`.

---

### DEEP ISSUE #2
**File:** `dev/utils/git_auto.py`
**Domain:** Security
**Severity:** High
**Title:** Auto-commit tracks and uploads sensitive files

**Failure Scenario:**
The user accidentally creates a `.env` file but forgets to add it to `.gitignore`. The agent edits a python file. The `auto_commit` feature runs `git add .` or `git commit -am`.
**Root Cause:**
The agent blindly commits all working tree changes. This bypasses the developer's manual review of staged files, immediately permanently embedding the `.env` API keys into the Git history.
**Impact:**
Automated credential leakage into version control.
**Fix:**
```python
# Before
        subprocess.run(["git", "add", "."], check=True)

# After
        # Only add files that the agent specifically modified in this turn
        for edited_file in self._state.edited_files:
            subprocess.run(["git", "add", edited_file], check=True)
```
**Verification:**
Create an untracked `.env` file, let the agent edit a different file, assert `.env` is not committed.

---

### DEEP ISSUE #3
**File:** `dev/agents/production_loop.py`
**Domain:** LLM Response
**Severity:** High
**Title:** Unregistered tool hallucination causes `KeyError` loop crash

**Failure Scenario:**
The LLM hallucinates a tool call that doesn't exist in the registry (e.g., `name: "read_database"`). 
**Root Cause:**
The loop extracts `tool_name`, passes the approval check (which returns allowed for unknown tools by default), and calls `await self._execute_tool(tool_name, ...)`, which attempts a dictionary lookup `self.tools[tool_name]`, throwing an unhandled `KeyError`.
**Impact:**
Agent loop crashes completely instead of telling the LLM the tool is invalid.
**Fix:**
```python
# Before
        result = await self._execute_tool(tool_name, tool_args)

# After
        if tool_name not in self.tools:
            return {"error": f"Tool '{tool_name}' does not exist. Available tools: {list(self.tools.keys())}"}
        result = await self._execute_tool(tool_name, tool_args)
```
**Verification:**
Mock the LLM to return `fake_tool`, assert agent returns a JSON error to the LLM and continues.

---

### DEEP ISSUE #4
**File:** `dev/utils/context_pruner.py`
**Domain:** Context
**Severity:** High
**Title:** Heuristic `_count_tokens` underestimates dense code by 60%

**Failure Scenario:**
The agent reads a minified JS file or a base64 string. The `_count_tokens` heuristic uses `len(text) / 4`. Minified code or hex dumps have extremely high token density (often 1 char = 1 token).
**Root Cause:**
The agent thinks the 100K char string is 25K tokens, perfectly fitting the 32K context window. It sends it to the NIM API, which calculates it as 80K tokens and immediately returns HTTP 400 Context Length Exceeded.
**Impact:**
Unrecoverable death spiral on dense text files.
**Fix:**
```python
# Before
        return len(text) // 4

# After
        # Better heuristic for non-whitespace heavy text, or use actual tokenizer (tiktoken)
        import re
        if not re.search(r'\s', text[:1000]): # Dense text detection
            return len(text) // 2
        return len(text) // 4
```
**Verification:**
Feed a 50KB base64 string, assert the token counter weights it heavily and triggers compaction early.

---

### DEEP ISSUE #5
**File:** `dev/utils/history.py`
**Domain:** Memory
**Severity:** High
**Title:** OOM via unbounded `Conversation` history object

**Failure Scenario:**
The agent runs continuously for 3 weeks, executing 10,000 tool calls. The context window is kept small by the `context_pruner`, but `history.py` keeps *every single message* in the `Conversation.messages` list in RAM to save it to disk.
**Root Cause:**
The disk-save state is strictly appending to a memory list that never gets pruned.
**Impact:**
The Python process grows to 4GB+ RAM and is eventually killed by the OS OOM killer.
**Fix:**
```python
# Before
        self.messages.extend(new_messages)

# After
        self.messages.extend(new_messages)
        # Cap full history at 5000 messages (or stream it to disk incrementally)
        if len(self.messages) > 5000:
            self.messages = self.messages[-5000:]
```
**Verification:**
Push 100,000 mock messages into the conversation, assert RAM usage stays flat.

---

### DEEP ISSUE #6
**File:** `dev/utils/repo_map.py`
**Domain:** Context
**Severity:** Medium
**Title:** Unbounded repo map generation for `node_modules`

**Failure Scenario:**
The agent starts in a JavaScript monorepo without a proper `.gitignore` or with a massive nested folder structure. `repo_map.py` traverses 50,000 files.
**Root Cause:**
`os.walk` builds a massive tree string. The resulting string is 5MB. When injected into the system prompt, it instantly blows out the context window before the user even types a message.
**Impact:**
Immediate context death spiral on startup for large repos.
**Fix:**
```python
# Before
        for root, dirs, files in os.walk(project_path):

# After
        MAX_FILES = 2000
        file_count = 0
        for root, dirs, files in os.walk(project_path):
            file_count += len(files)
            if file_count > MAX_FILES:
                tree_string += f"\n... [Truncated: Too many files ({file_count}+)] ..."
                break
```
**Verification:**
Run `repo_map` on a directory with 10,000 dummy files, assert output is capped.

---

### DEEP ISSUE #7
**File:** `dev/tools/real_tools.py`
**Domain:** Filesystem
**Severity:** Medium
**Title:** Uncaught `PermissionError` on `read_files`

**Failure Scenario:**
The agent is asked to read `/etc/shadow` or a file owned by root in the workspace. 
**Root Cause:**
`open(abs_path, "r")` throws `PermissionError`. The tool does not catch this specific exception, which either crashes the tool execution loop or returns a generic Python stack trace to the LLM instead of a clean error.
**Impact:**
Agent crashes or wastes tokens on stack traces.
**Fix:**
```python
# Before
        with open(abs_path, "r", encoding="utf-8") as f:

# After
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except PermissionError:
            results.append({"path": file_path, "error": "Permission denied. Run with elevated privileges."})
            continue
```
**Verification:**
`chmod 000 test.txt` and run `read_files` on it, assert clean error JSON.

---

### DEEP ISSUE #8
**File:** `dev/agents/production_loop.py`
**Domain:** Concurrency
**Severity:** Medium
**Title:** `history.save_conversation` blocking I/O freezes agent

**Failure Scenario:**
The `Conversation.messages` list grows to 20MB of JSON. The agent calls `save_conversation()` at the end of a turn.
**Root Cause:**
`json.dump()` and `f.write()` are completely synchronous and block the asyncio event loop for 1-2 seconds while writing to disk.
**Impact:**
Background tasks (like MCP heartbeat, API stream readers) stall, causing disconnects and choppy terminal UI updates.
**Fix:**
```python
# Before
        history.save_conversation(self._state.conv)

# After
        await asyncio.to_thread(history.save_conversation, self._state.conv)
```
**Verification:**
Save a 50MB conversation and assert that a background async timer does not skip a beat.

---

### DEEP ISSUE #9
**File:** `dev/providers/nim_provider.py`
**Domain:** Network
**Severity:** Medium
**Title:** `httpx.ConnectError` on DNS failure crashes agent

**Failure Scenario:**
The user is on a train or VPN, and DNS resolution for `integrate.api.nvidia.com` temporarily fails.
**Root Cause:**
The retry block explicitly catches `httpx.HTTPStatusError` and `httpx.TimeoutException`, but misses `httpx.ConnectError` (raised for DNS failures).
**Impact:**
The loop crashes instantly instead of applying the robust 429/timeout exponential backoff.
**Fix:**
```python
# Before
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:

# After
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError) as e:
```
**Verification:**
Disable network adapter, run agent, assert it enters the retry loop instead of crashing.

---

### DEEP ISSUE #10
**File:** `dev/tools/browser_tools.py`
**Domain:** Tool Chain
**Severity:** Medium
**Title:** `browser_click` race condition with page load

**Failure Scenario:**
The LLM calls `browser_navigate` to `example.com`. In the very next tool call, it calls `browser_click` on `#submit`. 
**Root Cause:**
If `browser_navigate` returns success immediately upon receiving the HTML, client-side React/Vue rendering hasn't finished. `browser_click` fails because `#submit` doesn't exist yet.
**Impact:**
Agent gets stuck in a loop of failed clicks and gives up on web automation tasks.
**Fix:**
```python
# Before
        await page.goto(url)

# After
        await page.goto(url, wait_until="networkidle")
        # OR add explicit wait in click tool
        await page.locator(selector).wait_for(state="visible", timeout=5000)
```
**Verification:**
Navigate to a heavy SPA and click a lazy-loaded element, assert it waits instead of failing instantly.

---

### DEEP ISSUE #11
**File:** `dev/utils/auto_memory.py`
**Domain:** Memory
**Severity:** Low
**Title:** `memory.json` unbounded growth slows down prompt

**Failure Scenario:**
The agent runs for months on a project. Every time it learns a new rule, it appends to `memory.json`. The file reaches 500 rules.
**Root Cause:**
`memory.json` is fully injected into the system prompt on every turn. 500 rules consume 15,000 tokens of the context window permanently.
**Impact:**
Context starvation (the "death spiral") caused by the agent's own memory system.
**Fix:**
```python
# Before
        self.rules.append(new_rule)

# After
        self.rules.append(new_rule)
        if len(self.rules) > 50:
            # Trigger an LLM summarization of rules, or FIFO eviction
            self.rules = self._summarize_rules(self.rules)
```
**Verification:**
Add 100 rules, assert the memory manager compresses or rejects further additions without pruning.

---

### DEEP ISSUE #12
**File:** `dev/tools/real_tools.py` (run_terminal_command)
**Domain:** Cross-Platform
**Severity:** Low
**Title:** Shell defaults to `cmd.exe` breaking Bash scripts on Windows

**Failure Scenario:**
A Windows developer uses the agent in Git Bash. The agent decides to run `ls -la` or `./script.sh`. 
**Root Cause:**
`asyncio.create_subprocess_shell` defaults to `cmd.exe` on Windows. `cmd.exe` does not understand `ls` or `./script.sh`, causing immediate tool failure.
**Impact:**
Agent fails to navigate or execute scripts on Windows unless explicitly prepended with `bash -c`.
**Fix:**
```python
# Before
        proc = await asyncio.create_subprocess_shell(cmd)

# After
        import os
        shell_cmd = cmd
        if os.name == 'nt' and ('bash' in os.environ.get('SHELL', '').lower() or cmd.startswith('./')):
            shell_cmd = f"bash -c {shlex.quote(cmd)}"
        proc = await asyncio.create_subprocess_shell(shell_cmd)
```
**Verification:**
Run agent on Windows, ask it to `ls`, assert it uses bash if available or translates it.

---

### DEEP ISSUE #13
**File:** `dev/tools/real_tools.py`
**Domain:** Tool Chain
**Severity:** Low
**Title:** `str_replace` fails entirely if target spans lines unexpectedly

**Failure Scenario:**
The LLM reads a file formatted with CRLF (`\r\n`). The LLM generates the `oldString` replacement block using just `\n`. 
**Root Cause:**
Python's `content.count(oldString)` strictly checks character-for-character. The mismatch in line endings causes a 0-match, and the tool errors out. The LLM gets confused and tries repeatedly with slight whitespace variations.
**Impact:**
Massive token waste as the agent gets stuck in a loop trying to apply an edit.
**Fix:**
```python
# Before
        count = content.count(old)

# After
        # Normalize line endings before comparison
        normalized_content = content.replace('\r\n', '\n')
        normalized_old = old.replace('\r\n', '\n')
        if normalized_content.count(normalized_old) > 0:
            # apply replacement safely ...
```
**Verification:**
Create a CRLF file, pass LF replacement string, assert the replacement succeeds.

---

### DEEP ISSUE #14
**File:** `dev/mcp/client.py`
**Domain:** Filesystem
**Severity:** Low
**Title:** Project path traversal in MCP server configurations

**Failure Scenario:**
The `mcp.json` config specifies a local server script path: `"command": "node", "args": ["../malicious_server.js"]`.
**Root Cause:**
The MCP client blindly trusts the paths provided in the workspace `mcp.json`. If a user downloads a repository containing this file, the agent will execute the script outside the workspace bounds.
**Impact:**
Sandbox escape / arbitrary code execution via configuration file.
**Fix:**
```python
# Before
        command = server_config["command"]
        args = server_config.get("args", [])

# After
        # Validate that local script paths in args remain within project bounds
        for i, arg in enumerate(args):
            if arg.endswith('.js') or arg.endswith('.py'):
                abs_arg = os.path.abspath(os.path.join(self.project_path, arg))
                if not abs_arg.startswith(self.project_path):
                    raise PermissionError(f"MCP server script {arg} escapes workspace")
```
**Verification:**
Add `../script.js` to `mcp.json`, assert client refuses to boot it.

---

### DEEP ISSUE #15
**File:** `tests/test_cli.py`
**Domain:** Test Gap
**Severity:** Low
**Title:** No testing for Piped/Headless usage (CI/CD)

**Failure Scenario:**
A developer uses the agent in a GitHub Action: `cat instructions.txt | dev run`. 
**Root Cause:**
The Rich console uses terminal detection. Piped environments lack a TTY. There are 0 integration tests verifying that `main.py` degrades gracefully without crashing when `sys.stdin.isatty()` is False.
**Impact:**
Agent crashes or outputs unreadable ANSI garbage in CI/CD logs.
**Fix:**
```python
# Add test:
def test_headless_pipe_execution():
    # Use subprocess.run to pipe text into the CLI
    # Assert return code 0 and plain text output (no ANSI)
```
**Verification:**
Run `echo "test" | python -m dev.cli.main` and ensure a clean, successful execution.
