# Dev Agent vs Claude Code — Feature Comparison V3

**Date**: August 23, 2026
**Status**: Feature parity analysis

---

## CLI COMMANDS (Claude Code has 40+, Dev has 106+)

### Session Management
| Command | Claude Code | Dev Agent | Status |
|---------|-------------|-----------|--------|
| `/clear` | ✅ | ✅ | ✅ |
| `/compact` | ✅ | ✅ | ✅ |
| `/resume` | ✅ | ✅ | ✅ |
| `/fork` | ✅ | ✅ | ✅ |
| `/rename` | ✅ | ✅ | ✅ |
| `/rewind` | ✅ | ✅ | ✅ |
| `/exit` | ✅ | ✅ | ✅ |

### Information and Diagnostics
| Command | Claude Code | Dev Agent | Status |
|---------|-------------|-----------|--------|
| `/cost` | ✅ | ✅ | ✅ |
| `/usage` | ✅ | ✅ | ✅ |
| `/context` | ✅ | ✅ | ✅ |
| `/status` | ✅ | ✅ | ✅ |
| `/doctor` | ✅ | ✅ | ✅ |
| `/help` | ✅ | ✅ | ✅ |
| `/stats` | ✅ | ✅ | ✅ |
| `/diff` | ✅ | ✅ | ✅ |
| `/export` | ✅ | ✅ | ✅ |
| `/copy` | ✅ | ❌ MISSING | ❌ |
| `/release-notes` | ✅ | ❌ MISSING | ❌ |
| `/insights` | ✅ | ✅ | ✅ |

### Model and Mode Control
| Command | Claude Code | Dev Agent | Status |
|---------|-------------|-----------|--------|
| `/model` | ✅ | ✅ | ✅ |
| `/fast` | ✅ | ❌ MISSING | ❌ |
| `/plan` | ✅ | ✅ | ✅ |
| `/vim` | ✅ | ❌ MISSING | ❌ |
| `/output-style` | ✅ | ✅ | ✅ |
| `/theme` | ✅ | ✅ | ✅ |

### Configuration and Permissions
| Command | Claude Code | Dev Agent | Status |
|---------|-------------|-----------|--------|
| `/config` | ✅ | ✅ | ✅ |
| `/permissions` | ✅ | ✅ | ✅ |
| `/init` | ✅ | ✅ | ✅ |
| `/memory` | ✅ | ✅ | ✅ |
| `/login` | ✅ | ✅ | ✅ |
| `/logout` | ✅ | ✅ | ✅ |
| `/hooks` | ✅ | ✅ | ✅ |
| `/agents` | ✅ | ✅ | ✅ |
| `/skills` | ✅ | ✅ | ✅ |
| `/mcp` | ✅ | ✅ | ✅ |
| `/plugin` | ✅ | ✅ | ✅ |
| `/terminal-setup` | ✅ | ❌ MISSING | ❌ |
| `/keybindings` | ✅ | ❌ MISSING | ❌ |
| `/sandbox` | ✅ | ✅ | ✅ |
| `/extra-usage` | ✅ | ❌ MISSING | ❌ |
| `/privacy-settings` | ✅ | ❌ MISSING | ❌ |
| `/statusline` | ✅ | ✅ | ✅ |

### Code Review and PR Workflow
| Command | Claude Code | Dev Agent | Status |
|---------|-------------|-----------|--------|
| `/review` | ✅ | ✅ | ✅ |
| `/pr-comments` | ✅ | ✅ | ✅ |
| `/security-review` | ✅ | ✅ | ✅ |
| `/install-github-app` | ✅ | ❌ MISSING | ❌ |

### Working Directories and Integration
| Command | Claude Code | Dev Agent | Status |
|---------|-------------|-----------|--------|
| `/add-dir` | ✅ | ✅ | ✅ |
| `/ide` | ✅ | ✅ | ✅ |
| `/chrome` | ✅ | ✅ | ✅ |
| `/remote-control` | ✅ | ❌ MISSING | ❌ |
| `/desktop` | ✅ | ❌ MISSING | ❌ |
| `/tasks` | ✅ | ✅ | ✅ |
| `/feedback` | ✅ | ❌ MISSING | ❌ |

---

## CLI FLAGS

| Claude Code Flag | Dev Agent Flag | Status |
|------------------|----------------|--------|
| `--continue` / `-c` | `--resume` | ✅ |
| `--resume` / `-r` | `--resume` | ✅ |
| `--from-pr` | `--from-pr` | ✅ |
| `--fork-session` | `--fork-session` | ✅ |
| `--session-id` | ❌ MISSING | ❌ |
| `--worktree` / `-w` | `--worktree` | ✅ |
| `--model` | `--model` | ✅ |
| `--fallback-model` | `--fallback-model` | ✅ |
| `--permission-mode` | ❌ MISSING | ❌ |
| `--agent` | `--agent` | ✅ |
| `--agents` | `--agents` | ✅ |
| `--print` / `-p` | `--print` | ✅ |
| `--output-format` | `--output-format` | ✅ |
| `--json-schema` | `--json-schema` | ✅ |
| `--max-turns` | `--max-turns` | ✅ |
| `--max-budget-usd` | `--max-budget` | ✅ |
| `--input-format` | `--input-format` | ✅ |
| `--allowedTools` | `--allowedTools` | ✅ |
| `--disallowedTools` | `--disallowedTools` | ✅ |
| `--tools` | `--tools` | ✅ |
| `--dangerously-skip-permissions` | `--dangerously-skip-permissions` | ✅ |
| `--system-prompt` | `--system-prompt` | ✅ |
| `--system-prompt-file` | `--system-prompt-file` | ✅ |
| `--append-system-prompt` | `--append-system` | ✅ |
| `--append-system-prompt-file` | `--append-system-prompt-file` | ✅ |
| `--mcp-config` | ❌ MISSING | ❌ |
| `--strict-mcp-config` | ❌ MISSING | ❌ |
| `--chrome` | `--chrome` | ✅ |
| `--plugin-dir` | `--plugin-dir` | ✅ |
| `--add-dir` | `--add-dir` | ✅ |
| `--verbose` | `--verbose` | ✅ |
| `--debug` | `--debug` | ✅ |
| `--version` | `--version` | ✅ |
| `--ide` | `--ide` | ✅ |
| `--init` | `--init-only` | ✅ |
| `--remote` | ❌ MISSING | ❌ |
| `--teleport` | ❌ MISSING | ❌ |
| `--disable-slash-commands` | `--disable-slash-commands` | ✅ |
| `--settings` | ❌ MISSING | ❌ |

