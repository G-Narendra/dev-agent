# 🛠️ AI Agent CLI Tools — Master Installation Guide

> **Purpose:** Every CLI tool this AI agent needs, organized by tier, with exact install commands for **Windows** (scoop/winget), **Linux** (apt), and **macOS** (brew). Always install in a virtual environment — never globally.

---

## 🔥 NEW: Hidden Gems Edition

Tools below are fresh discoveries from GitHub, Reddit, and developer communities — Rust/Go-based replacements that are 10-100x faster than traditional tooling. Bold items are newly added.

---

## Quick Install (Windows — Scoop)

```powershell
# Install scoop (if not installed)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Install TIER 1 essentials only
scoop install ripgrep jq fd httpie

# Then verify
rg --version; jq --version; fd --version; http --version
```

### Install Tier 2 recommended extras:
```powershell
scoop install bat fzf tokei dust sd dasel delta
```

### Install Tier 5 toolchain (code quality):
```powershell
scoop install biome ruff minify
# oxc: npx oxlint@latest (runs without install)
```

### Install Tier 4 + 6 hidden gems:
```powershell
scoop install hyperfine zoxide atuin eza btop
# Aider: pip install aider-chat (in venv)
```

---

## 🟢 TIER 1: ESSENTIAL — Install First (Must-Have)

These tools replace the most common Python reimplementations. Install **ripgrep** and **jq** before anything else.

| Tool | What It Does | Windows | Linux | macOS | Verify |
|------|-------------|---------|-------|-------|--------|
| **ripgrep (rg)** | Blazing-fast code search. Replaces `grep` + Python `os.walk` + `re.search`. | `scoop install ripgrep` | `apt install ripgrep` | `brew install ripgrep` | `rg --version` |
| **jq** | JSON parser/transformer. Replaces Python `json.load()` + list comprehensions. | `scoop install jq` | `apt install jq` | `brew install jq` | `jq --version` |
| **fd** | Fast file finder. Replaces Python `glob.glob()` + `os.listdir()`. | `scoop install fd` | `apt install fd-find` | `brew install fd` | `fd --version` |
| **HTTPie (http)** | Human-friendly HTTP client. Replaces Python `requests.get()` + error handling. | `scoop install httpie` | `pip install httpie` (in venv) | `brew install httpie` | `http --version` |

### Test the Essentials Pipeline
```bash
# Search all .py files for TODO, extract first line of each match, format as JSON
rg 'TODO' src/ --type py -l | jq -R -s 'split("\n") - [""] | {todo_files: .}'
```

---

## 🔵 TIER 2: RECOMMENDED — Install for Full Capability

These tools make the AI agent dramatically more efficient for specific tasks.

| Tool | What It Does | Windows | Linux | macOS | When to Use |
|------|-------------|---------|-------|-------|-------------|
| **bat** | `cat` with syntax highlighting + git integration | `scoop install bat` | `apt install bat` | `brew install bat` | Reading source files, configs, logs |
| **fzf** | Interactive fuzzy finder | `scoop install fzf` | `apt install fzf` | `brew install fzf` | Navigating large directory trees |
| **tokei** | Count lines of code by language | `scoop install tokei` | `apt install tokei` | `brew install tokei` | Project LOC stats, type/language breakdown |
| **dust** | Disk usage visualizer (better `du`) | `scoop install dust` | `apt install dust` | `brew install dust` | Finding large files/directories |
| **sd** | Find & replace (better `sed`) | `scoop install sd` | `cargo install sd` | `brew install sd` | Bulk text replacement across files |
| **dasel** | Query/transform JSON, YAML, TOML, XML | `scoop install dasel` | `go install github.com/TomWright/dasel@latest` | `brew install dasel` | Reading config files in any format |
| **delta** | Syntax-highlighted git diff viewer | `scoop install delta` | `cargo install git-delta` | `brew install git-delta` | Code review, git diff analysis |

### Advanced Pipeline Examples
```bash
# Find all Python files, count LOC by directory, output as JSON
fd '*.py' src -X tokei --output json | jq '{total_lines: [..|.code? // empty] | add}'

# Find large log files, search for errors, format as structured report
fd '*.log' -s 1M | xargs rg 'ERROR' -c | sd ':' '\t' | column -t

# Read YAML config, extract key, pipe to another tool
dasel select -f config.yaml '.database.host'
```

---

## 🟣 TIER 3: PLATFORM CLIs (Project-Specific)

Install these when the project needs them.

