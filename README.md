# 🚀 Dev Agent

**The world's first free, open-source AI coding agent with 140+ free APIs, 65+ MCP servers, and 1500+ skills — powered by NVIDIA NIMs.**

Build production-ready software with AI — completely free. No credit card, no API costs, no limits.

[![npm version](https://img.shields.io/badge/npm-narendra-blue)](https://www.npmjs.com/package/narendra)
[![Python](https://img.shields.io/badge/python-3.11+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-282%20passing-brightgreen)](tests/)
[![Code](https://img.shields.io/badge/code-48K%2B%20lines-blue)](dev/)

---

## ⚡ Quick Start

```bash
# Install globally via npm
npm install -g narendra

# Configure API keys (free, takes 2 minutes)
narendra setup

# Start building
narendra chat                    # Interactive chat
narendra run "build a REST API"  # Single task
narendra --help                  # All commands
```

### From Source

```bash
git clone https://github.com/G-Narendra/dev-agent.git
cd dev-agent
python -m venv .venv
.venv/Scripts/pip install -e .
.venv/Scripts/python.exe -m dev setup
.venv/Scripts/python.exe -m dev chat
```

---

## 🎯 What It Does

Dev Agent is a **CLI coding agent** that runs in your terminal and helps you build software using AI. It can:

| Capability | Description |
|-----------|-------------|
| **💬 Interactive Chat** | Streaming AI conversations with tool calling |
| **⚡ Single Tasks** | `narendra run "build a REST API with Express"` |
| **🔄 24/7 Operation** | Background workers that run continuously |
| **🛠️ 31+ Tools** | File editing, shell commands, web search, browser automation |
| **🔌 140+ Free APIs** | Weather, maps, news, finance, translation, and more |
| **📡 65+ MCP Servers** | Database, browser, filesystem, GitHub, and external tool connections |
| **🎯 1500+ Skills** | Domain-specific knowledge for any project type |
| **🔒 7 Security Layers** | Injection detection, sandboxing, encryption, rate limiting |
| **🤖 Multi-Agent Teams** | Parallel agents for complex tasks |
| **📋 Auto-Commit** | Git integration with AI-generated commit messages |
| **🔍 Code Review** | AI-powered review of recent changes |
| **🚀 Deploy** | One-command deployment to Vercel/Netlify/Railway |

---

## 🔑 Free API Keys (3 Providers)

Dev Agent uses **3 free providers** for 24/7 operation. Each gives you different strengths:

| Provider | Models | Speed | Free Tier | Sign Up |
|----------|--------|-------|-----------|---------|
| **NVIDIA NIM** | 80+ models (Llama, Nemotron) | ⚡ Fastest | 40 RPM per key | [build.nvidia.com](https://build.nvidia.com) |
| **OpenRouter** | 28+ free models (Qwen, Kimi) | 🚀 Fast | Generous limits | [openrouter.ai](https://openrouter.ai) |
| **Bytez** | 175K+ models | 🔄 Scale | No credit card | [bytez.com](https://bytez.com) |

### Setup

```bash
# Interactive setup wizard
narendra setup

# Or add keys individually
narendra login --provider nvidia --key "nvapi-..."
narendra login --provider openrouter --key "sk-or-..."
narendra login --provider bytez --key "..."

# Verify keys
narendra auth-status
narendra validate
```

---

## 📦 Installation

### Option 1: npm (Recommended)

```bash
npm install -g narendra
narendra setup        # Configure API keys
narendra chat         # Start coding
```

### Option 2: From Source

```bash
git clone https://github.com/G-Narendra/dev-agent.git
cd dev-agent
python -m venv .venv

# Windows
.venv\Scripts\pip install -e .

# macOS/Linux
.venv/bin/pip install -e .

.venv/bin/python -m dev setup
.venv/bin/python -m dev chat
```

### Shell Completion

```bash
# Bash
narendra --install-completion

# Fish
narendra --install-completion --shell fish

# Zsh
narendra --install-completion --shell zsh
```

---

## 🎮 CLI Commands (92)

### Core Commands

| Command | Description |
|---------|-------------|
| `narendra` | Start interactive chat (default) |
| `narendra chat` | Interactive chat with streaming |
| `narendra run "task"` | Run a single task |
| `narendra setup` | Configure API keys |
| `narendra --version` | Show version |
| `narendra --help` | Show all commands |

### Session Management

| Command | Description |
|---------|-------------|
| `narendra sessions` | List all saved sessions |
| `narendra resume <id>` | Resume a specific session |
| `narendra fork <id>` | Fork a session into a new branch |
| `narendra stop <id>` | Stop a background session |
| `narendra respawn <id>` | Restart a stopped session |
| `narendra rm <id>` | Remove a session |
| `narendra logs <id>` | Print session output |
| `narendra conversations` | Manage saved conversations |
| `narendra search-sessions` | Search sessions by name/content |

### Agent Control

| Command | Description |
|---------|-------------|
| `narendra mode-set <mode>` | Set approval mode (suggest/auto-edit/full-auto) |
| `narendra mode-get` | Show current approval mode |
| `narendra effort <level>` | Set reasoning effort (low/medium/high) |
| `narendra models` | List available models |
| `narendra status` | Show system status |
| `narendra validate` | Validate configuration and API keys |

### Code Quality

| Command | Description |
|---------|-------------|
| `narendra commit` | Auto-commit with AI-generated message |
| `narendra branch` | Create/switch branches |
| `narendra git-diff` | Show colored git diff |
| `narendra review` | AI code review |
| `narendra ultrareview` | Deep PR review |
| `narendra batch` | Parallel worktree branches |

### Deployment

| Command | Description |
|---------|-------------|
| `narendra deploy` | Deploy to Vercel/Netlify/Railway |
| `narendra ci` | Generate CI/CD workflows |
| `narendra gitlab-ci` | Generate GitLab CI pipeline |
| `narendra pr create` | Create pull request |
| `narendra issue create` | Create GitHub issue |

### Tools & Skills

| Command | Description |
|---------|-------------|
| `narendra tools-list` | List all available tools |
| `narendra skill <name>` | Run a built-in skill |
| `narendra skills-list` | List all built-in skills |
| `narendra hooks` | Manage pre/post hooks |
| `narendra tool-rules` | Manage tool allow/deny rules |
| `narendra plugin-install` | Install a plugin |

### MCP & Connectors

| Command | Description |
|---------|-------------|
| `narendra mcp` | Configure MCP servers |
| `narendra plugins-list` | List available plugins |
| `narendra connect` | Connect messaging platforms |

### Background Operations

| Command | Description |
|---------|-------------|
| `narendra task` | Manage background tasks |
| `narendra serve` | Start 24/7 background worker |
| `narendra daemon` | Manage background supervisor |
| `narendra agents` | Monitor parallel sessions |
| `narendra team` | Manage agent teams |
| `narendra schedule` | Manage scheduled agents |

### Configuration

| Command | Description |
|---------|-------------|
| `narendra config` | Manage configuration |
| `narendra settings` | Manage hierarchical settings |
| `narendra init` | Initialize Dev in a project |
| `narendra purge` | Remove all Dev state |
| `narendra doctor` | Full diagnostic check |
| `narendra update` | Check for updates |

### Memory & Learning

| Command | Description |
|---------|-------------|
| `narendra memory` | Manage auto-learned memories |
| `narendra powerup` | Interactive learning system |
| `narendra plan` | Manage execution plans |

---

## 💬 Chat Slash Commands (95)

When in interactive chat mode (`narendra chat`), type `/` to access slash commands:

### Session Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/quit` or `/exit` | Exit chat |
| `/new` | Start fresh conversation |
| `/restart` | Restart session preserving config |
| `/clear` | Clear screen |
| `/save` | Save conversation |
| `/history` | List saved conversations |
| `/fork` | Fork session into new branch |
| `/copy` | Copy last response to clipboard |
| `/export` | Export session to file |
| `/context` | Show context window usage |
| `/snapshot` | Save project state to git stash |
| `/restore` | List stashes for restore |
| `/version` | Show version info |

### Agent Control Commands

| Command | Description |
|---------|-------------|
| `/plan` | Toggle plan mode (read-only) |
| `/approve` | Approve plan from /plan mode |
| `/skip` | Skip current step |
| `/retry` | Retry last action |
| `/model` | Show/switch AI model |
| `/effort <level>` | Set reasoning effort (low/medium/high) |
| `/deepthink` | Activate deep reasoning mode |
| `/verbose` | Toggle verbose output |
| `/compact` | Compress conversation context |
| `/permissions` | Show/edit permissions |
| `/config` | Show configuration |
| `/personality` | Change communication style |

### Output Mode Commands

| Command | Description |
|---------|-------------|
| `/ghost` | Pure output, no meta-commentary |
| `/raw` | Plain text output |
| `/statusline` | Customize footer status |

### File Operation Commands

| Command | Description |
|---------|-------------|
| `/undo` | Undo last file edit |
| `/redo` | Redo undone edit |
| `/diff` | Show colored git diff |
| `/commit` | Commit all changes |
| `/mention <file>` | Attach file to conversation |

### Git Commands

| Command | Description |
|---------|-------------|
| `/git <args>` | Run git commands (status, log, etc.) |
| `/branch` | List/create/switch branches |
| `/worktree` | Manage git worktrees |

### Code Quality Commands

| Command | Description |
|---------|-------------|
| `/test` | Run project tests |
| `/testit` | Write tests for code |
| `/lint` | Run linter |
| `/review` | AI code review |
| `/explain` | Explain project structure |
| `/debug` | Find bugs in code |
| `/refactor` | Find refactoring opportunities |
| `/architect` | Design system structure |
| `/document` | Generate documentation |
| `/optimize` | Performance analysis |
| `/security` | Security audit |
| `/code-review` | Deep code review |
| `/security-review` | Deep security review |
| `/verify` | Verify changes |

### Web & Research Commands

| Command | Description |
|---------|-------------|
| `/web <query>` | Force web search before answering |
| `/search` | Search the web |

### Project Commands

| Command | Description |
|---------|-------------|
| `/detect` | Detect project type |
| `/rules` | Show project rules |
| `/doctor` | Run diagnostics |
| `/deps` | Check dependency status |
| `/env` | Show environment variables |
| `/schema` | Analyze database schema |
| `/migrate` | Check migration needs |
| `/docs` | Show documentation |
| `/init` | Initialize project config |

### Connector & Plugin Commands

| Command | Description |
|---------|-------------|
| `/apps` | Browse available connectors |
| `/plugins` | Manage plugins |
| `/mcp` | List/configure MCP servers |

### Information Commands

| Command | Description |
|---------|-------------|
| `/stats` | Show token/request stats |
| `/cost` | Show cost dashboard |
| `/usage` | Show usage statistics |
| `/agents` | List available agents |
| `/templates` | List workflow templates |
| `/memory` | Show auto-learned rules |
| `/remember` | Save a learning |
| `/forget` | Remove a learning |
| `/insights` | Show session insights |
| `/feedback` | Submit feedback |

### Custom Commands

Create your own commands by adding markdown files:

```bash
# Project-level (shared with team)
mkdir -p .dev/commands
echo "# Ship\nReview diff. Run tests. Commit. Push." > .dev/commands/ship.md

# User-level (personal)
mkdir -p ~/.dev/commands
echo "# Deploy\nBuild. Test. Deploy." > ~/.dev/commands/deploy.md
```

Then use them: `/ship`, `/deploy`

---

## 🛠️ Tools (31+)

Dev Agent has access to these tools during conversations:

### File Operations

| Tool | Description |
|------|-------------|
| `write_file` | Create or replace a file |
| `str_replace` | Find and replace text in files |
| `read_files` | Read files with line ranges |
| `glob` | Find files by pattern |
| `list_directory` | List directory contents |

### Code Search

| Tool | Description |
|------|-------------|
| `code_search` | Search code with regex (ripgrep) |
| `tool_search` | Search for available tools |

### Terminal

| Tool | Description |
|------|-------------|
| `run_terminal_command` | Execute shell commands |
| `spawn_agents` | Create parallel sub-agents |

### Web

| Tool | Description |
|------|-------------|
| `web_search` | Search the web (DuckDuckGo) |
| `read_url` | Fetch and read web pages |
| `free_api` | Call 140+ free public APIs |

### Browser

| Tool | Description |
|------|-------------|
| `browser_screenshot` | Take browser screenshots |
| `browser_navigate` | Navigate browser |
| `browser_click` | Click elements |
| `browser_evaluate` | Execute JavaScript |

### Computer Use

| Tool | Description |
|------|-------------|
| `computer_screenshot` | Take desktop screenshots |
| `computer_mouse` | Move/click mouse |
| `computer_type` | Type text |
| `computer_key` | Press keyboard keys |
| `computer_open_app` | Open applications |

### Context & Planning

| Tool | Description |
|------|-------------|
| `write_todos` | Track task progress |
| `ask_user` | Ask user questions |
| `suggest_followups` | Suggest next steps |

### Visual & Design

| Tool | Description |
|------|-------------|
| `visual_review` | Screenshot + AI design review |
| `design_fetch` | Fetch brand design systems |
| `render_ui` | Render interactive UI widgets |

### MCP & External

| Tool | Description |
|------|-------------|
| `mcp_connect` | Connect to MCP servers |
| `mcp_list` | List available MCP tools |

### Multi-Edit

| Tool | Description |
|------|-------------|
| `multi_edit` | Edit multiple files atomically |
| `apply_patch` | Apply git-style patches |

### Skills & Teams

| Tool | Description |
|------|-------------|
| `skill` | Load and use a skill |
| `team_spawn` | Spawn a team agent |
| `team_execute` | Execute team task |

### Deployment

| Tool | Description |
|------|-------------|
| `deploy` | Deploy to hosting platform |
| `docker_run` | Run Docker containers |
| `docker_build` | Build Docker images |

### Monitoring

| Tool | Description |
|------|-------------|
| `monitor_start` | Start monitoring |
| `monitor_stop` | Stop monitoring |
| `monitor_status` | Check monitoring status |

### Session

| Tool | Description |
|------|-------------|
| `session_send` | Send message to another session |
| `session_list` | List active sessions |

---

## 🔌 140+ Free APIs

Dev Agent has pre-configured access to 140+ free public APIs:

### Categories

| Category | Count | Examples |
|----------|-------|----------|
| **Weather** | 5 | OpenWeatherMap, WeatherAPI, Visual Crossing |
| **Finance** | 10 | Alpha Vantage, CoinGecko, ExchangeRate |
| **News** | 8 | NewsAPI, GNews, Currents |
| **Maps** | 5 | OpenStreetMap, Mapbox, HERE |
| **Translation** | 5 | LibreTranslate, MyMemory, Lingva |
| **Entertainment** | 10 | TMDB, JokeAPI, PoetryDB |
| **Science** | 8 | NASA, Open Notify, Numbers API |
| **Dev Tools** | 15 | GitHub API, REST Countries, IP Geolocation |
| **AI & ML** | 10 | Hugging Face, Replicate, AssemblyAI |
| **Communication** | 5 | Telegram, Discord Webhooks |
| **Storage** | 5 | Cloudinary, ImgBB, Catbox |
| **Data** | 10 | JSONBin, MockAPI, FakeStore |
| **Social** | 5 | Reddit, Stack Overflow, Dev.to |
| **Health** | 5 | Nutritionix, CDC, WHO |
| **Education** | 5 | Wikipedia, Open Library, QuizAPI |
| **Shopping** | 5 | FakeStore, DummyJSON, Platzi |
| **Sports** | 5 | API-Football, Cricket, NBA |
| **Travel** | 5 | Amadeus, Skyscanner, Booking |
| **Utility** | 20 | QR Code, URL Shortener, Email Validation |

### Usage

```bash
# In chat, ask the agent to use APIs
"Get the current weather in New York"
"Fetch today's top news headlines"
"Convert 100 USD to EUR"
"Search Wikipedia for quantum computing"
```

---

## 📡 65+ MCP Servers

Dev Agent supports Model Context Protocol servers for external tool integration:

### Built-in MCP Servers

| Category | Servers |
|----------|---------|
| **Database** | PostgreSQL, SQLite, MySQL, MongoDB, Redis |
| **Browser** | Puppeteer, Playwright, Chrome DevTools |
| **Filesystem** | Local files, Google Drive, Dropbox |
| **GitHub** | Repos, Issues, PRs, Actions |
| **Search** | Brave Search, Exa, Tavily |
| **Communication** | Slack, Discord, Email |
| **Cloud** | AWS, GCP, Azure (limited) |
| **Monitoring** | Sentry, Datadog, Prometheus |
| **CMS** | Contentful, Strapi, WordPress |
| **E-commerce** | Shopify, Stripe |
| **And 35+ more** | See `narendra mcp list` |

### Usage

```bash
# List available MCP servers
narendra mcp list

# Add an MCP server
narendra mcp add postgres --command "npx @modelcontextprotocol/server-postgres"

# Configure MCP server
narendra mcp config my-server --command "..." --env "DB_URL=..."
```

---

## 🎯 1500+ Skills

Dev Agent includes 1500+ expert skills organized by role and technology:

### By Role

| Role | Skills | Examples |
|------|--------|----------|
| **Frontend Engineer** | 200+ | React, Vue, Angular, CSS, responsive design |
| **Backend Engineer** | 200+ | Node.js, Python, Go, Rust, APIs |
| **DevOps Engineer** | 150+ | Docker, CI/CD, deployment, monitoring |
| **Security Engineer** | 100+ | Penetration testing, code review, compliance |
| **Data Engineer** | 150+ | SQL, ETL, analytics, machine learning |
| **Product Manager** | 50+ | PRDs, user stories, roadmaps |
| **UI/UX Designer** | 100+ | Design systems, accessibility, prototyping |
| **Mobile Developer** | 100+ | React Native, Flutter, iOS, Android |
| **Full Stack** | 200+ | End-to-end development |
| **And 25+ more roles** | 500+ | See `narendra skills-list` |

### By Technology

| Technology | Skills |
|-----------|--------|
| **Languages** | Python, JavaScript, TypeScript, Go, Rust, Java, C++, Swift, Kotlin |
| **Frameworks** | React, Next.js, Vue, Angular, Express, FastAPI, Django, Flask |
| **Databases** | PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB |
| **Cloud** | AWS, GCP, Azure, Vercel, Netlify, Railway |
| **Tools** | Docker, Kubernetes, Terraform, Ansible, GitHub Actions |
| **AI/ML** | TensorFlow, PyTorch, scikit-learn, Hugging Face |

### By Technology

| Technology | Skills |
|-----------|--------|
| **Languages** | Python, JavaScript, TypeScript, Go, Rust, Java, C++, Swift, Kotlin |
| **Frameworks** | React, Next.js, Vue, Angular, Express, FastAPI, Django, Flask |
| **Databases** | PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB |
| **Cloud** | AWS, GCP, Azure, Vercel, Netlify, Railway |
| **Tools** | Docker, Kubernetes, Terraform, Ansible, GitHub Actions |
| **AI/ML** | TensorFlow, PyTorch, scikit-learn, Hugging Face |

### Usage

```bash
# List all skills
narendra skills-list

# Run a specific skill
narendra skill react-testing
narendra skill docker-deploy
narendra skill security-audit
```

---

## 🔒 Security (7 Layers)

Dev Agent has 7 security layers to protect your system:

| Layer | Description |
|-------|-------------|
| **1. Injection Detection** | Detects and blocks prompt injection attacks |
| **2. Sandboxing** | Commands run in isolated environment |
| **3. Tool Validation** | Validates all tool inputs before execution |
| **4. Rate Limiting** | Prevents abuse with per-tool rate limits |
| **5. Encryption** | API keys encrypted at rest |
| **6. Audit Logging** | All actions logged for review |
| **7. Red Team Testing** | Regular security audits |

### Security Features

```bash
# Run security audit
narendra review --security

# Check permissions
/permissions

# View audit logs
narendra logs --security
```

---

## 🏗️ Architecture

```
dev/
├── agents/              # Agent loop, compaction, teams, skills
│   ├── production_loop.py    # Main agent loop (2848 lines)
│   ├── compaction.py         # Context compaction engine
│   ├── skill_integration.py  # Skill loading and matching
│   ├── teams.py              # Multi-agent team management
│   └── system_prompt.py      # System prompt construction
├── apis/                # 140+ free API integrations
│   └── free_apis.py          # All free API configurations
├── cli/                 # CLI commands and TUI
│   ├── main.py               # Thin entrypoint
│   ├── shared.py             # Shared utilities
│   ├── chat.py               # Interactive chat (801 lines)
│   ├── slash_handler.py      # 95+ slash commands (1100 lines)
│   ├── run_cmd.py            # Single-task execution
│   ├── session_cmd.py        # Session management
│   ├── agent_cmd.py          # Multi-agent management
│   ├── tools_cmd.py          # Tool and MCP management
│   └── util_cmd.py           # All utility commands
├── config/              # Configuration management
├── mcp/                 # MCP server integration
│   ├── client.py             # MCP client
│   └── registry.py           # 65+ MCP server configs
├── providers/           # AI model providers
│   ├── nim_provider.py       # NVIDIA NIM provider
│   ├── unified_provider.py   # Multi-provider router
│   └── openrouter_provider.py # OpenRouter provider
├── sandbox/             # Command sandboxing
├── security/            # Security layers
│   ├── injection_detector.py # Prompt injection detection
│   ├── tool_validator.py     # Tool input validation
│   └── audit.py              # Audit logging
├── skills/              # 1500+ skill definitions
├── tools/               # 31 tool implementations
│   ├── real_tools.py         # Core tools (11)
│   ├── browser_tools.py      # Browser automation (5)
│   ├── computer_use.py       # Computer control (6)
│   ├── api_tools.py          # API tools (5)
│   ├── mcp_tools.py          # MCP tools (5)
│   └── ...                   # 12 more tool files
└── utils/               # Shared utilities
    ├── budget.py             # Cost tracking
    ├── error_recovery.py     # Error handling
    ├── project_detector.py   # Project type detection
    └── prompt_templates.py   # Prompt engineering
```

### Key Design Decisions

1. **Provider-Agnostic**: Works with NVIDIA NIM, OpenRouter, Bytez, or any OpenAI-compatible API
2. **Tool-First Architecture**: Every capability is exposed as a tool the AI can call
3. **Lazy-Loaded Skills**: 1500+ skills loaded on-demand, not at startup
4. **Context Compaction**: Auto-compacts at 75% context (more aggressive than Claude Code's 95%)
5. **Security by Default**: All tool calls validated, rate-limited, and audited
6. **Free by Design**: Every feature uses free APIs and free-tier models

---

## 📊 Comparison with Leading CLI Agents

| Feature | Claude Code | Codex CLI | Aider | **Dev Agent** |
|---------|:-----------:|:---------:|:-----:|:-------------:|
| **Price** | $20/mo+ | $20/mo+ | Free (BYOK) | **Free** |
| **Models** | Claude only | OpenAI only | 100+ | **80+ free** |
| **Slash Commands** | 40+ | 25+ | 10+ | **95** |
| **Tools** | ~30 | ~20 | ~10 | **31+** |
| **Free APIs** | 0 | 0 | 0 | **88+** |
| **MCP Servers** | ~20 | ~15 | ~5 | **65** |
| **Skills** | 2300+ | ~100 | 0 | **1500+** |
| **Security Layers** | ~3 | ~2 | ~1 | **7** |
| **Plan Mode** | ✅ | ✅ | ✅ | ✅ |
| **Auto-Compact** | ✅ | ✅ | ✅ | ✅ |
| **Custom Commands** | ✅ | ✅ | ❌ | ✅ |
| **Image Analysis** | ✅ | ✅ | ❌ | ✅ |
| **CI/CD** | ✅ | ✅ | ❌ | ✅ |
| **Deploy** | ❌ | ❌ | ❌ | ✅ |
| **Database** | ❌ | ❌ | ❌ | ✅ |
| **Security Audit** | ❌ | ❌ | ❌ | ✅ |
| **Multi-Agent** | ✅ | ✅ | ❌ | ✅ |
| **Open Source** | ❌ | ✅ | ✅ | ✅ |

---

## 🔧 Configuration

### Config File

Location: `~/.dev/config.json`

```json
{
  "api_keys": {
    "nvidia": ["nvapi-..."],
    "openrouter": ["sk-or-..."],
    "bytez": ["..."]
  },
  "default_model": "meta/llama-3.1-70b-instruct",
  "approval_mode": "auto-edit",
  "auto_commit": true,
  "auto_test": false,
  "auto_lint": false,
  "verbose": false,
  "max_context_tokens": 128000,
  "auto_compact_threshold": 0.75
}
```

### Project Config

Location: `.dev/` in your project root

```
.dev/
├── config.json        # Project-specific settings
├── commands/          # Custom slash commands
├── rules/             # Project rules (.devrules)
├── skills/            # Project-specific skills
└── memory/            # Auto-learned memories
```

### Hierarchical Settings

Settings cascade: Global → Project → User → CLI flags

```bash
# Global settings
narendra settings set default_model "meta/llama-3.1-70b-instruct"

# Project settings
narendra settings set --project auto_commit true

# CLI flags (highest priority)
narendra chat --model "nvidia/nemotron-ultra-253b-v1"
```

---

## 🧪 Testing

### Run Tests

```bash
# Unit tests
python -m pytest tests/ -q

# Integration tests (requires API keys)
python -m pytest tests/test_integration_nim.py -q

# Security tests
python -m pytest tests/test_security_hardening.py -q

# All tests with coverage
python -m pytest tests/ --cov=dev --cov-report=term-missing
```

### Test Status

```
282 passed, 12 warnings in 109s
```

### Test Categories

| Category | Tests | Description |
|----------|-------|-------------|
| Unit | 235 | Tool implementations, providers, agents |
| Integration | 26 | Real NIM API calls, streaming, tool execution |
| Security | 12 | Injection detection, sandboxing, encryption |
| Streaming | 9 | Token-by-token streaming, fallback |

---

## 🤝 Contributing

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/dev-agent.git`
3. **Create** a branch: `git checkout -b feature/amazing-feature`
4. **Install** dependencies: `pip install -e ".[dev]"`
5. **Make** your changes
6. **Run** tests: `python -m pytest tests/ -q`
7. **Commit**: `git commit -m "Add amazing feature"`
8. **Push**: `git push origin feature/amazing-feature`
9. **Open** a Pull Request

### Development Setup

```bash
# Clone
git clone https://github.com/G-Narendra/dev-agent.git
cd dev-agent

# Create virtual environment
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"

# Run tests
.venv/Scripts/python -m pytest tests/ -q

# Run the agent
.venv/Scripts/python -m dev chat
```

### Code Style

- **Type hints** on all functions
- **Docstrings** on all classes and public methods
- **No bare excepts** — always catch specific exceptions
- **`# Intentional:`** comments on swallowed exceptions
- **`__all__`** exports in all modules

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

Built with inspiration from:

- **[Claude Code](https://claude.ai)** — Tool calling, streaming, and orchestration patterns
- **[Freebuff](https://freebuff.com)** — CLI architecture and TUI design
- **[Aider](https://aider.chat)** — Context management, repo mapping, and git discipline
- **[OpenClaw](https://openclaw.ai)** — Compaction engine and context pruning patterns
- **[Codex CLI](https://github.com/openai/codex)** — Loop safety, sandboxing, and approval modes
- **[Cline](https://github.com/cline/cline)** — Multi-agent teams and parallel execution
- **[Kilo CLI](https://github.com/kilo-org/kilo)** — Orchestration modes and skill system
- **[OpenCode](https://github.com/opencode-ai/opencode)** — TUI design and provider routing

---

## 📞 Support

- **GitHub Issues**: [github.com/G-Narendra/dev-agent/issues](https://github.com/G-Narendra/dev-agent/issues)
- **Documentation**: Run `narendra --help` or `/help` in chat
- **Diagnostics**: Run `narendra doctor` for system health check

---

**Made with ❤️ by G-Narendra**

*The world's first free, open-source AI coding agent with 88+ free APIs, 65 MCP servers, and 1500+ skills.*
