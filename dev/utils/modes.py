"""
Plan mode vs Act mode toggle.

Like Cline:
- Plan mode: Explore codebase, ask questions, lay out strategy
- Act mode: Execute the plan with file edits and commands
"""
from __future__ import annotations
from typing import Callable
import os
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class AgentMode(str, Enum):
    PLAN = "plan"      # Explore, analyze, plan only
    ACT = "act"        # Execute edits and commands
    AUTO = "auto"      # Switch between plan and act automatically


@dataclass
class PlanStep:
    """A step in the execution plan."""
    id: int
    description: str
    status: str = "pending"  # pending, in_progress, completed, skipped
    files_involved: list = field(default_factory=list)
    commands_needed: list = field(default_factory=list)
    notes: str = ""


@dataclass
class ExecutionPlan:
    """A plan for executing a task."""
    id: str
    goal: str
    steps: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "draft"  # draft, approved, executing, completed


@dataclass
class ModeManager:
    """Manages plan/act mode switching."""
    current_mode: AgentMode = AgentMode.ACT
    current_plan: Optional[ExecutionPlan] = None
    plans: list = field(default_factory=list)
    _on_mode_change: Optional[Callable] = None

    def set_mode(self, mode: str) -> AgentMode:
        """Switch between plan and act mode."""
        try:
            new_mode = AgentMode(mode)
        except ValueError:
            new_mode = AgentMode.ACT
        
        old_mode = self.current_mode
        self.current_mode = new_mode
        
        if self._on_mode_change and old_mode != new_mode:
            self._on_mode_change(old_mode, new_mode)
        
        return self.current_mode

    def on_mode_change(self, callback: Callable):
        """Register callback for mode changes."""
        self._on_mode_change = callback

    def create_plan(self, goal: str) -> ExecutionPlan:
        """Create a new execution plan."""
        plan_id = f"plan-{len(self.plans)}"
        plan = ExecutionPlan(id=plan_id, goal=goal)
        self.current_plan = plan
        self.plans.append(plan)
        return plan

    def add_step(self, plan_id: str, description: str, files: list = None, commands: list = None) -> PlanStep:
        """Add a step to a plan."""
        plan = self._get_plan(plan_id)
        if not plan:
            return None
        
        step = PlanStep(
            id=len(plan.steps),
            description=description,
            files_involved=files or [],
            commands_needed=commands or [],
        )
        plan.steps.append(step)
        return step

    def approve_plan(self, plan_id: str) -> bool:
        """Approve a plan for execution."""
        plan = self._get_plan(plan_id)
        if plan:
            plan.status = "approved"
            return True
        return False

    def start_step(self, plan_id: str, step_id: int) -> bool:
        """Mark a step as in progress."""
        plan = self._get_plan(plan_id)
        if plan and step_id < len(plan.steps):
            plan.steps[step_id].status = "in_progress"
            plan.status = "executing"
            return True
        return False

    def complete_step(self, plan_id: str, step_id: int, notes: str = "") -> bool:
        """Mark a step as completed."""
        plan = self._get_plan(plan_id)
        if plan and step_id < len(plan.steps):
            plan.steps[step_id].status = "completed"
            plan.steps[step_id].notes = notes
            
            # Check if all steps completed
            if all(s.status == "completed" for s in plan.steps):
                plan.status = "completed"
            return True
        return False

    def skip_step(self, plan_id: str, step_id: int, reason: str = "") -> bool:
        """Skip a step."""
        plan = self._get_plan(plan_id)
        if plan and step_id < len(plan.steps):
            plan.steps[step_id].status = "skipped"
            plan.steps[step_id].notes = reason
            return True
        return False

    def get_next_step(self, plan_id: str) -> Optional[PlanStep]:
        """Get the next pending step in a plan."""
        plan = self._get_plan(plan_id)
        if plan:
            for step in plan.steps:
                if step.status == "pending":
                    return step
        return None

    def _get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a plan by ID."""
        for plan in self.plans:
            if plan.id == plan_id:
                return plan
        return self.current_plan if self.current_plan and self.current_plan.id == plan_id else None

    def is_plan_mode(self) -> bool:
        """Check if we're in plan mode."""
        return self.current_mode == AgentMode.PLAN

    def is_act_mode(self) -> bool:
        """Check if we're in act mode."""
        return self.current_mode == AgentMode.ACT

    def should_act(self, action_type: str) -> bool:
        """Check if we should execute an action based on current mode."""
        if self.current_mode == AgentMode.ACT:
            return True
        if self.current_mode == AgentMode.PLAN:
            # In plan mode, only allow read-only actions
            read_only = ["read_files", "code_search", "glob", "list_directory", "web_search", "read_url"]
            return action_type in read_only
        return True  # AUTO mode

    def format_plan(self, plan: ExecutionPlan = None) -> str:
        """Format a plan for display."""
        plan = plan or self.current_plan
        if not plan:
            return "No active plan"
        
        lines = [f"Plan: {plan.goal}", f"Status: {plan.status}", ""]
        for step in plan.steps:
            status_icon = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "skipped": "⏭️"}.get(step.status, "❓")
            lines.append(f"  {status_icon} Step {step.id}: {step.description}")
            if step.notes:
                lines.append(f"     Notes: {step.notes}")
        return "\n".join(lines)

    def save_state(self, path: str = ".dev/mode_state.json"):
        """Save mode state to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = {
            "current_mode": self.current_mode.value,
            "current_plan": self.current_plan.id if self.current_plan else None,
            "plans": [
                {
                    "id": p.id,
                    "goal": p.goal,
                    "status": p.status,
                    "steps": [
                        {
                            "id": s.id,
                            "description": s.description,
                            "status": s.status,
                            "notes": s.notes,
                        }
                        for s in p.steps
                    ],
                }
                for p in self.plans
            ],
        }
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self, path: str = ".dev/mode_state.json"):
        """Load mode state from disk."""
        if os.path.exists(path):
            with open(path) as f:
                state = json.load(f)
            self.current_mode = AgentMode(state.get("current_mode", "act"))
            for plan_data in state.get("plans", []):
                plan = ExecutionPlan(
                    id=plan_data["id"],
                    goal=plan_data["goal"],
                    status=plan_data.get("status", "draft"),
                )
                for step_data in plan_data.get("steps", []):
                    step = PlanStep(
                        id=step_data["id"],
                        description=step_data["description"],
                        status=step_data.get("status", "pending"),
                        notes=step_data.get("notes", ""),
                    )
                    plan.steps.append(step)
                self.plans.append(plan)
                if plan.id == state.get("current_plan"):
                    self.current_plan = plan
