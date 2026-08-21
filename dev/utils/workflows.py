"""
Dynamic Workflow System for Dev.

Define multi-agent pipelines as YAML or JSON:
- Chain agents in sequence
- Branch based on results
- Parallel execution
- Conditional steps
- Error handling

Like Claude Code's dynamic workflows for orchestrating subagents.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from pathlib import Path


class StepType(str, Enum):
    AGENT = "agent"          # Run an agent with a prompt
    TOOL = "tool"            # Run a specific tool
    PARALLEL = "parallel"    # Run multiple steps in parallel
    CONDITION = "condition"  # Branch based on result
    SHELL = "shell"          # Run a shell command


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    id: str
    type: StepType
    prompt: str = ""
    agent_id: str = "coder"
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    command: str = ""
    condition: str = ""  # Python expression to evaluate
    on_success: str = ""  # Step ID to go to on success
    on_failure: str = ""  # Step ID to go to on failure
    parallel_steps: list[str] = field(default_factory=list)
    timeout: int = 300
    retry: int = 0
    status: StepStatus = StepStatus.PENDING
    result: dict = field(default_factory=dict)


@dataclass
class Workflow:
    """A complete workflow definition."""
    name: str
    description: str = ""
    steps: dict[str, WorkflowStep] = field(default_factory=dict)
    first_step: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "first_step": self.first_step,
            "steps": {
                sid: {
                    "type": s.type.value,
                    "prompt": s.prompt,
                    "agent_id": s.agent_id,
                    "tool_name": s.tool_name,
                    "tool_args": s.tool_args,
                    "command": s.command,
                    "condition": s.condition,
                    "on_success": s.on_success,
                    "on_failure": s.on_failure,
                    "timeout": s.timeout,
                }
                for sid, s in self.steps.items()
            },
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Workflow:
        steps = {}
        for sid, sdata in data.get("steps", {}).items():
            steps[sid] = WorkflowStep(
                id=sid,
                type=StepType(sdata.get("type", "agent")),
                prompt=sdata.get("prompt", ""),
                agent_id=sdata.get("agent_id", "coder"),
                tool_name=sdata.get("tool_name", ""),
                tool_args=sdata.get("tool_args", {}),
                command=sdata.get("command", ""),
                condition=sdata.get("condition", ""),
                on_success=sdata.get("on_success", ""),
                on_failure=sdata.get("on_failure", ""),
                timeout=sdata.get("timeout", 300),
            )
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            steps=steps,
            first_step=data.get("first_step", ""),
            metadata=data.get("metadata", {}),
        )


class WorkflowEngine:
    """Executes workflows."""

    def __init__(self, runtime=None, provider=None):
        self.runtime = runtime
        self.provider = provider
        self._context: dict[str, Any] = {}

    async def execute(self, workflow: Workflow) -> dict:
        """Execute a complete workflow."""
        results = {}
        current_step_id = workflow.first_step
        max_iterations = 50  # Prevent infinite loops

        for _ in range(max_iterations):
            if not current_step_id or current_step_id not in workflow.steps:
                break

            step = workflow.steps[current_step_id]
            step.status = StepStatus.RUNNING

            try:
                result = await self._execute_step(step, workflow)
                step.result = result
                step.status = StepStatus.COMPLETED
                results[current_step_id] = result

                # Determine next step
                if result.get("success", True) and step.on_success:
                    current_step_id = step.on_success
                elif not result.get("success", True) and step.on_failure:
                    current_step_id = step.on_failure
                else:
                    # Find next step in order
                    step_ids = list(workflow.steps.keys())
                    idx = step_ids.index(current_step_id) if current_step_id in step_ids else -1
                    if idx + 1 < len(step_ids):
                        current_step_id = step_ids[idx + 1]
                    else:
                        break

            except Exception as e:
                step.status = StepStatus.FAILED
                step.result = {"error": str(e)}
                results[current_step_id] = {"error": str(e)}

                if step.on_failure:
                    current_step_id = step.on_failure
                else:
                    break

        return {
            "workflow": workflow.name,
            "results": results,
            "completed": all(
                s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
                for s in workflow.steps.values()
            ),
        }

    async def _execute_step(self, step: WorkflowStep, workflow: Workflow) -> dict:
        """Execute a single workflow step."""
        if step.type == StepType.AGENT:
            return await self._execute_agent_step(step)
        elif step.type == StepType.TOOL:
            return await self._execute_tool_step(step)
        elif step.type == StepType.SHELL:
            return await self._execute_shell_step(step)
        elif step.type == StepType.PARALLEL:
            return await self._execute_parallel_step(step, workflow)
        elif step.type == StepType.CONDITION:
            return self._evaluate_condition(step)
        return {"error": f"Unknown step type: {step.type}"}

    async def _execute_agent_step(self, step: WorkflowStep) -> dict:
        """Run an agent with a prompt."""
        if self.runtime:
            result = await self.runtime.run_agent(
                agent_id=step.agent_id,
                prompt=step.prompt,
            )
            return {"success": result.get("status") == "completed", "output": result.get("content", "")}
        return {"error": "No runtime available", "success": False}

    async def _execute_tool_step(self, step: WorkflowStep) -> dict:
        """Run a specific tool."""
        if self.runtime:
            handler = self.runtime.tools.get(step.tool_name)
            if handler:
                result = await handler.execute(step.tool_args, None, ".")
                return {"success": True, "output": result}
        return {"error": f"Tool not found: {step.tool_name}", "success": False}

    async def _execute_shell_step(self, step: WorkflowStep) -> dict:
        """Run a shell command."""
        try:
            proc = await asyncio.create_subprocess_shell(
                step.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=step.timeout)
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:5000],
                "stderr": stderr.decode(errors="replace")[:2000],
            }
        except asyncio.TimeoutError:
            return {"error": f"Timed out after {step.timeout}s", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}

    async def _execute_parallel_step(self, step: WorkflowStep, workflow: Workflow) -> dict:
        """Run multiple steps in parallel."""
        tasks = []
        for sub_step_id in step.parallel_steps:
            if sub_step_id in workflow.steps:
                tasks.append(self._execute_step(workflow.steps[sub_step_id], workflow))

        if not tasks:
            return {"error": "No parallel steps found", "success": False}

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "success": all(
                r.get("success", False) if isinstance(r, dict) else False
                for r in results
            ),
            "results": results,
        }

    def _evaluate_condition(self, step: WorkflowStep) -> dict:
        """Evaluate a condition expression safely using AST whitelist."""
        import ast as _ast
        try:
            # Parse and validate the expression
            tree = _ast.parse(step.condition, mode='eval')
            # Whitelist allowed node types
            ALLOWED_NODES = (
                _ast.Expression, _ast.Compare, _ast.BoolOp, _ast.BinOp,
                _ast.UnaryOp, _ast.Name, _ast.Constant, _ast.Attribute,
                _ast.Load, _ast.And, _ast.Or, _ast.Not,
                _ast.Eq, _ast.NotEq, _ast.Lt, _ast.LtE, _ast.Gt, _ast.GtE,
                _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.Mod,
                _ast.In, _ast.NotIn, _ast.Is, _ast.IsNot,
            )
            for node in _ast.walk(tree):
                if not isinstance(node, ALLOWED_NODES):
                    return {"success": False, "error": f"Disallowed expression node: {type(node).__name__}"}
            # Safe to evaluate
            result = eval(compile(tree, '<condition>', 'eval'), {"__builtins__": {}}, self._context)
            return {"success": bool(result), "condition": step.condition, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_context(self, key: str, value: Any):
        """Set a context variable for conditions."""
        self._context[key] = value


class WorkflowManager:
    """Manages workflow definitions."""

    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.workflows_dir = os.path.join(self.project_root, ".dev", "workflows")
        os.makedirs(self.workflows_dir, exist_ok=True)

    def save_workflow(self, workflow: Workflow) -> str:
        """Save a workflow to disk."""
        fpath = os.path.join(self.workflows_dir, f"{workflow.name}.json")
        with open(fpath, "w") as f:
            json.dump(workflow.to_dict(), f, indent=2)
        return fpath

    def load_workflow(self, name: str) -> Workflow | None:
        """Load a workflow from disk."""
        fpath = os.path.join(self.workflows_dir, f"{name}.json")
        if not os.path.exists(fpath):
            return None
        with open(fpath) as f:
            data = json.load(f)
        return Workflow.from_dict(data)

    def list_workflows(self) -> list[dict]:
        """List all saved workflows."""
        workflows = []
        for fname in os.listdir(self.workflows_dir):
            if fname.endswith(".json"):
                name = fname[:-5]
                fpath = os.path.join(self.workflows_dir, fname)
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    workflows.append({
                        "name": name,
                        "description": data.get("description", ""),
                        "steps": len(data.get("steps", {})),
                    })
                except Exception:
                    pass
        return workflows

    def delete_workflow(self, name: str) -> bool:
        """Delete a workflow."""
        fpath = os.path.join(self.workflows_dir, f"{name}.json")
        if os.path.exists(fpath):
            os.remove(fpath)
            return True
        return False


# Built-in workflow templates
BUILTIN_WORKFLOWS = {
    "code-review": {
        "name": "code-review",
        "description": "Review code changes with research, analysis, and suggestions",
        "steps": {
            "1_research": {
                "type": "agent",
                "agent_id": "researcher",
                "prompt": "Research best practices for the code in this project. Look at the project structure, dependencies, and patterns.",
            },
            "2_review": {
                "type": "agent",
                "agent_id": "reviewer",
                "prompt": "Review the codebase for bugs, security issues, performance problems, and code style violations. Be thorough.",
            },
            "3_suggest": {
                "type": "agent",
                "agent_id": "coder",
                "prompt": "Based on the review findings, create a prioritized list of improvements with specific file/line references.",
            },
        },
        "first_step": "1_research",
    },
    "fix-and-test": {
        "name": "fix-and-test",
        "description": "Fix issues and verify with tests",
        "steps": {
            "1_detect": {
                "type": "tool",
                "tool_name": "run_terminal_command",
                "tool_args": {"command": "python -m pytest --tb=short 2>&1 | head -50"},
            },
            "2_fix": {
                "type": "agent",
                "agent_id": "coder",
                "prompt": "Fix the failing tests. Read the test output, find the root cause, and implement fixes.",
            },
            "3_verify": {
                "type": "tool",
                "tool_name": "run_terminal_command",
                "tool_args": {"command": "python -m pytest --tb=short"},
            },
        },
        "first_step": "1_detect",
    },
    "deploy-check": {
        "name": "deploy-check",
        "description": "Pre-deployment verification checklist",
        "steps": {
            "1_lint": {
                "type": "tool",
                "tool_name": "run_terminal_command",
                "tool_args": {"command": "echo 'Running linter...' && python -m flake8 src/ 2>&1 | head -20 || echo 'No linter configured'"},
            },
            "2_test": {
                "type": "tool",
                "tool_name": "run_terminal_command",
                "tool_args": {"command": "echo 'Running tests...' && python -m pytest --tb=short 2>&1 | head -30 || echo 'No tests configured'"},
            },
            "3_security": {
                "type": "agent",
                "agent_id": "reviewer",
                "prompt": "Review the codebase for security vulnerabilities before deployment. Check for hardcoded secrets, injection risks, and auth issues.",
            },
            "4_report": {
                "type": "agent",
                "agent_id": "coder",
                "prompt": "Generate a deployment readiness report summarizing all checks. List any blockers.",
            },
        },
        "first_step": "1_lint",
    },
}
