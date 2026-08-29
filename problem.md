# Dev-Agent: Comprehensive Issue List

**Date**: 2026-08-30
**Codebase**: 146 Python files, 47,902 lines, 262 tests
**Current State**: Functional but needs hardening to surpass leading CLI agents

---

## Current Stats

| Metric | Count | vs Claude Code |
|--------|-------|----------------|
| CLI Commands | 101 | ~100 |
| Slash Commands | 84 | ~60 |
| Tool Classes | 63 | ~30 |
| Free APIs | 140 | 0 |
| MCP Servers | 65 | ~20 |
| Skills | 1,532 | ~50 |
| Security Layers | 7 | ~3 |
| Integration Tests | 26 | N/A |
| Unit Tests | 236 | ~500 |

---

## CRITICAL (Blocks production use)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 1 | **production_loop.py is 3,488 lines** | `dev/agents/production_loop.py` | Split into: tool_executor.py, message_formatter.py, auto_design.py, context_manager.py |
| 2 | **skill_integration.py is 2,194 lines** | `dev/agents/skill_integration.py` | Lazy-load skills per-category instead of loading all 1,532 at startup |
| 3 | **229 bare `except Exception:` blocks** | Throughout | Add specific exception types and logging to each |
| 4 | **No integration test for `chat` command** | `tests/` | The primary user-facing feature has zero test coverage |
| 5 | **No type checking enforced** | `pyproject.toml` | Add mypy config, fix type errors incrementally |

---

## HIGH (Degrades reliability and UX)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 6 | **chat.py is 1,689 lines** | `dev/cli/chat.py` | Extract slash command handling into dedicated handler class |
| 7 | **util_cmd.py is 933 lines** | `dev/cli/util_cmd.py` | Split into setup_cmd.py and feature_cmd.py |
| 8 | **tool_defs.py is 715 lines of redundant definitions** | `dev/tools/tool_defs.py` | Remove — tool schemas already in tool classes |
| 9 | **feature_parity.py is 822 lines of dead code** | `dev/utils/feature_parity.py` | Remove or convert to actual implementations |
| 10 | **free_apis.py is 2,087 lines of hardcoded data** | `dev/apis/free_apis.py` | Convert to JSON/YAML data file |
| 11 | **No retry logic in chat streaming** | `dev/cli/chat.py` | Add exponential backoff on NIM failures |
| 12 | **No session auto-save on crash** | `dev/cli/chat.py` | Save conversation in exception handler |
| 13 | **Context bar doesn't update live** | `dev/cli/chat.py` | Update after each tool call, not just turn end |
| 14 | **No token budget enforcement** | `dev/agents/production_loop.py` | Stop agent when budget exceeded |
| 15 | **MCP client has no connection pooling** | `dev/mcp/client.py` | Cache connections, reuse across requests |

---

