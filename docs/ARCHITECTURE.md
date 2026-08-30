# Dev Agent — Architecture Guide

Technical architecture documentation for contributors and advanced users.

---

## Overview

Dev Agent is a CLI coding agent built in Python. It uses a modular architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   main.py │  │  chat.py │  │ run_cmd  │  │ util_cmd │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       └──────────────┴──────────────┴──────────────┘        │
│                          │                                  │
│  ┌───────────────────────┴──────────────────────────────┐   │
│  │              shared.py (app, config, provider)        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────┴───────────────────────────────────┐
│                      Agent Layer                            │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ ProductionLoop    │  │ SkillIntegration │                │
│  │ (2848 lines)      │  │ (2194 lines)     │                │
│  └────────┬─────────┘  └────────┬─────────┘                │
│           │                     │                           │
│  ┌────────┴─────────┐  ┌────────┴─────────┐                │
│  │ ToolExecutor     │  │ CompactionEngine │                │
│  │ (370 lines)       │  │ (580 lines)      │                │
│  └────────┬─────────┘  └────────┬─────────┘                │
│           │                     │                           │
│  ┌────────┴─────────┐  ┌────────┴─────────┐                │
│  │ SystemPrompt     │  │ TeamAgent        │                │
│  │ (258 lines)       │  │ (multi-agent)    │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────┴───────────────────────────────────┐
│                      Tool Layer                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ real_    │  │ browser_ │  │ computer_│  │ api_     │   │
│  │ tools    │  │ tools    │  │ use      │  │ tools    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ mcp_     │  │ deploy_  │  │ visual_  │  │ team_    │   │
│  │ tools    │  │ tool     │  │ review   │  │ tools    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────┴───────────────────────────────────┐
│                    Provider Layer                           │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ UnifiedProvider   │  │ NimProvider      │                │
│  │ (multi-provider)  │  │ (NVIDIA NIM)     │                │
│  └────────┬─────────┘  └────────┬─────────┘                │
│           │                     │                           │
│  ┌────────┴─────────┐  ┌────────┴─────────┐                │
│  │ OpenRouter        │  │ Bytez            │                │
│  │ Provider          │  │ Provider         │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────┴───────────────────────────────────┐
│                    Security Layer                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Injection│  │ Tool     │  │ Rate     │  │ Audit    │   │
│  │ Detector │  │Validator │  │ Limiter  │  │ Logger   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Sand-box │  │ Encrypt  │  │ Red Team │                  │
│  │ Manager  │  │ Keys     │  │ Tester   │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. CLI Layer (`dev/cli/`)

The CLI layer handles user interaction, command parsing, and output formatting.

| File | Lines | Responsibility |
|------|-------|----------------|
| `main.py` | 34 | Thin entrypoint importing all modules |
| `shared.py` | 244 | Config, provider, runtime, constants |
| `chat.py` | 801 | Interactive chat + streaming display |
| `slash_handler.py` | 1100 | 95+ slash commands |
| `run_cmd.py` | 267 | Single-task execution |
| `session_cmd.py` | 299 | Session lifecycle |
| `agent_cmd.py` | 210 | Multi-agent management |
| `tools_cmd.py` | 221 | Tool and MCP management |
| `util_cmd.py` | 1132 | All utility commands |
| `slash_commands.py` | 559 | Legacy slash commands |
| `tui.py` | ~200 | Terminal UI components |

**Key Design:**
- Uses Typer for CLI framework
- Rich for terminal output (panels, tables, markdown)
- Async/await throughout for non-blocking I/O
- Sub-apps pattern: each module registers commands on the shared `app` instance

### 2. Agent Layer (`dev/agents/`)

The agent layer implements the AI loop, tool execution, and context management.

