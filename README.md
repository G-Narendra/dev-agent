# 🚀 Dev Agent

**Free 24/7 AI coding agent powered by NVIDIA NIMs.**

No local GPU required. No API costs. No subscription.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## ⚡ Quick Start (2 minutes)

### Option 1: Install via npm (Recommended)

```bash
npm install -g dev-agent
```

This automatically:
1. Detects Python 3.11+ on your system
2. Creates a virtual environment
3. Installs all dependencies
4. Makes the `narendra` command available globally

### Option 2: Install via pip

```bash
pip install dev-agent
```

### Option 3: Install from source

```bash
git clone https://github.com/dev-agent/dev-agent.git
cd dev-agent
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

pip install -e ".[full]"
```

---

## 🔑 First Run — API Key Setup

When you run `narendra` for the first time, it will **automatically detect** you have no API keys and launch an interactive wizard:

```
$ narendra

🚀 First-Time Setup
┌─────────────────────────────────────────────┐
│ Welcome to Dev Agent!                       │
│ Free 24/7 AI coding agent.                  │
│ No local GPU required. No API costs.        │
│                                             │
│ Let's set up your API keys.                 │
└─────────────────────────────────────────────┘

Get free API keys at: https://build.nvidia.com
Each key gives 40 requests/minute (free tier)
You can use up to 3 keys for 120 RPM total

How many NVIDIA NIM API keys do you have?: 3

Key 1/3:
  Paste your API key #1: ••••••••••••••••
  Verifying key...  ✓ Valid
    Found 8 models

Key 2/3:
  Paste your API key #2: ••••••••••••••••
  Verifying key...  ✓ Valid
    Found 8 models

Key 3/3:
  Paste your API key #3: ••••••••••••••••
  Verifying key...  ✓ Valid
    Found 8 models

✅ Setup Complete!
  Keys configured: 3
  Total RPM: 120
  Config saved: ~/.dev/config.json

Available Models:
┌──────────────────────────────────────┬────────────────────────┬───────────┐
│ Model                                │ Best For               │ Status    │
├──────────────────────────────────────┼────────────────────────┼───────────┤
│ nvidia/llama-3.1-nemotron-70b-instruct│ Coding & reasoning    │ ✅ Available│
│ nvidia/llama-3.1-8b-instruct         │ Fast responses         │ ✅ Available│
│ deepseek-ai/deepseek-r1              │ Deep reasoning & math  │ ✅ Available│
│ qwen/qwen2.5-coder-32b-instruct      │ Code generation        │ ✅ Available│
│ meta/llama-3.1-405b-instruct         │ Largest free model     │ ✅ Available│
└──────────────────────────────────────┴────────────────────────┴───────────┘

Quick Start:
  narendra chat                    # Interactive chat
  narendra run "build a REST API"  # Single task
  narendra --help                  # All commands
```

### Get Your Free API Keys

1. Go to **https://build.nvidia.com**
2. Sign up (free)
3. Click **"Get API Key"**
4. Generate up to **3 keys** (each gives 40 RPM free)

With 3 keys: **120 requests/minute** via round-robin.

---

## 🎯 Usage

### Interactive Chat

```bash
narendra chat
```

### Single Task

```bash
narendra run "build a REST API with FastAPI and SQLite"
narendra run "add user authentication to this project"
narendra run "write tests for the payment module"
```

### Background Worker (24/7 Mode)

```bash
# Start the worker
narendra serve

# Add tasks from another terminal
narendra task add "build landing page"
narendra task add "write tests for auth module"
narendra task add "review PR #42"
```

### Print Mode (Non-Interactive)

```bash
narendra chat -p "explain this codebase"
echo "fix the bug in main.py" | narendra chat -p
```

---

## 🛠️ All Commands

| Command | Description |
|---------|-------------|
| `narendra` | First-run setup wizard (if no keys configured) |
| `narendra setup` | Re-run setup wizard |
| `narendra setup --key <key>` | Add a single key directly |
| `narendra chat` | Interactive chat with streaming |
| `narendra run <prompt>` | Run a single task |
| `narendra serve` | Start 24/7 background worker |
| `narendra first-run` | Run the setup wizard explicitly |
| `narendra models` | List available NVIDIA NIM models |
| `narendra status` | Show status and config |
| `narendra task add/list/cancel` | Manage background tasks |
| `narendra approval set <mode>` | Set approval mode |
| `narendra checkpoint list/undo/redo` | Manage undo checkpoints |
| `narendra team create/add/run` | Manage agent teams |
| `narendra mode set <mode>` | Switch plan/act modes |
| `narendra schedule add/list/cancel` | Manage scheduled agents |
| `narendra connect telegram/slack/discord` | Connect messaging platforms |
| `narendra --version` | Show version |
| `narendra --help` | Show all options |

---

## ⚙️ CLI Flags

### Core Flags

| Flag | Description |
|------|-------------|
| `--model <model>` | NIM model to use |
| `--verbose` | Show detailed output |
| `--max-turns <n>` | Max conversation turns |
| `--approval <mode>` | Approval mode: suggest, auto-edit, full-auto |
| `--bare` | Fast startup: skip loading rules/skills |
| `--plan` | Start in plan mode (read-only) |