| Tool | What It Does | Install Command | Project Type |
|------|-------------|----------------|-------------|
| **GitHub CLI (gh)** | PRs, issues, repos from terminal | `scoop install gh` | Any GitHub-hosted project |
| **Supabase CLI** | Local Postgres + schema migrations | `scoop bucket add supabase https://github.com/supabase/scoop-bucket && scoop install supabase` or `npx supabase` | Projects using Supabase |
| **Stripe CLI** | Webhooks, API logs, test events | `scoop install stripe` | Payment integration projects |
| **Starship** | Fast shell prompt customization | `scoop install starship` | Any project — prompt shows git status, runtime version |
| **Vercel CLI** | Deploy previews, env vars, infra | `npm install -g vercel` (use `npx vercel` instead) | Frontend/Next.js deployment |
| **Railway CLI** | Deploy backend services | `npm install -g @railway/cli` (use npx) | Backend deployment |
| **Firecrawl** | Turn web pages → clean Markdown for AI | `npm install -g @firecrawl/cli` (use npx) | Web scraping for research |
| **Amazon Q Developer CLI** 🆕 | Free-tier AI agent with deep AWS context | `npm install -g @amazonq/cli` (use npx) | AWS/cloud-native projects |
| **Ponytail** 🆕 | Enforces Decision Ladder on AI agents — 54% LOC reduction | `npm install ponytail` | AI-assisted projects (Claude Code, Copilot CLI) |

---

## 🟡 TIER 4: DATA & DATABASE TOOLS (Install When Needed)

| Tool | What It Does | Install Command | Use Case |
|------|-------------|----------------|---------|
| **DuckDB CLI** | Query CSV/JSON/Parquet with SQL | `scoop install duckdb` | Analyzing data files without loading into Python |
| **usql** | Universal SQL client (all databases) | `scoop install usql` | Query Postgres/MySQL/SQLite from one CLI |
| **pgcli** | Postgres CLI with auto-complete | `pip install pgcli` (in venv) | Database management |
| **bottom (btm)** | Cross-platform system monitor | `scoop install bottom` | Debugging performance issues |
| **procs** | Modern `ps` replacement | `scoop bucket add extras && scoop install procs` | Process management |
| **curlie** | HTTP client with curl engine + HTTPie UI | `scoop install curlie` | API calls with familiar curl syntax |
| **xh** | Rust-based HTTPie alternative (faster) | `scoop install xh` | Fast API calls for CI/CD pipelines |
| **hyperfine** 🆕 | Statistical CLI benchmarking (mean, median, min, max, stddev) | `scoop install hyperfine` or `cargo install hyperfine` | Benchmark before/after optimization |
| **zoxide** 🆕 | Smarter `cd` — learns your habits, jumps with `z <partial>` | `scoop install zoxide` or `cargo install zoxide` | Project navigation |
| **atuin** 🆕 | Encrypted, searchable shell history (cross-machine sync) | `scoop install atuin` or `cargo install atuin` | Shell history search |
| **eza** 🆕 | Modern `ls` with icons, git status, file types | `scoop install eza` or `cargo install eza` | Directory listing |
| **btop** 🆕 | GPU-aware system monitor dashboard | `scoop install btop` | Performance monitoring |

## 🔴 TIER 5: TOOLCHAIN & LINTING (Code Quality)

Install these for production-ready code quality checks.

| Tool | What It Does | Install Command | Replaces |
|------|-------------|----------------|----------|
| **biome** 🆕 | Rust-based all-in-one formatter + linter for JS/TS/JSON/CSS | `npx @biomejs/biome init` or `scoop install biome` | Prettier + ESLint (single tool, 10x faster) |
| **Ruff** 🆕 | Python linter in Rust (10-100x faster) | `pip install ruff` (in venv) or `scoop install ruff` | Flake8, Pylint, Pyright |
| **oxc (oxlint)** 🆕 | Next-gen JS/TS toolchain (linter, parser, bundler, minifier) | `npx oxlint@latest` or `npm install -g @oxidation/oxlint` | Terser + ESLint (Rust-based) |
| **minify (tdewolff)** 🆕 | Go-based multi-format minifier (HTML/CSS/JS/JSON/SVG/XML) | `scoop install minify` or `go install github.com/tdewolff/minify/cmd/minify@latest` | htmlmin, cssmin, jsmin (single tool) |

### Configure for Your Project
```bash
# biome: init config
npx @biomejs/biome init

# biome: check all files
npx biome check . --apply

# Ruff: check with sensible defaults
ruff check . --fix

# minify: compress build output
minify --all --output dist/ src/
```

---

## 🚀 TIER 6: CLI AGENT FRAMEWORKS (Advanced)

These are AI agents you can spawn as sub-processes from within the main AI agent.