| File | Lines | Responsibility |
|------|-------|----------------|
| `production_loop.py` | 2848 | Main agent loop with streaming |
| `skill_integration.py` | 2194 | Skill loading and matching |
| `compaction.py` | 580 | Context compaction engine |
| `tool_executor.py` | 370 | Tool execution with approval |
| `system_prompt.py` | 258 | System prompt construction |
| `loop_types.py` | 115 | Data classes and constants |
| `teams.py` | ~500 | Multi-agent team management |
| `super_agent.py` | ~200 | High-level agent orchestration |
| `agent_definition.py` | ~300 | Agent role definitions |
| `model_router.py` | ~300 | Model selection based on task |
| `commands.py` | ~800 | Agent-level commands |

**ProductionAgentLoop** is the heart of the system:

```python
class ProductionAgentLoop(ToolExecutorMixin, SystemPromptMixin):
    """
    Main agent loop with:
    - Streaming text output
    - Tool calling and execution
    - Auto-compact at 75% context
    - Retry with exponential backoff
    - Error recovery
    - Git diff display
    """
    
    async def run_streaming(self, prompt, system_prompt, ...):
        while step < max_steps:
            # 1. Format messages
            messages = self._format_messages(system_prompt)
            
            # 2. Auto-compact if needed
            messages = self._auto_compact_if_needed(messages, system_prompt)
            
            # 3. Call LLM with streaming
            async for event in self.provider.stream_events(messages, tools):
                if event["type"] == "text":
                    yield event["text"]  # Stream to user
                elif event["type"] == "tool_use":
                    # 4. Execute tool
                    result = await self._execute_tool(event["tool"], event["args"])
                    yield {"tool": event["tool"], "result": result}
            
            # 5. Check if done
            if no_more_tool_calls:
                break
```

### 3. Tool Layer (`dev/tools/`)

Tools are the agent's interface to the outside world. Each tool is a class with:
- `name`: Tool identifier
- `description`: What the tool does
- `parameters`: JSON Schema for inputs
- `execute()`: Async method to run the tool

| File | Tools | Purpose |
|------|-------|---------|
| `real_tools.py` | 11 | Core: write, read, replace, search, terminal, git |
| `browser_tools.py` | 5 | Browser: screenshot, navigate, click, evaluate |
| `computer_use.py` | 6 | Desktop: screenshot, mouse, keyboard |
| `api_tools.py` | 5 | API: free_api, web_search, read_url |
| `mcp_tools.py` | 5 | MCP: connect, list, call |
| `deploy_tool.py` | 1 | Deploy to hosting platforms |
| `visual_review.py` | 2 | Screenshot + AI design review |
| `design_fetcher.py` | 2 | Fetch design systems |
| `team_tools.py` | 5 | Multi-agent: spawn, execute, list |
| `session_messaging.py` | 5 | Cross-session communication |
| `context_tools.py` | 3 | Context: todos, ask_user, followups |
| `monitor.py` | 4 | Monitoring: start, stop, status |
| `sandbox_tools.py` | 2 | Sandboxed execution |
| `multi_edit_tool.py` | 1 | Atomic multi-file edits |
| `multimodal_tools.py` | 2 | Image analysis |
| `patch_tools.py` | 2 | Git-style patches |
| `skill_tool.py` | 1 | Skill loading |
| `tool_search.py` | 1 | Tool discovery |
| `agent_tools.py` | 3 | Agent management |

### 4. Provider Layer (`dev/providers/`)

Providers handle communication with AI models.

| File | Responsibility |
|------|----------------|
| `unified_provider.py` | Multi-provider routing with fallback |
| `nim_provider.py` | NVIDIA NIM API client |
| `openrouter_provider.py` | OpenRouter API client |

**UnifiedProvider** routes requests:

```python
class UnifiedProvider:
    """
    Routes requests to the best available provider:
    1. Try primary provider (NVIDIA NIM)
    2. On failure, try fallback (OpenRouter)
    3. On rate limit, rotate keys
    """
    
    def resolve_model(self, task_type, has_tools):
        # Route to best model for the task
        if task_type == "vision":
            return "nvidia", "meta/llama-3.2-11b-vision"
        elif has_tools:
            return "nvidia", "meta/llama-3.1-70b-instruct"
        else:
            return "nvidia", "meta/llama-3.1-8b-instruct"
```

