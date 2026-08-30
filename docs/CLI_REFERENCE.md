# Dev Agent — CLI Reference

Complete reference for all 90+ CLI commands and 95+ slash commands.

---

## Table of Contents

- [Installation](#installation)
- [Global Flags](#global-flags)
- [CLI Commands](#cli-commands)
- [Chat Slash Commands](#chat-slash-commands)
- [Custom Commands](#custom-commands)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)

---

## Installation

```bash
# npm (recommended)
npm install -g narendra

# From source
git clone https://github.com/G-Narendra/dev-agent.git
cd dev-agent
python -m venv .venv
.venv/Scripts/pip install -e .

# Shell completion
narendra --install-completion
```

---

## Global Flags

These flags apply to all commands:

| Flag | Short | Description |
|------|-------|-------------|
| `--version` | `-v` | Show version |
| `--help` | `-h` | Show help message |
| `--install-completion` | | Install shell completion |
| `--show-completion` | | Show completion script |

---

## CLI Commands

### `narendra chat`

Start interactive chat with streaming output.

```bash
narendra chat [OPTIONS]

Options:
  --model TEXT          Model to use (default: auto)
  --agent TEXT          Agent role (default: coder)
  --project PATH        Project directory (default: .)
  --effort TEXT         Reasoning effort: low, medium, high (default: medium)
  --approval TEXT       Approval mode: suggest, auto-edit, full-auto (default: auto-edit)
  --verbose / --no-verbose  Show detailed output
  --plan / --no-plan    Start in plan mode (read-only)
  --max-steps INT       Max agent steps (default: 50)
  --append-system TEXT  Extra system prompt text
  --fallback-model TEXT Fallback model if primary fails
  --bare / --no-bare    Fast startup: skip loading rules/skills
  --json / --no-json    Output as JSON
  --yes / --no-yes      Skip all confirmation prompts
  --diff-preview / --no-diff-preview  Show diff before applying edits
  --autocompact TEXT    Auto-compact mode: auto, off, or token count
  --context-bar / --no-context-bar  Show live context usage bar
```

**Examples:**

```bash
narendra chat
narendra chat --model "nvidia/nemotron-ultra-253b-v1"
narendra chat --effort high --verbose
narendra chat --plan --approval suggest
narendra chat --bare  # Fast startup
```

---

### `narendra run`

Run a single task with streaming output.

```bash
narendra run "task description" [OPTIONS]

Options:
  --agent TEXT          Agent to use (default: coder)
  --project PATH        Project directory (default: .)
  --effort TEXT         Reasoning effort (default: medium)
  --model TEXT          Model to use (default: auto)
  --verbose / --no-verbose  Show detailed output
  --max-steps INT       Max agent steps (default: 50)
  --approval TEXT       Approval mode (default: full-auto)
  --append-system TEXT  Extra system prompt text
  --fallback-model TEXT Fallback model if primary fails
  --bare / --no-bare    Fast startup
  --json / --no-json    Output as JSON
  --yes / --no-yes      Skip confirmations
  --max-turns INT       Max conversation turns (default: 50)
  --output-format TEXT  Output format: text, json, stream-json
  --max-budget-usd FLOAT  Max spend in USD (0=unlimited)
```

**Examples:**

```bash
narendra run "create a REST API with Express and PostgreSQL"
narendra run "fix all failing tests" --json
narendra run "deploy to Vercel" --approval full-auto
```

---

### `narendra setup`

Configure API keys interactively.

```bash
narendra setup [OPTIONS]

Options:
  --provider TEXT    Provider: nvidia, openrouter, bytez (default: all)
  --key TEXT         API key to add
  --non-interactive / --no-non-interactive  Skip interactive prompts
```

**Examples:**

```bash
narendra setup  # Interactive wizard for all providers
narendra setup --provider nvidia --key "nvapi-..."
```

---

### `narendra sessions`

List all saved sessions.

```bash
narendra sessions [OPTIONS]

Options:
  --all / --no-all    Show all sessions including completed
  --limit INT         Max sessions to show (default: 20)
  --format TEXT       Output format: table, json
```

---

### `narendra resume`

Resume a specific session.

```bash
narendra resume SESSION_ID [OPTIONS]

Options:
  --last / --no-last    Resume most recent session
  --model TEXT          Model to use
  --verbose / --no-verbose  Show detailed output
```

**Examples:**

```bash
narendra resume          # Interactive picker
narendra resume --last   # Most recent
narendra resume abc123   # Specific session
```

---

### `narendra fork`

Fork a session into a new branch.

```bash
narendra fork SESSION_ID [OPTIONS]

Options:
  --name TEXT    Name for the forked session
  --branch TEXT  Git branch name
```

---

### `narendra stop`

Stop a background session.

```bash
narendra stop SESSION_ID
```

---

### `narendra respawn`

Restart a stopped session.

```bash
narendra respawn SESSION_ID
```

---

### `narendra rm`

Remove a session.

```bash
narendra rm SESSION_ID [--yes]
```

---

### `narendra logs`

Print recent output from a session.

```bash
narendra logs SESSION_ID [OPTIONS]

Options:
  --lines INT    Number of lines to show (default: 100)
  --follow / --no-follow  Follow output in real-time
```

---

### `narendra models`

List available models.

```bash
narendra models [OPTIONS]

Options:
  --provider TEXT    Filter by provider
  --available / --no-available  Show only available models
```

---

### `narendra status`

Show system status.

```bash
narendra status
```

---

### `narendra validate`

Validate configuration and API keys.

```bash
narendra validate [OPTIONS]

Options:
  --fix / --no-fix    Try to fix issues automatically
```

---

### `narendra doctor`

Full diagnostic check.

```bash
narendra doctor [OPTIONS]

Options:
  --fix / --no-fix    Try to fix issues automatically
```

---

### `narendra cost`

Show cost and token usage dashboard.

```bash
narendra cost [OPTIONS]

Options:
  --session TEXT    Show cost for specific session
  --all / --no-all  Show all-time cost
```

---

### `narendra init`

Initialize Dev in a project.

```bash
narendra init [OPTIONS]

Options:
  --template TEXT    Project template to use
  --force / --no-force  Overwrite existing config
```

---

### `narendra commit`

Auto-commit changes with AI-generated message.

```bash
narendra commit [OPTIONS]

Options:
  --message TEXT    Custom commit message
  --all / --no-all  Stage all changes
  --push / --no-push  Push after commit
```

---

### `narendra branch`

Create and switch branches.

```bash
narendra branch [BRANCH_NAME] [OPTIONS]

Options:
  --list / --no-list  List all branches
  --delete TEXT       Delete a branch
```

---

### `narendra git-diff`

Show colored git diff.

```bash
narendra git-diff [OPTIONS]

Options:
  --staged / --no-staged  Show staged changes
  --stat / --no-stat      Show only statistics
```

---

### `narendra review`

AI-powered code review.

```bash
narendra review [OPTIONS]

Options:
  --range TEXT      Commit range (e.g., "HEAD~3..HEAD")
  --deep / --no-deep  Deep review
  --security / --no-security  Include security review
```

---

### `narendra ultrareview`

Deep AI-powered PR review.

```bash
narendra ultrareview [OPTIONS]

Options:
  --pr INT          PR number to review
  --base TEXT       Base branch (default: main)
```

---

### `narendra batch`

Split task into parallel worktree branches.

```bash
narendra batch "task description" [OPTIONS]

Options:
  --agents INT      Number of parallel agents (default: 3)
  --timeout INT     Timeout in seconds (default: 300)
```

---

### `narendra deploy`

Deploy project to hosting platform.

```bash
narendra deploy [OPTIONS]

Options:
  --platform TEXT   Platform: vercel, netlify, railway (default: auto-detect)
  --prod / --no-prod  Deploy to production
  --preview / --no-preview  Deploy preview
```

---

### `narendra ci`

Generate CI/CD workflow files.

```bash
narendra ci [OPTIONS]

Options:
  --platform TEXT   Platform: github, gitlab (default: github)
  --actions TEXT    Custom actions to include
```

---

### `narendra pr create`

Create a pull request.

```bash
narendra pr create [OPTIONS]

Options:
  --title TEXT      PR title
  --body TEXT       PR description
  --base TEXT       Base branch (default: main)
  --draft / --no-draft  Create as draft
```

---

### `narendra tools-list`

List all available tools.

```bash
narendra tools-list [OPTIONS]

Options:
  --category TEXT   Filter by category
  --verbose / --no-verbose  Show descriptions
```

---

### `narendra skill`

Run a built-in skill.

```bash
narendra skill SKILL_NAME [OPTIONS]

Options:
  --list / --no-list  List available skills
  --category TEXT     Filter by category
```

---

### `narendra mcp`

Configure MCP servers.

```bash
narendra mcp [ACTION] [OPTIONS]

Actions:
  list              List configured MCP servers
  add NAME          Add an MCP server
  remove NAME       Remove an MCP server
  config NAME       Configure an MCP server

Options:
  --command TEXT    MCP server command
  --env TEXT        Environment variables (KEY=VALUE)
  --timeout INT     Timeout in seconds (default: 30)
```

---

### `narendra hooks`

Manage pre/post tool execution hooks.

```bash
narendra hooks [ACTION] [OPTIONS]

Actions:
  list              List configured hooks
  add NAME          Add a hook
  remove NAME       Remove a hook
```

---

### `narendra memory`

Manage auto-learned memories.

```bash
narendra memory [ACTION] [OPTIONS]

Actions:
  list              List memories
  add TEXT           Add a memory
  remove ID          Remove a memory
  clear             Clear all memories
```

---

### `narendra config`

Manage configuration.

```bash
narendra config [ACTION] [OPTIONS]

Actions:
  show              Show current config
  set KEY VALUE     Set a config value
  get KEY           Get a config value
  reset             Reset to defaults
```

---

### `narendra settings`

Manage hierarchical settings.

```bash
narendra settings [ACTION] [OPTIONS]

Actions:
  show              Show all settings
  set KEY VALUE     Set a setting
  get KEY           Get a setting
  reset             Reset to defaults

Options:
  --project / --no-project  Project-level setting
  --global / --no-global    Global setting
```

---

### `narendra headless`

Run in headless mode for CI/CD pipelines.

```bash
narendra headless "task description" [OPTIONS]

Options:
  --json / --no-json    Output as JSON
  --timeout INT         Timeout in seconds
  --max-steps INT       Max agent steps
```

---

### `narendra task`

Manage background tasks.

```bash
narendra task [ACTION] [OPTIONS]

Actions:
  list              List background tasks
  add NAME          Add a task
  remove ID         Remove a task
  start ID          Start a task
  stop ID           Stop a task
```

---

### `narendra serve`

Start the 24/7 background worker.

```bash
narendra serve [OPTIONS]

Options:
  --workers INT     Number of workers (default: 1)
  --poll-interval INT  Poll interval in seconds (default: 60)
```

---

### `narendra team`

Manage agent teams.

```bash
narendra team [ACTION] [OPTIONS]

Actions:
  list              List teams
  create NAME       Create a team
  add-agent TEAM AGENT  Add agent to team
  execute TEAM      Execute team task
```

---

### `narendra schedule`

Manage scheduled agents.

```bash
narendra schedule [ACTION] [OPTIONS]

Actions:
  list              List scheduled tasks
  add NAME          Add a scheduled task
  remove ID         Remove a scheduled task
  pause ID          Pause a task
  resume ID         Resume a task
```

---

### `narendra daemon`

Manage background-session supervisor.

```bash
narendra daemon [ACTION] [OPTIONS]

Actions:
  start             Start the daemon
  stop              Stop the daemon
  status            Show daemon status
  restart           Restart the daemon
```

---

### `narendra agents`

Open agent view to monitor and dispatch parallel background sessions.

```bash
narendra agents [OPTIONS]

Options:
  --refresh INT     Refresh interval in seconds (default: 5)
```

---

## Chat Slash Commands

When in interactive chat mode (`narendra chat`), type these commands:

### Session Management

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
| `/context` | Show context window usage with visual bar |
| `/snapshot` | Save project state to git stash |
| `/restore` | List stashes for restore |
| `/version` | Show version info |

### Agent Control

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

### Output Modes

| Command | Description |
|---------|-------------|
| `/ghost` | Pure output, no meta-commentary |
| `/raw` | Plain text output |
| `/statusline` | Customize footer status |

### File Operations

| Command | Description |
|---------|-------------|
| `/undo` | Undo last file edit |
| `/redo` | Redo undone edit |
| `/diff` | Show colored git diff |
| `/commit` | Commit all changes |
| `/mention <file>` | Attach file to conversation |

### Git

| Command | Description |
|---------|-------------|
| `/git <args>` | Run git commands (status, log, etc.) |
| `/branch` | List/create/switch branches |
| `/worktree` | Manage git worktrees |

### Code Quality

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

### Web & Research

| Command | Description |
|---------|-------------|
| `/web <query>` | Force web search before answering |
| `/search` | Search the web |

### Project

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

### Connectors & Plugins

| Command | Description |
|---------|-------------|
| `/apps` | Browse available connectors |
| `/plugins` | Manage plugins |
| `/mcp` | List/configure MCP servers |

### Information

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

---

## Custom Commands

Create your own slash commands by adding markdown files:

### Project-Level Commands (shared with team)

```bash
mkdir -p .dev/commands
echo "# Ship
Review the current diff. Run tests. If tests pass, commit with a clear message and push to main." > .dev/commands/ship.md
```

### User-Level Commands (personal)

```bash
mkdir -p ~/.dev/commands
echo "# Deploy
Build the project. Run tests. Deploy to the configured platform." > ~/.dev/commands/deploy.md
```

### Using Custom Commands

```bash
/ship              # Runs .dev/commands/ship.md
/deploy            # Runs ~/.dev/commands/deploy.md
/fix-all           # Runs .dev/commands/fix-all.md
```

### Command Variables

Use `$ARGUMENTS` to pass user input:

```markdown
# review
Review the following: $ARGUMENTS
Focus on security, performance, and best practices.
```

```bash
/review auth module  # $ARGUMENTS = "auth module"
```

---

## Configuration

### Config File Location

- **Global**: `~/.dev/config.json`
- **Project**: `.dev/config.json`

### Config Options

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
  "auto_compact_threshold": 0.75,
  "sandbox_enabled": true,
  "injection_detection": true,
  "max_tool_calls_per_turn": 20,
  "tool_timeout_seconds": 30
}
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NVIDIA_API_KEY` | NVIDIA NIM API key | — |
| `OPENROUTER_API_KEY` | OpenRouter API key | — |
| `BYTEZ_API_KEY` | Bytez API key | — |
| `DEV_MODEL` | Default model | auto |
| `DEV_APPROVAL` | Approval mode | auto-edit |
| `DEV_VERBOSE` | Verbose output | false |
| `DEV_Sandbox` | Enable sandbox | true |
| `DEV_LOG_LEVEL` | Log level | INFO |