| Framework | What It Does | Install (in venv) | Project |
|-----------|-------------|-------------------|---------|
| **Goose** | Terminal-first AI coding agent | `pip install goose-ai` | [block/goose](https://github.com/block/goose) |
| **OpenCode** | Open-source coding harness with MCP | `pip install opencode` | [opencode-dev/opencode](https://github.com/opencode-dev/opencode) |
| **pilotty** | Headless PTY terminal automation | `pip install pilotty` | [msmps/pilotty](https://github.com/msmps/pilotty) |
| **Gemini CLI** | Google's multimodal terminal agent | `npx @google/gemini-cli` | [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) |
| **Aider** 🆕 | Open-source CLI pair programming with any LLM | `pip install aider-chat` (in venv) | [Aider-AI/aider](https://github.com/Aider-AI/aider) |

```bash
# Spawn Goose to generate code, scoped to project directory
cd my-project
python -m venv .venv && source .venv/bin/activate
pip install goose-ai
goose run --working-dir . "Build a REST API with Express and SQLite"
```

---

## 🛠️ IDE EXTENSIONS (Not CLI, But Essential)

These are NOT CLI tools — they're editor extensions that enhance AI agent workflows.

| Extension | What It Does | Install | Project |
|-----------|-------------|---------|---------|
| **Cline** 🆕 | Agentic VSCode extension with BYOK support — runs agent loops inside your editor | Search "Cline" in VSCode Marketplace | [cline/cline](https://github.com/cline/cline) |
| **Continue** 🆕 | Open-source AI code assistant (VS + JetBrains) | Search "Continue" in VSCode Marketplace | [continuedev/continue](https://github.com/continuedev/continue) |

```bash
# For CLI-accessible agentic coding, use Aider instead:
pip install aider-chat  # (in venv)
aider --model claude-sonnet-4-20250514 --lint-cmd "npx biome check"
```

---

## 🧪 VERIFICATION CHECKLIST

After installing, run these to confirm everything works:

```bash
# Core tools
rg --version          # Expect ripgrep x.y.z
jq --version          # Expect jq-x.y
fd --version          # Expect fd x.y.z
http --version        # Expect HTTPie x.y.z

# Recommended tools
bat --version         # Expect bat x.y.z
fzf --version         # Expect x.y.z
tokei --version       # Expect tokei x.y.z
dust --version        # Expect dust x.y.z
sd --version          # Expect sd-x.y.z
dasel --version       # Expect x.y.z

# Full pipeline test
echo '{"tools":["rg","jq","fd","httpie"]}' | jq '.tools[]' | sort
```

---

## 📚 REFERENCE UTILITY FILES

These YAML files in the project document CLI tools in detail:

| File | Content |
|------|---------|
| `utilities/coding/modern-cli-arsenal.yaml` | Full CLI toolbox — 17 tools with usage examples and pipeline patterns |
| `utilities/coding/cli-agent-frameworks.yaml` | Goose, Gemini CLI, OpenCode, pilotty — install, configure, spawn |
| `utilities/coding/mcp-server-orchestrator.yaml` | MCP server discovery + installation for database, browser, filesystem access |
| `utilities/research/cli-tool-discovery.yaml` | How to find the right CLI tool for any task (awesome-lists, GitHub topics, crates.io) |
| `utilities/coding/ai-code-compression.yaml` 🆕 | Ponytail Decision Ladder + Caveman prompting — 54% LOC reduction on AI-generated code |
| `utilities/coding/production-toolchain.yaml` 🆕 | Hidden gems: oxc, biome, Ruff, hyperfine, minify, zoxide, atuin, eza, btop |
| `utilities/cognitive/minimalist-agent-workflow.yaml` 🆕 | Master workflow: Plan → Compress → Validate → Iterate with all hidden gems |

---

## ⚠️ RULES

1. **Never install globally.** Use `scoop install` (Windows), `pip install` in a venv (Python tools), or `npx` (Node tools).
2. **Check availability first** with `which <tool>` (Linux/macOS) or `where <tool>` (Windows).
3. **Prefer these tools over Python reimplementations.** A one-liner `rg 'pattern'` is faster and more reliable than 20 lines of `os.walk` + `re.search`.
4. **Chain them in pipelines.** The real power is combining tools: `fd '*.py' | xargs rg 'TODO' | jq -s '{todos: .}'`
5. **No `curl | bash`.** Always use a proper package manager or download from a verified release.
6. **Apply Ponytail's Decision Ladder before generating code.** YAGNI → Reuse → Stdlib → Native APIs → Simplicity. See `utilities/coding/ai-code-compression.yaml`.
7. **Use biome or Ruff instead of traditional linters.** 10-100x faster, unified config. See `utilities/coding/production-toolchain.yaml`.
8. **Count LOC before and after compression** with `tokei src/ --output json | jq '.[] | {language, code}'`.
9. **Follow the full Plan → Compress → Validate → Iterate workflow** for every new feature. See `utilities/cognitive/minimalist-agent-workflow.yaml`.
