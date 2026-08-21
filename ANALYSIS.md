# Dev Agent - Open Source Codebase Analysis

## Date: August 20, 2026

## Repos Analyzed

| # | Repo | Stars | Language | Files | Key Pattern |
|---|------|-------|----------|-------|-------------|
| 1 | Freebuff (CodebuffAI/freebuff) | - | TypeScript/Bun | 1,418 | Multi-agent orchestration |
| 2 | Aider (Aider-AI/aider) | - | Python | 691 | Coder strategies, git integration |
| 3 | OpenHands (OpenHands/OpenHands) | - | TypeScript | 2,058 | Agent Canvas, automation |
| 4 | Codex (openai/codex) | - | Rust/TS | 6,394 | Sandboxing, exec policies |
| 5 | Continue (continuedev/continue) | 35.5k | TypeScript | 3,058 | Autocomplete, IDE integration |
| 6 | Qwen Code (QwenLM/qwen-code) | 27.2k | TypeScript | 8,555 | Workflow orchestrator, team agents |
| 7 | Plandex (plandex-ai/plandex) | 15.6k | Go | 696 | Server architecture, plan-based |
| 8 | Kilocode (Kilo-Org/kilocode) | 26.9k | TypeScript | 9,522 | Effect system, state management |

---

## 1. FREEBUFF (CodebuffAI/freebuff)

### Architecture
```
freebuff/
├── agents/          # Agent definitions (TypeScript generators)
│   ├── base-chat.ts         # Main chat agent
│   ├── base2/               # Model-specific variants
│   ├── base3/               # More variants
│   ├── thinker/             # Reasoning agent
│   ├── reviewer/            # Code review agent
│   ├── editor/              # Code editing agent
│   ├── file-explorer/       # File discovery agent
│   ├── researcher/          # Web research agent
│   ├── browser-use/         # Browser automation
│   ├── librarian/           # Documentation agent
│   ├── general-agent/       # General purpose
│   ├── types/               # Agent type definitions
│   └── constants.ts         # Shared constants
├── cli/             # Terminal UI (React/Ink)
│   └── src/
│       ├── entry.ts         # CLI entry point
│       ├── commands/        # Slash commands
│       ├── components/      # UI components
│       ├── hooks/           # React hooks
│       ├── state/           # State management
│       └── utils/           # Utilities
├── sdk/             # Core SDK
│   └── src/
│       ├── run.ts           # Main agent loop
│       ├── run-state.ts     # Session state
│       ├── client.ts        # API client
│       ├── impl/
│       │   ├── agent-runtime.ts  # Runtime implementation
│       │   ├── llm.ts            # LLM integration (Vercel AI SDK)
│       │   └── model-provider.ts # Model routing
│       ├── tools/           # Tool implementations
│       │   ├── read-files.ts
│       │   ├── change-file.ts
│       │   ├── apply-patch.ts
│       │   ├── code-search.ts
│       │   ├── glob.ts
│       │   ├── list-directory.ts
│       │   ├── run-terminal-command.ts
│       │   └── read-url.ts
│       └── agents/          # Agent loading
├── common/          # Shared types and utilities
└── evals/           # Evaluation framework
```

### Key Patterns Extracted

#### A. Agent Definition Pattern
```typescript
// agents/types/agent-definition.ts
interface AgentDefinition {
  id: string
  displayName: string
  model: ModelName
  toolNames: ToolName[]
  spawnableAgents: string[]
  systemPrompt: string
  instructionsPrompt: string
  handleSteps: Generator  // KEY: Programmatic step control
  outputMode: 'last_message' | 'all_messages' | 'structured_output'
  mcpServers: Record<string, MCPConfig>
}
```

#### B. handleSteps Generator Pattern
```typescript
// Each agent can control its execution flow via a generator
handleSteps: function* ({ model }) {
  while (true) {
    // Spawn sub-agent before each step
    yield { toolName: 'spawn_agent_inline', input: { agent_type: 'context-pruner' } }
    const { stepsComplete } = yield 'STEP'
    if (stepsComplete) break
  }
}
```

#### C. Tool System
- 30+ tools defined in `agents/types/tools.ts`
- OpenAI-compatible function calling format
- Tools: read_files, write_file, str_replace, code_search, glob, list_directory, run_terminal_command, web_search, read_url, spawn_agents, write_todos, task_completed, etc.

