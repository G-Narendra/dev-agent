# Dev Agent vs Claude Code — Feature Comparison

**Date**: August 23, 2026
**Status**: Feature parity analysis

---

## CLI COMMANDS

| Claude Code | Dev Agent | Status | Notes |
|-------------|-----------|--------|-------|
| `/help` | `/help` | ✅ | Same |
| `/clear` | `/clear` | ✅ | Same |
| `/compact` | `/compact` | ✅ | Same |
| `/context` | `/context` | ✅ | Same |
| `/cost` | `/cost` | ✅ | Same |
| `/init` | `/init` | ✅ | Same |
| `/resume` | `/resume` | ✅ | Same |
| `/diff` | `/diff` | ✅ | Same |
| `/model` | `/model` | ✅ | Same |
| `/rewind` | `/rewind` | ✅ | Same |
| `/plan` | `/plan` | ✅ | Same |
| `/review` | `/review` | ✅ | Same |
| `/security-review` | `/security-review` | ✅ | Same |
| `/fork` | `/fork` | ✅ | Same |
| `/export` | `/export` | ✅ | Same |
| `/batch` | `/batch` | ✅ | Same |
| `/doctor` | `/doctor` | ✅ | Same |
| `/commit` | `/commit` | ✅ | Same |
| `/branch` | `/branch` | ✅ | Same |
| `/hooks` | `/hooks` | ✅ | Same |
| `/memory` | `/memory` | ✅ | Same |
| `/agents` | `/agents` | ✅ | Same |
| `/permissions` | `/permissions` | ✅ | Same |
| `/tasks` | `/tasks` | ✅ | Same |
| `/skills` | `/skills` | ✅ | Same |
| `/rename` | `/rename` | ✅ | Same |
| `/usage` | `/usage` | ✅ | Same |
| `/config` | `/config` | ✅ | Same |
| `/settings` | `/settings` | ✅ | Same |
| `/version` | `/version` | ✅ | Same |
| `/loop` | `/loop` | ✅ | Same |
| `/batch` | `/batch` | ✅ | Same |
| `/daemon` | `/daemon` | ✅ | Same |
| `/purge` | `/purge` | ✅ | Same |
| `/ultrareview` | `/ultrareview` | ✅ | Same |
| `/tool-rules` | `/tool-rules` | ✅ | Same |
| `/mcp` | `/mcp` | ✅ | Same |
| `/auto-mode` | `/auto-mode` | ✅ | Same |
| `/sessions-picker` | `/sessions-picker` | ✅ | Same |
| `/typo` | `/typo` | ✅ | Same |
| `/onboard` | `/onboard` | ✅ | Same |
| `/templates` | `/templates` | ✅ | Same |
| `/plugins` | `/plugins` | ✅ | Same |
| `/vscode` | `/vscode` | ✅ | Same |
| `/tool-create` | `/tool-create` | ✅ | Same |
| `/mailbox` | `/mailbox` | ✅ | Same |
| `/plan` | `/plan` | ✅ | Same |
| `/workflow` | `/workflow` | ✅ | Same |
| `/approval` | `/approval` | ✅ | Same |
| `/checkpoint` | `/checkpoint` | ✅ | Same |
| `/team` | `/team` | ✅ | Same |
| `/mode` | `/mode` | ✅ | Same |
| `/schedule` | `/schedule` | ✅ | Same |
| `/connect` | `/connect` | ✅ | Same |
| `/insights` | ❌ MISSING | ❌ | Usage analytics report |
| `/btw` | ❌ MISSING | ❌ | Side question without context |
| `/simplify` | ❌ MISSING | ❌ | Three-agent review pipeline |
| `/remote-control` | ❌ MISSING | ❌ | Remote control from web |
| `/output-style` | ❌ MISSING | ❌ | Change output style |
| `/statusline` | ❌ MISSING | ❌ | Real-time context display |
| `/terminal-setup` | ❌ MISSING | ❌ | Terminal configuration |
| `/install-github-app` | ❌ MISSING | ❌ | GitHub App integration |
| `/pr_comments` | ❌ MISSING | ❌ | PR comments display |
| `/extra-usage` | ❌ MISSING | ❌ | Rate limit configuration |
| `/theme` | ❌ MISSING | ❌ | Change color theme |
| `/stats` | ❌ MISSING | ❌ | Usage statistics |
| `/name` | ❌ MISSING | ❌ | Name current session |
| `/teleport` | ❌ MISSING | ❌ | Move to web session |
| `/artifacts` | ❌ MISSING | ❌ | Interactive code generation |
| `/web-artifacts-builder` | ❌ MISSING | ❌ | Build HTML/JS/CSS artifacts |
| `/grill` | ❌ MISSING | ❌ | Tough code review |
| `/ultra-think` | ❌ MISSING | ❌ | Deep thinking mode |
| `/step-by-step` | ❌ MISSING | ❌ | Step-by-step explanation |
| `/conservative` | ❌ MISSING | ❌ | Conservative mode |
| `/handover` | ❌ MISSING | ❌ | Session handover document |