### Session Flags

| Flag | Description |
|------|-------------|
| `-p, --print` | Non-interactive: print response and exit |
| `-r, --resume <id>` | Resume session by ID or name |
| `-n, --name <name>` | Session display name |
| `--fork-session` | Create new session ID on resume |
| `--no-session-persistence` | Don't save session to disk |

### System Prompt Flags

| Flag | Description |
|------|-------------|
| `--system-prompt <text>` | Full system prompt override |
| `--system-prompt-file <path>` | Load system prompt from file |
| `--append-system <text>` | Extra system prompt text |

### Tool Flags

| Flag | Description |
|------|-------------|
| `--tools <names>` | Restrict available tools |
| `--allowedTools <names>` | Tools that auto-execute |
| `--disallowedTools <names>` | Tools to deny |
| `--dangerously-skip-permissions` | Skip all permission prompts |

### Output Flags

| Flag | Description |
|------|-------------|
| `--output-format <format>` | Output format: text, json, stream-json |
| `--json` | Output as JSON |
| `--json-schema <schema>` | Validate output against JSON schema |

### Other Flags

| Flag | Description |
|------|-------------|
| `--ref <branch>` | Git branch/ref to checkout |
| `--chrome` | Enable Chrome browser integration |
| `--ide` | Auto-connect to IDE on startup |
| `-y, --yes` | Skip all confirmation prompts |
| `--max-budget-usd <amount>` | Max spend in USD |
| `--fallback-model <model>` | Fallback model if primary fails |
| `--permission-mode <mode>` | Permission mode override |
| `--agents <json>` | Define custom subagents via JSON |
| `--plugin-dir <path>` | Load plugin from directory |
| `--plugin-url <url>` | Fetch plugin from URL |

---

## 🔧 Interactive Chat Commands

