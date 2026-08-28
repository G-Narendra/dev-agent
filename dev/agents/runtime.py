"""
Core agent runtime for Dev.

Adapted from Freebuff's run.ts agent loop and Aider's base_coder.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import traceback
from typing import Any, Optional

from ..providers.nim_provider import NimProvider


class ToolRegistry:
    """Registry of available tools with auto-generated LLM schemas."""

    def __init__(self):
        self._tools: dict[str, Any] = {}

    def register(self, name: str, handler: Any):
        """Register a tool handler. Auto-attaches definition if missing."""
        self._tools[name] = handler
        # Auto-attach definition from tool_defs if handler doesn't have one
        if not hasattr(handler, "definition") or handler.definition is None:
            from ..tools.tool_defs import get_tool_definition, patch_tool
            patch_tool(handler, name)
            # If still no definition, auto-generate from handler.parameters
            if not hasattr(handler, "definition") or handler.definition is None:
                if hasattr(handler, "parameters") and handler.parameters:
                    handler.definition = {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": getattr(handler, "description", f"Execute {name}"),
                            "parameters": handler.parameters,
                        },
                    }

    def __contains__(self, name: str) -> bool:
        """Support `in` operator: `if tool_name in registry`."""
        return name in self._tools

    def __getitem__(self, name: str) -> Any:
        """Support `registry[name]` access."""
        return self._tools[name]

    def __len__(self) -> int:
        return len(self._tools)

    def keys(self):
        return self._tools.keys()

    def get(self, name: str) -> Any | None:
        """Get a tool handler by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_definitions(self) -> list[dict]:
        """Get OpenAI-compatible tool definitions for ALL registered tools.

        Priority:
        1. Handler's own .definition attribute
        2. Static definitions from tool_defs module
        3. Auto-generated from handler.parameters (last resort)
        """
        from ..tools.tool_defs import get_tool_definition
        defs = []
        seen = set()

        for name, handler in self._tools.items():
            if name in seen:
                continue
            seen.add(name)

            # 1. Handler's own definition
            if hasattr(handler, "definition") and handler.definition:
                defs.append(handler.definition)
                continue

            # 2. Static definition from tool_defs
            defn = get_tool_definition(name)
            if defn:
                defs.append(defn)
                continue

            # 3. Auto-generate from handler.parameters
            if hasattr(handler, "parameters") and handler.parameters:
                auto_def = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": getattr(handler, "description", f"Execute {name}"),
                        "parameters": handler.parameters,
                    },
                }
                defs.append(auto_def)

        return defs

    def get_definitions_for_tools(self, tool_names: list[str]) -> list[dict]:
        """Get OpenAI-compatible tool definitions for SPECIFIC tools only.
        
        This limits the number of tools sent to the model, which is critical
        for models like Llama 3.1 70B that can only handle ~15-20 tools.
        """
        all_defs = self.get_definitions()
        if not tool_names:
            return all_defs
        
        # Priority order: core tools first, then extras
        CORE_TOOLS = [
            'read_files', 'write_file', 'str_replace', 'run_terminal_command',
            'code_search', 'glob', 'list_directory', 'git_operations',
            'web_search', 'read_url', 'write_todos', 'task_completed',
            'summarize', 'free_api', 'skill',
        ]
        
        # Build filtered list: core tools that are in tool_names, then extras
        seen = set()
        filtered = []
        for d in all_defs:
            name = d.get('function', {}).get('name', '')
            if name in tool_names and name not in seen:
                seen.add(name)
                filtered.append(d)
        
        # If still too many (>20), only keep core tools
        if len(filtered) > 20:
            filtered = [d for d in filtered 
                       if d.get('function', {}).get('name', '') in CORE_TOOLS]
        
        return filtered