### 5. Security Layer (`dev/security/`)

| File | Responsibility |
|------|----------------|
| `injection_detector.py` | Detects prompt injection attacks |
| `tool_validator.py` | Validates tool inputs and rate limits |
| `audit.py` | Logs all actions for review |
| `sandbox_manager.py` | Command sandboxing |
| `encryption.py` | API key encryption at rest |
| `red_team.py` | Security testing suite |

---

## Data Flow

### Chat Interaction Flow

```
User types message
        │
        ▼
┌─────────────────┐
│  Slash Handler  │──→ /command handled? → Return
└────────┬────────┘
         │ (not a slash command)
         ▼
┌─────────────────┐
│  Injection      │──→ Blocked? → Reject
│  Detector       │
└────────┬────────┘
         │ (clean)
         ▼
┌─────────────────┐
│  Context        │──→ Compacted? → New context
│  Manager        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLM Provider   │──→ API call with streaming
│  (NIM/OpenRouter)│
└────────┬────────┘
         │ (streaming events)
         ▼
┌─────────────────┐
│  Tool Executor  │──→ Execute tool → Return result
└────────┬────────┘
         │ (text events)
         ▼
┌─────────────────┐
│  Streaming      │──→ Display to user
│  Display        │
└────────┬────────┘
         │ (loop if more tool calls)
         ▼
┌─────────────────┐
│  Session        │──→ Save to disk
│  Manager        │
└─────────────────┘
```

### Tool Execution Flow

```
LLM requests tool call
        │
        ▼
┌─────────────────┐
│  Tool Validator │──→ Rate limited? → Reject
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Approval       │──→ Needs approval? → Prompt user
│  Checker        │
└────────┬────────┘
         │ (approved)
         ▼
┌─────────────────┐
│  Backup         │──→ Backup file (for undo)
│  Manager        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Tool           │──→ Execute the tool
│  Implementation │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Audit          │──→ Log the action
│  Logger         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Git Diff       │──→ Show changes (if file modified)
│  Display        │
└─────────────────┘
```

---

## Context Management

### Token Counting

Dev Agent counts tokens using a simple heuristic:
- 1 token ≈ 4 characters (English text)
- Tool definitions add ~100 tokens each
- System prompt adds ~2000 tokens

### Auto-Compact

When context exceeds 75% of the model's limit:

1. **Memory Flush**: Save important notes to memory file
2. **Identifier Extraction**: Extract key identifiers to preserve
3. **LLM Summarization**: Use the model to summarize old messages
4. **Quality Audit**: Verify summary preserves critical information
5. **Context Rebuild**: Create new context with summary + recent messages

### Context Pruning

Before compaction, simple pruning removes:
- Duplicate tool results
- Very large tool outputs (truncated to 1000 chars)
- Old thinking blocks
- Stale system messages

---

## Multi-Agent Architecture

### TeamAgent

Allows multiple agents to work in parallel:

```python
class TeamAgent:
    """Coordinates multiple agents working on subtasks."""
    
    async def execute_team_task(self, task, agents):
        # 1. Break task into subtasks
        subtasks = await self._plan_subtasks(task, agents)
        
        # 2. Assign subtasks to agents
        assignments = self._assign_subtasks(subtasks, agents)
        
        # 3. Execute in parallel
        results = await asyncio.gather(*[
            agent.run(subtask) for agent, subtask in assignments
        ])
        
        # 4. Merge results
        return self._merge_results(results)
```

### ParallelAgent

Runs multiple agent instances in parallel with git worktree isolation:

```python
class ParallelAgent:
    """Runs agents in parallel with isolated worktrees."""
    
    async def run_parallel(self, task, num_agents=3):
        # 1. Create worktrees
        worktrees = [self._create_worktree(i) for i in range(num_agents)]
        
        # 2. Run agents in parallel
        results = await asyncio.gather(*[
            self._run_in_worktree(task, wt) for wt in worktrees
        ])
        
        # 3. Merge worktrees
        return self._merge_worktrees(results)
```