#### D. SDK Runtime (sdk/src/run.ts)
- Manages agent execution lifecycle
- Handles tool dispatch
- Context pruning and compaction
- MCP client integration
- File system operations

#### E. LLM Integration (sdk/src/impl/llm.ts)
- Uses Vercel AI SDK (`ai` package)
- OpenRouter as model provider
- Provider routing with fallbacks
- Streaming support
- Usage tracking

### What We Take From Freebuff
1. **Agent definition pattern** with handleSteps generators
2. **Tool system** with OpenAI-compatible format
3. **Multi-agent spawning** pattern
4. **Context pruning** approach
5. **MCP integration** pattern

---

## 2. AIDER (Aider-AI/aider)

### Architecture
```
aider/
├── aider/
│   ├── main.py              # CLI entry point
│   ├── llm.py               # LiteLLM integration (lazy loading)
│   ├── models.py            # Model configuration
│   ├── repo.py              # Git repository management
│   ├── repomap.py           # Repository map (tree-sitter based)
│   ├── io.py                # Input/Output handling
│   ├── commands.py          # Slash commands
│   ├── linter.py            # Code linting
│   ├── history.py           # Chat history/summarization
│   ├── run_cmd.py           # Shell command execution
│   ├── scrape.py            # Web scraping
│   ├── voice.py             # Voice input
│   ├── watch.py             # File watching
│   ├── coders/              # Different coding strategies
│   │   ├── base_coder.py    # Base coder class
│   │   ├── editblock_coder.py    # Edit block format
│   │   ├── wholefile_coder.py    # Whole file replacement
│   │   ├── udiff_coder.py        # Unified diff format
│   │   ├── architect_coder.py    # Architect mode
│   │   ├── editor_*.py           # Editor variants
│   │   └── ... (12+ coder types)
│   └── prompts/             # System prompts
├── benchmark/               # Evaluation benchmarks
└── tests/                   # Test suite
```

### Key Patterns Extracted

#### A. LiteLLM Integration
```python
# aider/llm.py - Lazy loading pattern
class LazyLiteLLM:
    _lazy_module = None
    def __getattr__(self, name):
        if self._lazy_module is None:
            self._lazy_module = importlib.import_module("litellm")
            self._lazy_module.drop_params = True
        return getattr(self._lazy_module, name)

litellm = LazyLiteLLM()
```

#### B. Coder Strategy Pattern
```python
# aider/coders/base_coder.py
class Coder:
    @classmethod
    def create(cls, main_model, edit_format, io):
        # Factory pattern - creates appropriate coder based on edit_format
        if edit_format == "editblock":
            return EditBlockCoder(...)
        elif edit_format == "wholefile":
            return WholeFileCoder(...)
        # ... more formats
    
    def get_edits(self):
        # Each coder type implements its own edit strategy
        pass
```

#### C. Repo Map (Tree-sitter based)
```python
# aider/repomap.py
class RepoMap:
    def get_repo_map(self, chat_files, other_files):
        # Uses tree-sitter to parse code
        # Builds a map of functions/classes and their locations
        # Helps LLM understand codebase structure
        pass
```

#### D. Git Integration
```python
# aider/repo.py
class GitRepo:
    def commit(self, msg):
        # Auto-commits with sensible messages
        pass
    def get_diffs(self):
        # Gets current changes
        pass
```

### What We Take From Aider
1. **Lazy LLM loading** pattern
2. **Coder strategy pattern** (multiple edit formats)
3. **Repo map** for codebase understanding
4. **Git integration** with auto-commit
5. **File watching** for live updates

---

## 3. OPENHANDS (OpenHands/OpenHands)

### Architecture
```
OpenHands/
├── src/                # Frontend (React/TypeScript)
│   ├── api/            # API clients
│   │   ├── agent-server-adapter.ts
│   │   ├── automation-service/
│   │   └── backend-registry/
│   ├── components/     # UI components
│   ├── hooks/          # React hooks
│   ├── routes/         # Page routes
│   └── stores/         # State management
├── bin/                # Backend server
├── docker/             # Docker configurations
├── docs/               # Documentation
├── tools/              # CLI tools
│   └── canvas_ui_tool.py
├── tests/              # Test suite
├── examples/           # Example configurations
└── helm/               # Kubernetes deployment
```

### Key Patterns Extracted

