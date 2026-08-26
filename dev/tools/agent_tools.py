"""
Agent management tools for Dev.

Adapted from Freebuff's spawn_agents, write_todos, task_completed tools.
"""

from __future__ import annotations

import json
from typing import Any

from .base import Tool


class WriteTodosTool(Tool):
    """
    Write a todo list to track tasks.
    
    Directly adapted from Freebuff's write_todos tool.
    """
    
    name = "write_todos"
    description = "Write a todo list to track tasks for multi-step implementations"
    parameters = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "completed": {"type": "boolean"},
                    },
                    "required": ["task", "completed"],
                },
                "description": "List of tasks with completion status",
            },
        },
        "required": ["todos"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        import json as _json
        todos = input_data.get("todos", [])
        # LLM may send todos as a JSON string instead of a list
        if isinstance(todos, str):
            try:
                todos = _json.loads(todos)
            except (_json.JSONDecodeError, TypeError):
                todos = []
        if not isinstance(todos, list):
            todos = []
        
        # Store in agent state
        if state and hasattr(state, "output"):
            if not state.output:
                state.output = {}
            state.output["todos"] = todos
        
        # Format for display
        lines = []
        completed_count = 0
        for i, todo in enumerate(todos, 1):
            # LLM may send items as plain strings or malformed dicts — normalize
            if isinstance(todo, str):
                todo = {"task": todo, "completed": False}
            elif not isinstance(todo, dict):
                continue
            task = str(todo.get("task", ""))
            completed = bool(todo.get("completed", False))
            if completed:
                completed_count += 1
            status = "✅" if completed else "⬜"
            lines.append(f"{status} {i}. {task}")
        
        return {
            "todos": todos,
            "display": "\n".join(lines),
            "completed_count": completed_count,
            "total_count": len(todos),
        }


class TaskCompletedTool(Tool):
    """
    Signal that the current task is complete.
    
    Adapted from Freebuff's task_completed tool.
    """
    
    name = "task_completed"
    description = "Signal that the current task is complete"
    parameters = {
        "type": "object",
        "properties": {},
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        return {"status": "completed"}


class SpawnAgentsTool(Tool):
    """
    Spawn sub-agents for parallel work.
    
    Adapted from Freebuff's spawn_agents tool.
    """
    
    name = "spawn_agents"
    description = "Spawn multiple agents to work in parallel on subtasks"
    parameters = {
        "type": "object",
        "properties": {
            "agents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_type": {"type": "string"},
                        "prompt": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["agent_type", "prompt"],
                },
            },
        },
        "required": ["agents"],
    }
    
    def __init__(self, runtime: Any = None):
        self.runtime = runtime
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        agents = input_data.get("agents", [])
        # Also accept single agent spawn (not wrapped in array)
        if not agents and input_data.get("agent_type") and input_data.get("prompt"):
            agents = [input_data]
        
        if not self.runtime:
            return {"error": "Runtime not initialized for agent spawning. Make sure spawn_agents has a runtime reference."}
        
        results = []

        async def _run_agent(agent_spec):
            agent_type = agent_spec.get("agent_type", agent_spec.get("agent_id", "coder"))
            prompt_text = agent_spec.get("prompt", "")
            try:
                result = await self.runtime.run_agent(
                    agent_id=agent_type,
                    prompt=prompt_text,
                    project_path=project_path,
                    params=agent_spec.get("params"),
                    parent_state=state,
                )
                return {
                    "agent_type": agent_type,
                    "output": result.get("content", result.get("output", "")),
                    "status": result.get("status", "completed"),
                    "steps": result.get("steps", 0),
                }
            except Exception as e:
                return {
                    "agent_type": agent_type,
                    "output": f"Error: {e}",
                    "status": "failed",
                }

        # Run agents in parallel
        import asyncio as _asyncio
        results = await _asyncio.gather(*[_run_agent(a) for a in agents])
        results = list(results)

        return {"results": results}
