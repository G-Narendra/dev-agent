"""
Workflow Orchestrator for Dev.

Adapted from Qwen Code's workflow-orchestrator.ts:
- Parallel agent execution
- Pipeline chains
- Budget management
- Stall detection
- Git worktree isolation
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class WorkflowStepType(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALLED = "stalled"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    id: str
    agent_id: str
    prompt: str
    params: dict = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: dict | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    depends_on: list[str] = field(default_factory=list)  # Step IDs this depends on


@dataclass
class WorkflowBudget:
    """Budget limits for a workflow."""
    max_tokens: int = 100_000
    max_cost: float = 0.0  # 0 = unlimited (free tier)
    max_steps: int = 100
    max_time_seconds: int = 3600  # 1 hour
    tokens_used: int = 0
    steps_executed: int = 0
    started_at: float | None = None


@dataclass
class Workflow:
    """A workflow containing multiple steps."""
    id: str
    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    budget: WorkflowBudget = field(default_factory=WorkflowBudget)
    status: StepStatus = StepStatus.PENDING
    result: dict | None = None
    created_at: float = field(default_factory=time.time)


class WorkflowOrchestrator:
    """
    Orchestrates multi-agent workflows.
    
    From Qwen Code's workflow-orchestrator.ts:
    - Dispatch agents sequentially, parallel, or pipeline
    - Track budget and stall conditions
    - Isolate work in git worktrees
    """
    
    MAX_AGENTS_PER_RUN = 1000
    
    def __init__(self, runtime: Any):
        self.runtime = runtime
        self._active_workflows: dict[str, Workflow] = {}
        self._worktrees: dict[str, str] = {}  # workflow_id -> worktree_path
    
    async def execute_workflow(self, workflow: Workflow) -> dict:
        """
        Execute a complete workflow.
        
        Steps can run:
        - Sequential: one after another
        - Parallel: all at once
        - Pipeline: output of one feeds into next
        """
        workflow.budget.started_at = time.time()
        workflow.status = StepStatus.RUNNING
        self._active_workflows[workflow.id] = workflow
        
        try:
            # Create git worktree for isolation
            worktree_path = self._create_worktree(workflow.id)
            self._worktrees[workflow.id] = worktree_path
            
            # Build dependency graph
            ready = [s for s in workflow.steps if not s.depends_on]
            completed = set()
            
            while ready:
                # Check budget
                if not self._check_budget(workflow.budget):
                    workflow.status = StepStatus.FAILED
                    workflow.result = {"error": "Budget exceeded"}
                    break
                
                # Check for stall
                if self._detect_stall(workflow):
                    workflow.status = StepStatus.STALLED
                    workflow.result = {"error": "Workflow stalled"}
                    break
                
                # Execute ready steps
                batch = self._get_parallel_batch(ready, completed, workflow.steps)
                
                if len(batch) > 1:
                    # Parallel execution
                    results = await asyncio.gather(
                        *[self._execute_step(step, worktree_path, workflow.budget) for step in batch],
                        return_exceptions=True,
                    )
                    for step, result in zip(batch, results):
                        if isinstance(result, Exception):
                            step.status = StepStatus.FAILED
                            step.error = str(result)
                        else:
                            step.result = result
                            step.status = StepStatus.COMPLETED
                        step.completed_at = time.time()
                        completed.add(step.id)
                else:
                    # Sequential execution
                    step = batch[0]
                    try:
                        result = await self._execute_step(step, worktree_path, workflow.budget)
                        step.result = result
                        step.status = StepStatus.COMPLETED
                    except Exception as e:
                        step.status = StepStatus.FAILED
                        step.error = str(e)
                    step.completed_at = time.time()
                    completed.add(step.id)
                
                # Find newly ready steps
                ready = [
                    s for s in workflow.steps
                    if s.id not in completed
                    and s.status == StepStatus.PENDING
                    and all(dep in completed for dep in s.depends_on)
                ]
            
            # Check if all steps completed
            all_done = all(
                s.status in (StepStatus.COMPLETED, StepStatus.FAILED)
                for s in workflow.steps
            )
            
            if all_done:
                failed = [s for s in workflow.steps if s.status == StepStatus.FAILED]
                workflow.status = StepStatus.COMPLETED if not failed else StepStatus.FAILED
                workflow.result = {
                    "steps_completed": len([s for s in workflow.steps if s.status == StepStatus.COMPLETED]),
                    "steps_failed": len(failed),
                    "total_steps": len(workflow.steps),
                }
            
            return workflow.result or {}
            
        finally:
            # Cleanup worktree
            self._cleanup_worktree(workflow.id)
            self._active_workflows.pop(workflow.id, None)
    
    async def _execute_step(
        self,
        step: WorkflowStep,
        worktree_path: str,
        budget: WorkflowBudget,
    ) -> dict:
        """Execute a single workflow step."""
        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        
        # Build context from previous step results
        context = self._build_step_context(step)
        
        # Execute agent
        result = await self.runtime.run_agent(
            agent_id=step.agent_id,
            prompt=step.prompt,
            params={**step.params, "context": context},
            project_path=worktree_path,
        )
        
        # Update budget
        usage = result.get("usage", {})
        budget.tokens_used += usage.get("total_tokens", 0)
        budget.steps_executed += 1
        
        return result
    
    def _build_step_context(self, step: WorkflowStep) -> str:
        """Build context from previous steps."""
        parts = []
        for dep_id in step.depends_on:
            # Find the dependency step
            # In a real implementation, we'd look up the step
            parts.append(f"[Previous step {dep_id} output]")
        return "\n".join(parts)
    
    def _get_parallel_batch(
        self,
        ready: list[WorkflowStep],
        completed: set[str],
        all_steps: list[WorkflowStep],
    ) -> list[WorkflowStep]:
        """
        Get steps that can run in parallel.
        
        From Qwen Code: steps with no inter-dependencies can run in parallel.
        """
        # Simple heuristic: if multiple steps are ready and don't depend on each other
        if len(ready) <= 1:
            return ready[:1]
        
        # Check if steps depend on each other
        independent = []
        for step in ready:
            # This step doesn't depend on any other ready step
            deps_in_ready = [d for d in step.depends_on if d in [s.id for s in ready]]
            if not deps_in_ready:
                independent.append(step)
        
        return independent if independent else ready[:1]
    
    def _check_budget(self, budget: WorkflowBudget) -> bool:
        """Check if budget is exceeded."""
        if budget.max_tokens > 0 and budget.tokens_used >= budget.max_tokens:
            return False
        if budget.max_steps > 0 and budget.steps_executed >= budget.max_steps:
            return False
        if budget.max_time_seconds > 0 and budget.started_at:
            elapsed = time.time() - budget.started_at
            if elapsed >= budget.max_time_seconds:
                return False
        return True
    
    def _detect_stall(self, workflow: Workflow) -> bool:
        """
        Detect if workflow is stalled.
        
        From Qwen Code: no progress for > 60 seconds.
        """
        running_steps = [s for s in workflow.steps if s.status == StepStatus.RUNNING]
        if not running_steps:
            return False
        
        for step in running_steps:
            if step.started_at:
                elapsed = time.time() - step.started_at
                if elapsed > 60:  # 60 second stall threshold
                    return True
        
        return False
    
    def _create_worktree(self, workflow_id: str) -> str:
        """
        Create a git worktree for workflow isolation.
        
        From Qwen Code's GitWorktreeService.
        """
        import subprocess
        
        worktree_dir = f"/tmp/dev-worktree-{workflow_id[:8]}"
        
        try:
            # Check if we're in a git repo
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                check=True,
            )
            
            # Create worktree
            branch = f"dev-workflow-{workflow_id[:8]}"
            subprocess.run(
                ["git", "worktree", "add", "-b", branch, worktree_dir],
                capture_output=True,
                timeout=10,
            )
            
            return worktree_dir
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Not in a git repo or git not available, use temp dir
            os.makedirs(worktree_dir, exist_ok=True)
            return worktree_dir
    
    def _cleanup_worktree(self, workflow_id: str):
        """Clean up git worktree."""
        import subprocess
        
        worktree_path = self._worktrees.pop(workflow_id, None)
        if not worktree_path:
            return
        
        try:
            subprocess.run(
                ["git", "worktree", "remove", worktree_path, "--force"],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            # Best effort cleanup
            try:
                import shutil
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception:
                pass
    
    def cancel_workflow(self, workflow_id: str):
        """Cancel a running workflow."""
        workflow = self._active_workflows.get(workflow_id)
        if workflow:
            workflow.status = StepStatus.CANCELLED
            for step in workflow.steps:
                if step.status == StepStatus.RUNNING:
                    step.status = StepStatus.CANCELLED
    
    def get_workflow_status(self, workflow_id: str) -> dict | None:
        """Get status of a workflow."""
        workflow = self._active_workflows.get(workflow_id)
        if not workflow:
            return None
        
        return {
            "id": workflow.id,
            "name": workflow.name,
            "status": workflow.status.value,
            "steps": [
                {
                    "id": s.id,
                    "agent": s.agent_id,
                    "status": s.status.value,
                    "error": s.error,
                }
                for s in workflow.steps
            ],
            "budget": {
                "tokens_used": workflow.budget.tokens_used,
                "steps_executed": workflow.budget.steps_executed,
            },
        }


# ============================================================================
# Workflow Builder - Easy workflow creation
# ============================================================================

class WorkflowBuilder:
    """Builder pattern for creating workflows."""
    
    def __init__(self, name: str):
        self._workflow = Workflow(
            id=str(uuid.uuid4()),
            name=name,
        )
        self._step_counter = 0
    
    def add_step(
        self,
        agent_id: str,
        prompt: str,
        depends_on: list[str] | None = None,
        params: dict | None = None,
    ) -> str:
        """Add a step and return its ID."""
        self._step_counter += 1
        step_id = f"step-{self._step_counter}"
        
        step = WorkflowStep(
            id=step_id,
            agent_id=agent_id,
            prompt=prompt,
            depends_on=depends_on or [],
            params=params or {},
        )
        
        self._workflow.steps.append(step)
        return step_id
    
    def add_parallel_steps(self, steps: list[dict]) -> list[str]:
        """Add multiple steps that run in parallel."""
        step_ids = []
        for step_def in steps:
            step_id = self.add_step(
                agent_id=step_def["agent_id"],
                prompt=step_def["prompt"],
                params=step_def.get("params"),
            )
            step_ids.append(step_id)
        return step_ids
    
    def set_budget(
        self,
        max_tokens: int = 100_000,
        max_steps: int = 100,
        max_time_seconds: int = 3600,
    ):
        """Set workflow budget."""
        self._workflow.budget = WorkflowBudget(
            max_tokens=max_tokens,
            max_steps=max_steps,
            max_time_seconds=max_time_seconds,
        )
        return self
    
    def build(self) -> Workflow:
        """Build the workflow."""
        return self._workflow