#### A. Agent Canvas Architecture
- **Agent Server** - REST API for running agents
- **Agent Client** - Connects to agent servers
- **Backend Registry** - Manages multiple agent backends
- **Automation Server** - Scheduled tasks and webhooks

#### B. Multi-Backend Support
```typescript
// Can switch between different agent backends:
// - Local (direct execution)
// - Docker (sandboxed)
// - Remote (VM/cloud)
// - Cloud (OpenHands Cloud)
```

#### C. Automation Patterns
- Scheduled tasks (cron-like)
- Webhook-triggered workflows
- Slack/GitHub/Linear integrations
- Report generation

### What We Take From OpenHands
1. **Agent server** pattern for 24/7 operation
2. **Backend registry** for multiple execution environments
3. **Automation** patterns for scheduled tasks
4. **Docker sandboxing** concept

---

## 4. CODEX (openai/codex)

### Architecture
```
codex/
├── codex-rs/           # Rust core
│   ├── cli/            # CLI binary
│   ├── core/           # Core agent logic
│   ├── tools/          # Tool implementations
│   ├── mcp-server/     # MCP server
│   ├── mcp-client/     # MCP client
│   ├── sandboxing/     # Sandboxing system
│   ├── exec/           # Command execution
│   ├── file-system/    # File operations
│   ├── git-utils/      # Git operations
│   ├── model-provider/ # LLM provider
│   ├── config/         # Configuration
│   ├── tui/            # Terminal UI
│   └── ...
├── codex-cli/          # TypeScript CLI wrapper
├── sdk/                # SDK for embedding
└── docs/               # Documentation
```

### Key Patterns Extracted

#### A. Sandboxing System
```
codex-rs/sandboxing/
├── linux-sandbox/      # Linux namespaces/cgroups
├── windows-sandbox/    # Windows sandboxing
├── bwrap/              # Bubblewrap (Linux)
└── execpolicy/         # Execution policies
```

#### B. Tool System
```
codex-rs/tools/
├── shell_command/      # Shell execution
├── file_search/        # File discovery
├── apply_patch/        # Patch application
└── ...
```

#### C. MCP Integration
- Built-in MCP server
- MCP client for external servers
- Tool discovery and registration

### What We Take From Codex
1. **Sandboxing** concept for safe execution
2. **Execution policies** for tool safety
3. **MCP server/client** architecture
4. **Apply patch** tool format

---

## 5. CONTINUE (continuedev/continue)

### Architecture
```
continue/
├── core/               # Core library
│   ├── autocomplete/   # Code completion
│   ├── codeRenderer/   # Code rendering
│   ├── commands/       # Slash commands
│   ├── config/         # Configuration
│   ├── context/        # Context management
│   ├── llm/            # LLM integration
│   ├── llm-chat/       # Chat with LLM
│   ├── llm-count/      # Token counting
│   ├── llm-openai/     # OpenAI provider
│   ├── llm-vectordb/   # Vector DB integration
│   ├── platform/       # Platform abstraction
│   ├── prompts/        # Prompt templates
│   ├── services/       # Services layer
│   └── util/           # Utilities
├── extensions/         # IDE extensions
│   ├── vscode/         # VS Code extension
│   └── jetbrains/      # JetBrains plugin
├── gui/                # Web UI
├── docs/               # Documentation
└── eval/               # Evaluation
```

### Key Patterns Extracted

#### A. Autocomplete System
- Tree-sitter based parsing
- Context retrieval service
- Import definitions tracking
- Completion filtering and ranking

#### B. Context Management
- File context gathering
- Codebase indexing
- Vector DB for semantic search

#### C. Multi-Provider Support
- OpenAI, Anthropic, Google, etc.
- Local model support (via custom provider)

### What We Take From Continue
1. **Autocomplete** system design
2. **Context retrieval** patterns
3. **Multi-provider** abstraction

---

## 6. QWEN CODE (QwenLM/qwen-code)