## CLI FLAGS

| Claude Code Flag | Dev Agent Flag | Status |
|------------------|----------------|--------|
| `--print` / `-p` | `--print` | ✅ |
| `--resume` / `-c` | `--resume` | ✅ |
| `--model` | `--model` | ✅ |
| `--dangerously-skip-permissions` | `--dangerously-skip-permissions` | ✅ |
| `--allowedTools` | `--allowed-tools` | ✅ |
| `--max-turns` | `--max-turns` | ✅ |
| `--output-format json` | `--output-format` | ✅ |
| `--worktree` / `-w` | ❌ MISSING | ❌ |
| `--agents` | `--agents` | ✅ |
| `--system-prompt` | `--system-prompt` | ✅ |
| `--system-prompt-file` | `--system-prompt-file` | ✅ |
| `--name` | `--name` | ✅ |
| `--no-session-persistence` | `--no-session-persistence` | ✅ |
| `--ref` | `--ref` | ✅ |
| `--chrome` | `--chrome` | ✅ |
| `--ide` | `--ide` | ✅ |
| `--tools` | `--tools` | ✅ |
| `--json-schema` | `--json-schema` | ✅ |
| `--input-format` | `--input-format` | ✅ |
| `--plugin-dir` | `--plugin-dir` | ✅ |
| `--plugin-url` | `--plugin-url` | ✅ |

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
| Free APIs | ❌ | ✅ (137) | ✅ Dev wins |
| MCP servers | ✅ (built-in) | ✅ (57) | ✅ Dev wins |
| Skills | ✅ (built-in) | ✅ (40+) | ✅ Dev wins |
| 24/7 operation | ❌ | ✅ | ✅ Dev wins |
| Free tier | ❌ ($20/mo) | ✅ | ✅ Dev wins |
| Multi-key rotation | ❌ | ✅ (3 keys) | ✅ Dev wins |
| Open source | ❌ | ✅ | ✅ Dev wins |

## GAPS TO FIX (Claude Code has, Dev doesn't)

### Critical (Must Have)
1. `/insights` — Usage analytics HTML report
2. `/btw` — Side question without context pollution
3. `/simplify` — Three-agent review pipeline
4. `/output-style` — Change output style (default/explanatory/learning)
5. `/statusline` — Real-time context display in status bar
6. `/theme` — Change color theme
7. `/stats` — Usage statistics
8. `/name` — Name current session
9. `/pr_comments` — PR comments display
10. `/install-github-app` — GitHub App integration

### Nice to Have
11. `/remote-control` — Remote control from web
12. `/teleport` — Move to web session
13. `/artifacts` — Interactive code generation
14. `/web-artifacts-builder` — Build HTML/JS/CSS artifacts
15. `/grill` — Tough code review
16. `/ultra-think` — Deep thinking mode
17. `/step-by-step` — Step-by-step explanation
18. `/conservative` — Conservative mode
19. `/handover` — Session handover document
20. `/extra-usage` — Rate limit configuration
21. `/terminal-setup` — Terminal configuration
22. `--worktree` flag — Isolated git worktree session