---

## Error Handling

### Retry with Exponential Backoff

```python
async def _call_llm_with_retry(self, messages, tools, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await self.provider.chat_completion(messages, tools)
        except RateLimitError:
            wait = 2 ** attempt * 5  # 5, 10, 20 seconds
            await asyncio.sleep(wait)
        except APIError as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)
```

### Error Recovery

When a tool call fails:

1. **Log the error** with full context
2. **Report to LLM** so it can adjust
3. **Continue the loop** (don't crash)
4. **Track error patterns** for auto-fix

---

## Performance Optimizations

### 1. Lazy Loading

Skills, APIs, and MCP servers are loaded on-demand, not at startup:
- Skills: Loaded when `/skill` is used
- APIs: Loaded when `free_api` tool is called
- MCP: Connected when `mcp_connect` tool is called

### 2. Context Compaction

Auto-compacts at 75% context to prevent hitting limits:
- More aggressive than Claude Code (95%)
- Preserves critical information via LLM summarization
- Saves ~30-50% of context tokens

### 3. Tool Caching

Tool results are cached to avoid re-execution:
- File reads: Cached for 5 seconds
- Web searches: Cached for 60 seconds
- API calls: Cached for 30 seconds

### 4. Streaming

Token-by-token streaming for responsive UX:
- Text streams as it's generated
- Tool calls execute immediately
- Progress indicators for long operations

---

## Testing Strategy

### Unit Tests (235+)

- Tool implementations
- Provider logic
- Agent loop logic
- Security validators
- Context management

### Integration Tests (26)

- Real NIM API calls
- Streaming verification
- Tool execution
- Rate limiting
- Error handling

### Security Tests (12)

- Injection detection
- Sandbox enforcement
- Rate limiting
- Encryption

### Running Tests

```bash
# All tests
python -m pytest tests/ -q

# Unit only
python -m pytest tests/ -q --ignore=tests/test_integration_nim.py

# Integration only
python -m pytest tests/test_integration_nim.py -q -m integration

# With coverage
python -m pytest tests/ --cov=dev --cov-report=term-missing
```

---

## Adding New Features

### Adding a New Tool

1. Create class in `dev/tools/`:
```python
class MyNewTool(Tool):
    name = "my_new_tool"
    description = "What it does"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input"}
        },
        "required": ["input"]
    }
    
    async def execute(self, input_data, state, project_path):
        # Implementation
        return {"result": "..."}
```

2. Register in `dev/cli/commands.py`:
```python
registry.register("my_new_tool", MyNewTool())
```

3. Add to tool definitions in `dev/tools/tool_defs.py`

4. Write tests in `tests/`

### Adding a New Slash Command

1. Add handler in `dev/cli/slash_handler.py`:
```python
if cmd == "/my-command":
    # Handle command
    self.console.print("Done!")
    return "continue", True
```

2. Update `/help` in `dev/cli/chat.py`

3. Write tests in `tests/test_chat_command.py`

### Adding a New API Integration

1. Add config in `dev/apis/free_apis.py`:
```python
{
    "name": "My API",
    "url": "https://api.example.com",
    "auth": "api_key",
    "auth_header": "X-API-Key",
    "endpoints": [...]
}
```

2. Test with `free_api` tool in chat

---

## Design Principles

1. **Free by Default**: Every feature uses free APIs and free-tier models
2. **Tool-First**: Every capability is exposed as a tool the AI can call
3. **Security by Default**: All actions validated, rate-limited, and audited
4. **Graceful Degradation**: If one provider fails, fall back to another
5. **Context Efficiency**: Aggressive compaction to fit more in context
6. **Modular Design**: Each component is independent and testable
7. **No Global Installs**: Everything runs in a virtual environment