When in `narendra chat`, type these slash commands:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/agents` | List available agents |
| `/stats` | Show token/request stats |
| `/cost` | Show cost dashboard |
| `/templates` | List workflow templates |
| `/effort <level>` | Set reasoning effort (low/medium/high) |
| `/detect` | Detect project type |
| `/save` | Save conversation |
| `/history` | List conversations |
| `/fork` | Fork session (save + new) |
| `/clear` | Clear screen |
| `/undo` | Undo last file change |
| `/approve <mode>` | Switch approval mode |
| `/model <name>` | Switch model |
| `/context` | Show context usage |
| `/name <name>` | Name current session |
| `/verbose` | Toggle verbose mode |
| `/plan` | Toggle plan mode |
| `/git` | Show git diff |
| `/doctor` | Run diagnostics |
| `/memory` | Show auto-memory |
| `/compact` | Force context compaction |
| `/quit` | Exit |

---

## 🧠 Available Models

| Model | Best For | Context | Speed |
|-------|----------|---------|-------|
| `nvidia/llama-3.1-nemotron-70b-instruct` | Coding, reasoning | 128K | Medium |
| `nvidia/llama-3.1-8b-instruct` | Fast responses | 128K | Fast |
| `nvidia/llama-3.3-70b-instruct` | Advanced reasoning | 128K | Medium |
| `deepseek-ai/deepseek-r1` | Deep reasoning, math | 128K | Slow |
| `qwen/qwen2.5-coder-32b-instruct` | Code generation | 128K | Fast |
| `qwen/qwen2.5-72b-instruct` | General purpose | 128K | Medium |
| `meta/llama-3.1-405b-instruct` | Largest free model | 128K | Slow |
| `google/gemma-2-27b-it` | Google's free model | 8K | Fast |

---

## 🏗️ Features

### Core

- **Streaming SSE** — Real-time token-by-token output
- **35 Tools** — File I/O, shell, git, web, browser, Docker, MCP, and more
- **Parallel Tool Execution** — Read-only tools run concurrently
- **Approval Modes** — suggest, auto-edit, full-auto
- **Plan Mode** — Read-only exploration mode
- **Undo/Redo** — File-level checkpoints
- **Auto-Commit** — Automatic git commits after changes
- **Auto-Lint** — Code quality checks after edits
- **Context Pruning** — Auto-compact when context fills up
- **Session Persistence** — Resume conversations across restarts
- **Multi-Key Rotation** — Round-robin across multiple API keys

### Advanced

- **MCP Integration** — Connect to any MCP server
- **Browser Automation** — Navigate, click, screenshot
- **Sandboxing** — Execution policies and command filtering
- **Multi-Agent Teams** — Leader/follower agent collaboration
- **Hook System** — Pre/post hooks for any tool
- **Plugin System** — Load custom plugins
- **Auto-Memory** — Learns project patterns automatically
- **Skills System** — Loadable instruction sets
- **Web Dashboard** — REST API for monitoring
- **File Watcher** — Auto-reaction to file changes
- **Error Recovery** — Automatic retry with backoff
- **Budget Tracking** — Token and cost monitoring
- **Tool Rules** — Allow/deny specific tools per project

### Unique (No Other Tool Has These)

- **24/7 Runtime** — Background task queue with persistence
- **Multi-Key Rotation** — Unlimited throughput via key rotation
- **Parallel Tool Execution** — Read-only tools run concurrently
- **Hook System** — Pre/post hooks for any tool
- **Plugin System** — Load custom plugins from directories/URLs
- **Auto-Memory** — Learns project patterns automatically
- **Free APIs Integration** — Access to 100+ free public APIs
- **Git Ref Checkout** — Start from any branch/commit
- **Session Fork** — Branch conversations
- **Dependency Checking** — Auto-detects missing imports

---

## 🔒 Security

Dev Agent has the **strongest security** of any CLI coding tool:

- **Shell injection prevention** — All shell commands use `shlex.quote`
- **Atomic file writes** — Writes go to temp file then rename
- **Process tree kill** — Kills all child processes on exit
- **Symlink protection** — Prevents path traversal via symlinks
- **Device file protection** — Blocks /dev/* writes
- **PATH injection prevention** — Never uses user PATH in subprocesses
- **Env var allowlist** — Only safe env vars passed to subprocesses
- **Budget enforcement** — Hard token/cost limits
- **Tool rules** — Per-project allow/deny lists
- **Config file permissions** — API keys restricted to owner only
- **CRLF normalization** — Prevents line-ending attacks
- **MCP path traversal** — Blocks `../` in MCP server paths
- **Detached HEAD protection** — Prevents commits on detached HEAD
- **Duplicate tool dedup** — Prevents re-execution of same tool call

---

## 📁 Project Structure

```
dev-agent/
├── dev/                    # Main Python package
│   ├── agents/             # Agent definitions and runtime
│   ├── apis/               # Free public API registry (100+ APIs)
│   ├── cli/                # CLI interface (typer)
│   ├── config/             # Configuration system
│   ├── mcp/                # MCP client/server/registry
│   ├── plugins/            # Plugin system
│   ├── providers/          # NVIDIA NIMs provider
│   ├── sandbox/            # Sandboxing and exec policies
│   ├── scheduler/          # 24/7 task queue
│   ├── skills/             # Loadable skill system
│   ├── tools/              # 35 agent tools
│   ├── utils/              # Utilities (first-run, budget, hooks, etc.)
│   └── web/                # Web dashboard
├── bin/                    # npm wrapper scripts
│   └── narendra.js         # Node.js CLI entry point
├── install.js              # npm postinstall script
├── tests/                  # Test suite (54 tests)
├── docs/                   # Documentation
├── skills/                 # Built-in skills
├── .github/workflows/      # CI/CD (GitHub Actions)
├── package.json            # npm package config
├── pyproject.toml          # Python package config
├── LICENSE                 # MIT License
└── README.md               # This file
```

---

## ⚙️ Configuration

Config file: `~/.dev/config.json`

```json
{
  "api_keys": ["nvapi-xxx", "nvapi-yyy", "nvapi-zzz"],
  "rpm": 120,
  "setup_complete": true
}
```

---

## 🆚 Comparison with Other Tools

| Feature | Claude Code | Codex CLI | Aider | Cursor | **Dev Agent** |
|---------|:-----------:|:---------:|:-----:|:------:|:-------------:|
| **Price** | $20/mo | $20/mo | Free* | $20/mo | **FREE** |
| **24/7 Runtime** | ❌ | ❌ | ❌ | ❌ | **✅** |
| **Tool Count** | ~15 | ~10 | ~8 | ~20 | **35** |
| **Parallel Tools** | ❌ | ❌ | ❌ | ❌ | **✅** |
| **MCP Support** | ✅ | ❌ | ❌ | ❌ | **✅** |
| **Browser Automation** | ❌ | ❌ | ❌ | ❌ | **✅** |
| **Sandboxing** | ❌ | ✅ | ❌ | ❌ | **✅** |
| **Multi-Agent Teams** | ❌ | ❌ | ❌ | ❌ | **✅** |
| **Hook System** | ❌ | ❌ | ❌ | ❌ | **✅** |
| **Plugin System** | ❌ | ❌ | ❌ | ❌ | **✅** |
| **Auto-Memory** | ✅ | ❌ | ❌ | ❌ | **✅** |
| **Free APIs** | ❌ | ❌ | ❌ | ❌ | **✅** |
| **Session Fork** | ✅ | ❌ | ❌ | ❌ | **✅** |
| **Git Ref Checkout** | ❌ | ❌ | ❌ | ❌ | **✅** |
| **Multi-Key Rotation** | ❌ | ❌ | ❌ | ❌ | **✅** |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Submit a pull request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [NVIDIA NIMs](https://build.nvidia.com) — Free AI model API
- [Aider](https://github.com/paul-gauthier/aider) — Inspiration for context pruning
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Inspiration for approval modes
- [OpenClaw](https://github.com/openclaw/openclaw) — Inspiration for agent architecture