class AgentRuntime:
    """
    Core runtime that executes agents.

    Adapted from Freebuff's run.ts agent loop:
    1. Load agent definition
    2. Build system prompt with tools
    3. Execute step loop:
       a. If handleSteps exists, follow generator
       b. Otherwise, let model decide tool calls
       c. Execute tool calls
       d. Repeat until done
    """

    def __init__(
        self,
        provider: NimProvider,
        tool_registry: ToolRegistry,
        max_steps: int = 100,
    ):
        self.provider = provider
        self.tools = tool_registry
        self.max_steps = max_steps
        self._running: dict[str, bool] = {}

    async def run_agent(
        self,
        agent_id: str,
        prompt: str,
        project_path: str = ".",
        system_prompt: str = "",
        params: dict | None = None,
        parent_state: Any = None,
    ) -> dict:
        """Run an agent by ID."""
        from ..agents.agent_definition import get_agent

        try:
            agent_def = get_agent(agent_id)
        except ValueError:
            return {"error": f"Unknown agent: {agent_id}"}

        # Build the full system prompt
        full_system = system_prompt or agent_def.system_prompt
        if agent_def.instructions_prompt:
            full_system += f"\n\n{agent_def.instructions_prompt}"

        # Try handle_steps generator first
        if agent_def.handle_steps:
            return await self._run_with_handle_steps(
                agent_def, prompt, full_system, project_path
            )

        # Standard LLM loop
        return await self._run_standard_loop(
            agent_def, prompt, full_system, project_path
        )

    async def _run_with_handle_steps(
        self, agent_def, prompt, system_prompt, project_path
    ) -> dict:
        """Run with handleSteps generator (programmatic control)."""
        from ..agents.agent_definition import AgentStepContext, StepAction

        state = AgentState(agent_id=agent_def.id, run_id=f"run-{int(time.time())}")
        state.system_prompt = system_prompt
        context = AgentStepContext(agent_state=state, prompt=prompt)

        result: dict = {"status": "completed", "steps": 0, "tool_calls": []}

        try:
            for action in agent_def.handle_steps(context):
                if action == StepAction.STEP:
                    result["steps"] += 1
                    response = await self.provider.chat_completion(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        model=agent_def.model,
                    )
                    choice = response.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    state.message_history.append(message)

                    tool_calls = message.get("tool_calls", [])
                    if tool_calls:
                        tc_results = await self._execute_tool_calls(
                            tool_calls, state, project_path
                        )
                        result["tool_calls"].extend(tc_results)

                elif action == StepAction.RETURN:
                    break

            result["content"] = state.message_history[-1].get("content", "") if state.message_history else ""

        except Exception as e:
            result = {"status": "error", "message": str(e)}

        return result

    async def _run_standard_loop(
        self, agent_def, prompt, system_prompt, project_path
    ) -> dict:
        """Standard agent loop — call LLM, execute tools, repeat."""
        from ..agents.production_loop import Message

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=prompt),
        ]

        all_tool_calls = []
        result = {
            "status": "completed",
            "steps": 0,
            "tool_calls": [],
            "content": "",
        }

        for step in range(self.max_steps):
            result["steps"] = step + 1

            # Build message dicts
            msg_dicts = []
            for m in messages:
                md = {"role": m.role, "content": m.content}
                if m.tool_call_id:
                    md["tool_call_id"] = m.tool_call_id
                if m.name:
                    md["name"] = m.name
                msg_dicts.append(md)

            # Get tool definitions
            tool_defs = self.tools.get_definitions()

            # Call LLM
            try:
                response = await self.provider.chat_completion(
                    messages=msg_dicts,
                    model=agent_def.model,
                    tools=tool_defs if tool_defs else None,
                )
            except Exception as e:
                result["status"] = "error"
                result["message"] = str(e)
                return result

            # Parse response
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

            # Add assistant message
            messages.append(
                Message(
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls,
                )
            )

            # No tool calls = done
            if not tool_calls:
                result["content"] = content
                break

            # Execute tool calls
            tc_results = await self._execute_tool_calls(
                tool_calls, None, project_path
            )
            result["tool_calls"].extend(tc_results)

            # Add tool results to messages
            for tc, tc_result in zip(tool_calls, tc_results):
                messages.append(
                    Message(
                        role="tool",
                        tool_call_id=tc.get("id", ""),
                        name=tc.get("function", {}).get("name", ""),
                        content=json.dumps(tc_result),
                    )
                )

        return result

    async def _execute_tool_calls(
        self, tool_calls: list[dict], state: Any, project_path: str
    ) -> list[dict]:
        """Execute a batch of tool calls."""
        results = []
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                tool_args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}

            result = await self._execute_single_tool(tool_name, tool_args, project_path)
            results.append(result)

        return results

    async def _execute_single_tool(
        self, tool_name: str, tool_args: dict, project_path: str
    ) -> Any:
        """Execute a single tool call."""
        handler = self.tools.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            if asyncio.iscoroutinefunction(handler.execute):
                result = await handler.execute(tool_args, None, project_path)
            else:
                result = handler.execute(tool_args, None, project_path)
            return result
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}", "traceback": traceback.format_exc()}


# Import AgentState here to avoid circular imports at module level
from ..agents.agent_definition import AgentState