---

## TOOLS

| Claude Code Tool | Dev Agent Tool | Status |
|------------------|----------------|--------|
| Read | `read_files` | ✅ |
| Write | `write_file` | ✅ |
| Edit | `str_replace` | ✅ |
| Grep | `code_search` | ✅ |
| Glob | `glob` | ✅ |
| LS | `list_directory` | ✅ |
| Bash | `run_terminal_command` | ✅ |
| TodoWrite | `write_todos` | ✅ |
| WebSearch | `web_search` | ✅ |
| WebFetch | `read_url` | ✅ |
| MultiEdit | `multi_edit` | ✅ |
| Browser | `browser_*` | ✅ |
| ReadImage | `read_image` | ✅ |
| ReadPDF | `read_pdf` | ✅ |
| Git | `git_operations` | ✅ |
| Task | `task_completed` | ✅ |
| Skill | `skill` | ✅ |
| ContextStats | `context_stats` | ✅ |
| RepoMap | `repo_map` | ✅ |
| Summarize | `summarize` | ✅ |
| Pipeline | `pipeline` | ✅ |
| SpawnAgents | `spawn_agents` | ✅ |
| Sandbox | `sandboxed_run` | ✅ |
| Diagram | `generate_diagram` | ✅ |
| FreeAPI | `free_api` | ✅ (137 APIs) |
| MCP | `install_mcp_tool` | ✅ (57 servers) |
| Monitor | `monitor_*` | ✅ (4 tools) |
| ComputerUse | `computer_*` | ✅ (6 tools) |
| SessionMessaging | `*_session_*` | ✅ (4 tools) |

---

## FEATURES

| Feature | Claude Code | Dev Agent | Status |
|---------|-------------|-----------|--------|
| Streaming | ✅ | ✅ | ✅ |
| Tool calling | ✅ | ✅ | ✅ |
| Multi-model | ✅ (Opus/Sonnet) | ✅ (NIMs) | ✅ |
| Plan mode | ✅ | ✅ | ✅ |
| Auto-accept mode | ✅ | ✅ | ✅ |
| Approval modes | ✅ | ✅ | ✅ |
| Undo/redo | ✅ | ✅ | ✅ |
| Session persistence | ✅ | ✅ | ✅ |
| Context compaction | ✅ | ✅ | ✅ |
| Auto-commit | ✅ | ✅ | ✅ |
| Git worktree | ✅ | ✅ | ✅ |
| MCP integration | ✅ | ✅ | ✅ |
| Skills system | ✅ | ✅ | ✅ |
| Hooks | ✅ | ✅ | ✅ |
| Custom commands | ✅ | ✅ | ✅ |
| Background tasks | ✅ | ✅ | ✅ |
| Daemon | ✅ | ✅ | ✅ |
| Batch processing | ✅ | ✅ | ✅ |
| Docker sandboxing | ✅ | ✅ | ✅ |
| Browser automation | ✅ | ✅ | ✅ |
| Agent teams | ✅ | ✅ | ✅ |
| Sub-agents | ✅ | ✅ | ✅ |
| Computer use | ✅ | ✅ | ✅ |
| Cross-session messaging | ✅ | ✅ | ✅ |
| Monitor tool | ✅ | ✅ | ✅ |
| Free APIs | ❌ | ✅ (137) | ✅ Dev wins |
| MCP servers | ✅ (built-in) | ✅ (57) | ✅ Dev wins |
| Skills | ✅ (built-in) | ✅ (40+) | ✅ Dev wins |
| 24/7 operation | ❌ | ✅ | ✅ Dev wins |
| Free tier | ❌ ($20/mo) | ✅ | ✅ Dev wins |
| Multi-key rotation | ❌ | ✅ (3 keys) | ✅ Dev wins |
| Open source | ❌ | ✅ | ✅ Dev wins |

---

## REMAINING GAPS (Claude Code has, Dev doesn't)

### Critical (Implementable)
1. `/copy` — Copy last response to clipboard
2. `/release-notes` — View changelog
3. `/fast` — Toggle fast mode
4. `/vim` — Toggle Vim mode
5. `/terminal-setup` — Configure terminal keybindings
6. `/keybindings` — Open keybindings config
7. `/extra-usage` — Configure extra usage
8. `/privacy-settings` — Privacy settings
9. `/install-github-app` — GitHub App setup
10. `/feedback` — Submit feedback
11. `/session-id` flag — Use specific session UUID
12. `--permission-mode` flag — Start in specific mode
13. `--mcp-config` flag — Load MCP config
14. `--strict-mcp-config` flag — Only use specified MCP
15. `--remote` flag — Create web session
16. `--teleport` flag — Resume web session
17. `--settings` flag — Load settings file

### N/A (Not applicable for CLI tool)
- `/remote-control` — Requires web UI
- `/desktop` — Requires desktop app
- `/teleport` — Requires web session
- `/privacy-settings` — Requires paid plan
