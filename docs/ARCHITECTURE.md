# Dev Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI / Web UI                         │
├─────────────────────────────────────────────────────────────┤
│                     Agent Runtime                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Coder   │  │Researcher│  │ Reviewer │  │ Planner  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
├─────────────────────────────────────────────────────────────┤
│                      Tool System                             │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │
│  │  File  │ │ Shell  │ │  Git   │ │  Web   │ │  MCP   │   │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   Infrastructure                             │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │
│  │Sandbox │ │Context │ │Budget  │ │Session │ │Security│   │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    LLM Provider                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │        NVIDIA NIMs (free tier, cloud-based)        │     │
│  │        3-key rotation, 120 RPM combined             │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Agent Runtime (`agents/`)

The agent runtime is the heart of Dev. It orchestrates:
- LLM calls with retries and streaming
- Tool execution and result handling
- Context management and pruning
- Error recovery and reflection

**Key files:**
- `runtime.py` - Basic runtime with tool dispatch
- `production_loop.py` - Production runtime from Aider (2485 lines)
- `agent_definition.py` - Agent type definitions
- `workflow.py` - Parallel/pipeline orchestration
- `team.py` - Leader/follower collaboration

**Execution flow:**
```
1. Build system prompt with repo map
2. Format messages (system + history + current)
3. Call LLM via NVIDIA NIMs API
4. Parse response (text + tool calls)
5. Execute tools
6. Check for completion or errors
7. Repeat until done or max steps
```

### 2. Tool System (`tools/`)

Tools are the agent's interface to the outside world.

**Tool categories:**
- **File tools**: read, write, edit, search, glob
- **System tools**: shell, git, processes
- **Web tools**: search, URL reading, screenshots
- **Context tools**: repo map, pruning, summarization
- **Patch tools**: apply patch, edit block
- **Sandbox tools**: policy-checked execution
- **API tools**: free APIs, MCP servers
- **Agent tools**: spawn agents, todos, task management

### 3. Provider System (`providers/`)

Single provider using NVIDIA NIMs free tier.

**Features:**
- Multi-key rotation (up to 3 keys)
- Token bucket rate limiting per key
- Automatic model selection (coding/reasoning/fast)
- Streaming support
- Usage tracking
- OpenAI-compatible API format

**Models available:**
- `nvidia/llama-3.1-nemotron-70b-instruct` - Coding, reasoning
- `nvidia/llama-3.1-8b-instruct` - Fast responses
- `deepseek-ai/deepseek-r1` - Deep reasoning
- `qwen/qwen2.5-coder-32b-instruct` - Code generation

### 4. Sandbox System (`sandbox/`)

Controls what the agent can do.

**Components:**
- `exec_policy.py` - Allow/Prompt/Forbidden rules
- `sandbox_manager.py` - Command execution sandbox

**Security levels:**
- **Default**: Safe commands allowed, project commands prompt
- **Strict**: Everything requires approval
- **Permissive**: Most commands allowed
- **Read-only**: No file modifications

### 5. Context Management (`utils/`)

Manages the agent's context window.

**Components:**
- `repo_map.py` - Codebase mapping (from Aider)
- `context_pruner.py` - Conversation compression
- `budget.py` - Token/cost tracking
- `session.py` - Session persistence

### 6. Free APIs & MCP (`apis/`, `mcp/`)

Free APIs and MCP servers for extended capabilities.

**Free APIs (27+):**
- Development: JSONPlaceholder, HTTPBin, GitHub, npm, Kroki
- ML: DeepCode, OpenVisionAPI
- Utilities: ipify, WorldTimeAPI, Random Data

**MCP Servers (8+):**
- Filesystem, Git, Fetch, Memory
- SQLite, Sequential Thinking, Puppeteer, Playwright

## Configuration

Config file: `~/.dev/config.json`

```json
{
  "api_keys": ["nvidia-xxx"],
  "rpm": 40,
  "sandbox_mode": "default"
}
```

## Extending Dev

### Adding a Tool

```python
from dev.tools.base import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string"}
        },
        "required": ["input"]
    }
    
    async def execute(self, input_data, state, project_path):
        return {"result": "done"}

# Register in CLI
registry.register("my_tool", MyTool())
```

### Adding an Agent

```python
from dev.agents.agent_definition import AgentDefinition

my_agent = AgentDefinition(
    id="my-agent",
    display_name="My Agent",
    model="default",
    tool_names=["read_files", "write_file"],
    system_prompt="You are a specialized agent...",
)

BUILTIN_AGENTS["my-agent"] = lambda: my_agent
```

### Adding a Skill

Create `.dev/skills/my-skill.md`:

```markdown
# My Skill

Instructions for the agent...

## Best Practices
- Do this
- Don't do that
```

### Creating a Plugin

```python
# my-plugin/dev_plugin.py
from dev.plugins.manager import PluginInfo

PLUGIN_INFO = PluginInfo(
    name="my-plugin",
    version="0.1.0",
    description="My awesome plugin",
)

def register_tools(registry):
    registry.register("my_tool", MyTool())
```