### Architecture
```
qwen-code/
├── packages/
│   ├── core/           # Core agent system
│   │   ├── src/
│   │   │   ├── agents/
│   │   │   │   ├── runtime/
│   │   │   │   │   ├── agent-core.ts        # Core execution engine
│   │   │   │   │   ├── agent-headless.ts    # One-shot tasks
│   │   │   │   │   ├── agent-interactive.ts # Interactive mode
│   │   │   │   │   ├── workflow-orchestrator.ts # Multi-agent workflows
│   │   │   │   │   ├── workflow-budget.ts   # Token/cost budgets
│   │   │   │   │   ├── workflow-sandbox.ts  # Sandboxed execution
│   │   │   │   │   └── workflow-stall.ts    # Stall detection
│   │   │   │   ├── arena/       # Agent arena (parallel agents)
│   │   │   │   ├── team/        # Team management
│   │   │   │   └── backends/    # Execution backends
│   │   │   ├── tools/           # 91 tool files!
│   │   │   │   ├── edit.ts
│   │   │   │   ├── read-file.ts
│   │   │   │   ├── write-file.ts
│   │   │   │   ├── shell.ts
│   │   │   │   ├── web-search.ts
│   │   │   │   ├── web-fetch.ts
│   │   │   │   ├── ripGrep.ts
│   │   │   │   ├── skill.ts
│   │   │   │   ├── todoWrite.ts
│   │   │   │   ├── task-create.ts
│   │   │   │   ├── team-create.ts
│   │   │   │   ├── cron-create.ts
│   │   │   │   ├── computer-use/
│   │   │   │   └── ...
│   │   │   ├── config/          # Configuration
│   │   │   ├── services/        # Services
│   │   │   └── utils/           # Utilities
│   │   └── ...
│   ├── cli/           # CLI interface
│   ├── web-shell/     # Web-based terminal
│   └── webui/         # Web UI
├── docs/              # Documentation
└── integrations/      # Third-party integrations
```

### Key Patterns Extracted

#### A. Agent Core (agent-core.ts)
```typescript
// Stateless per-call execution engine
class AgentCore {
  // Model reasoning loop
  // Tool scheduling
  // Stats tracking
  // Event emission
  // Loop detection
  // Duplicate tool call handling
}
```

#### B. Workflow Orchestrator
```typescript
// Multi-agent workflow management
class WorkflowOrchestrator {
  // Agent dispatch (sequential, parallel, pipeline)
  // Budget management (token limits)
  // Stall detection and recovery
  // Git worktree isolation
  // Journal/checkpoint system
  // Max 1000 agents per workflow (configurable)
}
```

#### C. Team System
```typescript
// Multi-agent collaboration
class TeamManager {
  // Leader/follower pattern
  // Mailbox for inter-agent communication
  // Task delegation
  // Plan approval workflow
}
```

#### D. Tool Registry
```typescript
// 91 tools organized by category:
// - File operations (edit, read, write)
// - Shell execution
// - Web (search, fetch)
// - Agent management (fork, team)
// - Task management (create, update, list)
// - Skill system
// - Cron scheduling
// - Computer use (Playwright)
// - MCP integration
```

### What We Take From Qwen Code
1. **Agent core** execution engine
2. **Workflow orchestrator** for multi-agent tasks
3. **Team system** for agent collaboration
4. **Tool registry** with 91+ tools
5. **Budget management** for token/cost control
6. **Stall detection** and recovery
7. **Git worktree** isolation for parallel work

---

## 7. PLANDEX (plandex-ai/plandex)

### Architecture
```
plandex/
├── app/
│   ├── cli/           # Go CLI
│   │   ├── cmd/       # Commands (40+ commands)
│   │   ├── api/       # API client
│   │   └── auth/      # Authentication
│   └── server/        # Go server
│       ├── db/        # Database layer (SQLite)
│       ├── handlers/  # HTTP handlers
│       ├── llm/       # LLM providers
│       ├── streaming/ # Response streaming
│       └── diff/      # Diff generation
├── docs/              # Documentation
└── plans/             # Example plans
```

### Key Patterns Extracted

#### A. Plan-Based Development
```
# Plandex uses a "plan" concept:
# - Each task is a "plan"
# - Plans have branches
# - Plans have context (files, code)
# - Plans execute in steps
# - Plans can be loaded/saved
```

#### B. Server Architecture
- REST API server
- SQLite database
- Streaming responses
- Context management (file loading, mapping)

#### C. Model Providers
- Multiple LLM provider support
- Model routing
- Token counting

### What We Take From Plandex
1. **Plan-based** task management
2. **Server architecture** for remote execution
3. **Context management** patterns

---

## 8. KILOCODE (Kilo-Org/kilocode)

