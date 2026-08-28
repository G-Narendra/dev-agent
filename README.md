# 🚀 Dev Agent (narendra)

**Free 24/7 AI coding agent powered by NVIDIA NIMs**

Build production-ready software with AI — completely free. No credit card, no API costs, no limits.

[![npm version](https://img.shields.io/badge/npm-narendra-blue)](https://www.npmjs.com/package/narendra)
[![Python](https://img.shields.io/badge/python-3.11+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## ⚡ Quick Start

```bash
# Install globally
npm install -g narendra

# Configure API keys (free)
narendra setup

# Start coding
narendra chat
```

## 🎯 What It Does

- **Interactive Chat** — AI-powered coding assistant with streaming output
- **Single Tasks** — `narendra run "build a REST API with Express"`
- **Auto-Commit** — Git integration with AI-generated commit messages
- **Tool Calling** — File editing, shell commands, web search, browser automation
- **31 Tools** — Including computer use, Docker, MCP servers, and more
- **137 Free APIs** — Pre-configured public API integrations
- **57 MCP Servers** — Database, browser, filesystem, and external tool connections
- **465+ Expert Skills** — Domain-specific knowledge for any project type

## 🔑 Free API Keys

Dev Agent uses **3 free providers** for 24/7 operation:

| Provider | Models | Speed | Sign Up |
|----------|--------|-------|---------|
| **NVIDIA NIM** | 80+ models, 40 RPM | ⚡ Fastest | [build.nvidia.com](https://build.nvidia.com) |
| **OpenRouter** | 28+ free models | 🚀 Fast | [openrouter.ai](https://openrouter.ai) |
| **Bytez** | 175K+ models | 🔄 Scale | [bytez.com](https://bytez.com) |

## 📦 Installation

### From npm (recommended)
```bash
npm install -g narendra
```

### From source
```bash
git clone https://github.com/G-Narendra/dev-agent.git
cd dev-agent
python -m venv .venv
.venv/Scripts/pip install -e .
```

## 🎮 Commands

```bash
narendra                          # Interactive chat (default)
narendra chat                     # Interactive chat
narendra run "task"               # Single task mode
narendra setup                    # Configure API keys
narendra models                   # List available models
narendra status                   # Show system status
narendra --version                # Show version
narendra --completion bash        # Generate shell completion
```

### Chat Commands
```
/help          Show all commands
/undo          Undo last file edit
/redo          Redo undone edit
/save          Save conversation
/history       List saved conversations
/cost          Show token usage and cost
/context       Show context window usage
/compact       Compress conversation history
/plan          Toggle plan mode (read-only)
/verbose       Toggle verbose output
/model         Switch AI model
/approve       Change approval mode
/config        Show configuration
/memory        View auto-learned memories
/diff          Show git diff
/commit        Auto-commit changes
/review        AI code review
/security      Security audit
/explain       Explain codebase
/optimize      Performance analysis
/refactor      Refactoring suggestions
/document      Generate documentation
/init          Initialize project config
/debug         Run diagnostics
```

## 🛠️ Tools

| Tool | Description |
|------|-------------|
| `write_file` | Create/replace files |
| `str_replace` | Find & replace in files |
| `read_files` | Read files with line ranges |
| `run_terminal_command` | Execute shell commands |
| `code_search` | Search code with regex |
| `glob` | Find files by pattern |
| `list_directory` | List directory contents |
| `web_search` | Search the web |
| `read_url` | Fetch and read web pages |
| `browser_screenshot` | Take browser screenshots |
| `browser_navigate` | Navigate browser |
| `docker_run` | Run Docker containers |
| `free_api` | Call 137+ free public APIs |
| `mcp_connect` | Connect to MCP servers |
| `spawn_agents` | Create parallel agents |
| `write_todos` | Track task progress |
| `visual_review` | Screenshot + AI review |
| `design_fetch` | Fetch brand design systems |

## 🔧 Configuration

Config stored at `~/.dev/config.json`:

```json
{
  "api_keys": {
    "nvidia": ["nvapi-..."],
    "openrouter": ["sk-or-..."],
    "bytez": ["..."]
  }
}
```

## 📁 Project Structure

```
~/.dev/
├── config.json          # API keys and settings
├── sessions/            # Saved chat sessions
├── conversations/       # Conversation history
├── checkpoints/         # File edit undo/redo
├── memory/              # Auto-learned memories
└── logs/                # Agent logs
```

## 🎨 Skills

Dev Agent includes 465+ expert skills organized by role:

- **Frontend Engineer** — React, Vue, Angular, CSS, responsive design
- **Backend Engineer** — Node.js, Python, Go, Rust, APIs
- **DevOps Engineer** — Docker, CI/CD, deployment, monitoring
- **Security Engineer** — Penetration testing, code review, compliance
- **Data Engineer** — SQL, ETL, analytics, machine learning
- **Product Manager** — PRDs, user stories, roadmaps
- **And 450+ more...**

## 🏗️ Architecture

```
dev/
├── agents/           # Agent loop, compaction, teams
├── apis/             # 137+ free API integrations
├── cli/              # CLI commands and TUI
├── config/           # Configuration management
├── mcp/              # MCP server integration
├── providers/        # NVIDIA NIM, OpenRouter, Bytez
├── sandbox/          # Command sandboxing
├── security/         # Injection detection, audit logging
├── skills/           # 465+ expert skill definitions
├── tools/            # 31 tool implementations
└── utils/            # Shared utilities
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `python -m pytest tests/ -q`
5. Submit a pull request

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

Built with inspiration from:
- [Claude Code](https://claude.ai) — Tool calling and streaming patterns
- [Freebuff](https://freebuff.com) — CLI architecture and TUI design
- [Aider](https://aider.chat) — Context management and repo mapping
- [OpenClaw](https://openclaw.ai) — Compaction engine patterns
- [Codex CLI](https://github.com/openai/codex) — Loop safety patterns

---

**Made with ❤️ by G-Narendra**