## MEDIUM (Feature gaps vs leading tools)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 16 | **No `/doctor` wired to slash commands** | `dev/cli/chat.py` | Add `/doctor` to slash command handler |
| 17 | **No `/undo` in streaming path** | `dev/cli/chat.py` | Wire undo to slash commands |
| 18 | **No `/redo` wiring in chat** | `dev/cli/chat.py` | Wire redo to slash commands |
| 19 | **No session resume from crash** | `dev/cli/chat.py` | Auto-detect last session on startup |
| 20 | **No live token count in streaming** | `dev/cli/chat.py` | Show tokens as they're generated |
| 21 | **No model switching mid-session** | `dev/cli/chat.py` | `/model` command doesn't reinitialize provider |
| 22 | **No parallel tool execution** | `dev/agents/production_loop.py` | Execute independent tools concurrently |
| 23 | **No tool result caching** | `dev/agents/production_loop.py` | Cache identical tool calls to save tokens |
| 24 | **No conversation branching** | `dev/utils/history.py` | Support tree-shaped conversation history |
| 25 | **No image generation tool** | `dev/tools/` | Add DALL-E/Stable Diffusion integration |
| 26 | **No voice input support** | `dev/cli/` | Add Whisper integration for voice commands |
| 27 | **No terminal recording** | `dev/cli/` | Record terminal sessions for replay |
| 28 | **No diff preview before apply** | `dev/agents/production_loop.py` | Show diff, wait for approval, then apply |
| 29 | **No multi-file atomic edits** | `dev/tools/` | Edit multiple files in single transaction |
| 30 | **No project template system** | `dev/` | `dev init --template react` scaffolds project |
| 31 | **No dependency auto-install** | `dev/agents/production_loop.py` | Auto-install missing packages |
| 32 | **No test auto-run after edits** | `dev/agents/production_loop.py` | Run tests after file changes |
| 33 | **No lint auto-fix** | `dev/agents/production_loop.py` | Auto-fix lint errors after edits |
| 34 | **No git auto-commit** | `dev/agents/production_loop.py` | Commit after each successful edit |
| 35 | **No PR creation command** | `dev/cli/` | `dev pr create` opens PR with AI description |
| 36 | **No issue creation command** | `dev/cli/` | `dev issue create` creates GitHub issue |
| 37 | **No CI/CD integration** | `dev/cli/` | `dev ci status` shows pipeline status |
| 38 | **No deployment command** | `dev/cli/` | `dev deploy` deploys to Vercel/Railway/etc |
| 39 | **No database integration** | `dev/tools/` | Add PostgreSQL/SQLite query tool |
| 40 | **No API testing tool** | `dev/tools/` | Add curl/HTTP client tool |
| 41 | **No performance profiling** | `dev/tools/` | Add cProfile/py-spy integration |
| 42 | **No memory consolidation** | `dev/utils/memory.py` | Merge similar memories, deduplicate |
| 43 | **No conversation summarization** | `dev/agents/compaction.py` | Summarize long conversations for context |
| 44 | **No multi-language detection** | `dev/utils/project_detector.py` | Detect Rust, Go, Java, etc. |
| 45 | **No Docker integration** | `dev/tools/` | Add docker-compose management |
| 46 | **No Kubernetes support** | `dev/tools/` | Add kubectl integration |
| 47 | **No Terraform support** | `dev/tools/` | Add infrastructure-as-code tools |
| 48 | **No Ansible support** | `dev/tools/` | Add configuration management |
| 49 | **No monitoring integration** | `dev/tools/` | Add Prometheus/Grafana tools |
| 50 | **No logging integration** | `dev/tools/` | Add ELK/Loki query tools |

---

## LOW (Nice-to-haves)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 51 | **No TUI themes** | `dev/cli/tui.py` | Add color themes (dracula, monokai, etc.) |
| 52 | **No keyboard shortcuts** | `dev/cli/` | Add Ctrl+R history search, Ctrl+T toggle |
| 53 | **No mouse support** | `dev/cli/tui.py` | Add clickable buttons in terminal |
| 54 | **No Unicode box drawing** | `dev/cli/tui.py` | Use proper Unicode characters |
| 55 | **No progress bars** | `dev/cli/` | Add progress bars for long operations |
| 56 | **No spinners** | `dev/cli/` | Add loading spinners for API calls |
| 57 | **No notifications** | `dev/cli/` | Desktop notifications on task completion |
| 58 | **No clipboard integration** | `dev/cli/` | Auto-copy responses to clipboard |
| 59 | **No file drag-and-drop** | `dev/cli/` | Support drag-and-drop in terminal |
| 60 | **No session export** | `dev/utils/history.py` | Export to Markdown/PDF/HTML |
| 61 | **No conversation search** | `dev/utils/history.py` | Full-text search across sessions |
| 62 | **No analytics dashboard** | `dev/` | Web dashboard for usage stats |
| 63 | **No plugin marketplace** | `dev/` | Community plugins repository |
| 64 | **No theme marketplace** | `dev/` | Community themes repository |
| 65 | **No skill marketplace** | `dev/` | Community skills repository |
| 66 | **No API rate limit display** | `dev/providers/` | Show RPM remaining in status bar |
| 67 | **No cost prediction** | `dev/utils/` | Estimate cost before running task |
| 68 | **No token usage graphs** | `dev/` | Visualize token usage over time |
| 69 | **No session replay** | `dev/utils/history.py` | Replay session step-by-step |
| 70 | **No diff visualization** | `dev/cli/` | Side-by-side diff in terminal |
| 71 | **No syntax highlighting** | `dev/cli/` | Highlight code in responses |
| 72 | **No markdown rendering** | `dev/cli/` | Full markdown support in terminal |
| 73 | **No table rendering** | `dev/cli/` | Rich table display for data |
| 74 | **No chart rendering** | `dev/cli/` | ASCII charts for metrics |
| 75 | **No file tree display** | `dev/cli/` | Visual file tree in terminal |

---