### Architecture
```
kilocode/
├── packages/
│   ├── core/          # Core library (Effect system)
│   │   ├── src/
│   │   │   ├── agent.ts       # Agent state management
│   │   │   ├── aisdk.ts       # AI SDK integration
│   │   │   ├── command.ts     # Command system
│   │   │   ├── config.ts      # Configuration
│   │   │   ├── credential.ts  # Credential management
│   │   │   ├── file.ts        # File operations
│   │   │   ├── filesystem.ts  # Filesystem abstraction
│   │   │   ├── git.ts         # Git operations
│   │   │   ├── image.ts       # Image handling
│   │   │   └── ...
│   │   └── ...
│   ├── codemode/      # Code modification tools
│   │   └── src/
│   │       ├── codemode.ts    # Main codemode
│   │       ├── tool.ts        # Tool system
│   │       ├── tool-runtime.ts # Tool execution
│   │       └── tool-schema.ts # Tool schemas
│   ├── client/        # Client library
│   ├── containers/    # Container management
│   └── ...
├── docs/              # Documentation
└── plans/             # Development plans
```

### Key Patterns Extracted

#### A. Effect System (TypeScript)
```typescript
// Uses the Effect library for:
// - Functional programming
// - Dependency injection
// - Error handling
// - State management
// - Service layer
```

#### B. Tool System (codemode)
```typescript
// Tool definitions with schemas
// Tool runtime for execution
// Tool error handling
// Tool result formatting
```

#### C. State Management
```typescript
// Agent state with immutable updates
// Service layer pattern
// Location-based node system
```

### What We Take From Kilocode
1. **Effect system** for functional architecture
2. **Tool schema** definitions
3. **State management** patterns

---

## COMMON PATTERNS ACROSS ALL REPOS

### 1. Agent Loop Pattern
Every repo implements some version of:
```
while not done:
    1. Build context (system prompt + history + tools)
    2. Call LLM
    3. Parse response (text + tool calls)
    4. Execute tools
    5. Add results to history
    6. Check termination conditions
```

### 2. Tool System
All repos use OpenAI-compatible function calling:
```json
{
  "type": "function",
  "function": {
    "name": "tool_name",
    "description": "...",
    "parameters": { "type": "object", ... }
  }
}
```

### 3. Multi-Agent Spawning
Most repos support spawning sub-agents:
- Freebuff: `spawn_agents` tool
- Qwen Code: `workflow-orchestrator`
- OpenHands: Agent Canvas

### 4. Context Management
- Token counting and budgeting
- Context pruning/summarization
- File relevance ranking

### 5. Git Integration
- Auto-commit with messages
- Diff tracking
- Branch management

### 6. MCP Support
- Client for connecting to MCP servers
- Server for exposing tools
- Tool discovery and registration

---

## WHAT DEV NEEDS (COMPARISON)

| Feature | Freebuff | Aider | OpenHands | Codex | Continue | Qwen | Plandex | Kilo | **Dev** |
|---------|----------|-------|-----------|-------|----------|------|---------|------|---------|
| CLI Agent | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ |
| Multi-Agent | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| MCP | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| 24/7 Mode | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ |
| Sandboxing | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Browser | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Git | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Free Models | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (NIMs) |
| Open Source | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## EXTRACTED CODE TO REUSE

### From Freebuff
- `agents/types/agent-definition.ts` → Agent definition types
- `agents/types/tools.ts` → Tool type definitions
- `sdk/src/run.ts` → Agent execution loop
- `sdk/src/tools/` → Tool implementations (read, write, search, etc.)
- `sdk/src/impl/llm.ts` → LLM integration pattern

### From Aider
- `aider/llm.py` → Lazy LLM loading
- `aider/coders/base_coder.py` → Coder strategy pattern
- `aider/repomap.py` → Repo map concept
- `aider/repo.py` → Git integration

### From Qwen Code
- `agents/runtime/agent-core.ts` → Core execution engine
- `agents/runtime/workflow-orchestrator.ts` → Multi-agent orchestration
- `tools/tool-registry.ts` → Tool registry pattern
- `tools/` → Tool implementations (91 tools!)

### From Codex
- `codex-rs/sandboxing/` → Sandboxing concept
- `codex-rs/mcp-server/` → MCP server pattern

### From Plandex
- `app/server/` → Server architecture
- Plan-based task management concept