## ARCHITECTURE (Code quality issues)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 76 | **production_loop.py has 70+ methods** | `dev/agents/production_loop.py` | Split into focused classes |
| 77 | **chat.py has 84 slash commands inline** | `dev/cli/chat.py` | Extract to slash_commands.py handler |
| 78 | **No dependency injection** | Throughout | Use DI container for providers |
| 79 | **No event system** | Throughout | Add event bus for decoupled communication |
| 80 | **No plugin architecture** | Throughout | Formalize plugin loading system |
| 81 | **No configuration validation** | `dev/config/` | Add JSON schema validation |
| 82 | **No migration system** | `dev/config/` | Handle config format changes |
| 83 | **No backwards compatibility** | `dev/cli/` | Version compat layer for old configs |
| 84 | **No API versioning** | `dev/providers/` | Support multiple API versions |
| 85 | **No graceful degradation** | Throughout | Fallback when features unavailable |
| 86 | **No circuit breaker** | `dev/providers/` | Stop calling failed providers |
| 87 | **No bulkhead pattern** | `dev/providers/` | Isolate provider failures |
| 88 | **No retry budget** | `dev/providers/` | Limit total retries per session |
| 89 | **No health checks** | `dev/providers/` | Periodic provider health checks |
| 90 | **No metrics collection** | `dev/` | Prometheus metrics endpoint |
| 91 | **No distributed tracing** | `dev/` | OpenTelemetry integration |
| 92 | **No structured logging** | `dev/` | JSON logging with correlation IDs |
| 93 | **No log levels** | `dev/` | DEBUG/INFO/WARN/ERROR levels |
| 94 | **No feature flags** | `dev/` | Toggle features without redeploy |
| 95 | **No A/B testing** | `dev/` | Test different prompts/models |

---

## TESTING (Coverage gaps)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 96 | **No test for `chat` command** | `tests/` | Add end-to-end chat test |
| 97 | **No test for `run` command** | `tests/` | Add end-to-end run test |
| 98 | **No test for slash commands** | `tests/` | Test each slash command |
| 99 | **No test for session management** | `tests/` | Test resume/fork/stop |
| 100 | **No test for team commands** | `tests/` | Test team create/status/list |
| 101 | **No test for MCP integration** | `tests/` | Test MCP server connections |
| 102 | **No test for security layers** | `tests/` | Test injection detection |
| 103 | **No test for sandbox** | `tests/` | Test command blocking |
| 104 | **No test for compaction** | `tests/` | Test context compression |
| 105 | **No test for streaming** | `tests/` | Test token-by-token output |
| 106 | **No test for error recovery** | `tests/` | Test retry logic |
| 107 | **No test for rate limiting** | `tests/` | Test key rotation |
| 108 | **No test for tool execution** | `tests/` | Test each tool class |
| 109 | **No test for provider fallback** | `tests/` | Test NIM→OpenRouter fallback |
| 110 | **No test for system prompt** | `tests/` | Test prompt building |
| 111 | **No test for project detection** | `tests/` | Test language detection |
| 112 | **No test for auto-commit** | `tests/` | Test git operations |
| 113 | **No test for checkpoint system** | `tests/` | Test undo/redo |
| 114 | **No test for memory system** | `tests/` | Test auto-memory |
| 115 | **No test for rules system** | `tests/` | Test .devrules loading |

---

## DOCUMENTATION (Missing docs)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 116 | **README.md is placeholder** | `README.md` | Write comprehensive docs |
| 117 | **No API documentation** | `dev/` | Generate API docs from docstrings |
| 118 | **No architecture diagram** | `docs/` | Create system architecture diagram |
| 119 | **No contribution guide** | `CONTRIBUTING.md` | Write contributor guidelines |
| 120 | **No changelog** | `CHANGELOG.md` | Maintain changelog |
| 121 | **No release notes** | `RELEASES.md` | Document each release |
| 122 | **No troubleshooting guide** | `docs/` | Common issues and fixes |
| 123 | **No examples** | `examples/` | Usage examples |
| 124 | **No benchmarks** | `bench/` | Performance benchmarks |
| 125 | **No security policy** | `SECURITY.md` | Security disclosure policy |

---

## PRIORITY ORDER

1. **Fix #1-5** (Critical) — production_loop.py split, skill lazy-loading, bare excepts, chat test, mypy
2. **Fix #6-15** (High) — chat.py split, tool_defs removal, retry logic, session save
3. **Fix #16-50** (Medium) — Feature gaps vs leading tools
4. **Fix #51-75** (Low) — Nice-to-haves
5. **Fix #76-95** (Architecture) — Code quality improvements
6. **Fix #96-115** (Testing) — Test coverage
7. **Fix #116-125** (Documentation) — Docs

---

## TOTAL: 125 issues identified
- Critical: 5
- High: 10
- Medium: 35
- Low: 25
- Architecture: 20
- Testing: 20
- Documentation: 10
