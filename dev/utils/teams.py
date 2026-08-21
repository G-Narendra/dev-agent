"""
Multi-agent teams with coordinator.

Like Cline's multi-agent teams:
- A coordinator agent breaks work into subtasks
- Specialist agents handle each subtask
- State persists across sessions
- Each agent has its own tools and context
"""
from __future__ import annotations
import os
import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Any, Callable
from datetime import datetime
from enum import Enum


class AgentRole(str, Enum):
    COORDINATOR = "coordinator"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    RESEARCHER = "researcher"
    PLANNER = "planner"
    DEVOPS = "devops"
    SECURITY = "security"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class SubTask:
    """A subtask delegated to a specialist agent."""
    id: str
    description: str
    assigned_to: Optional[AgentRole] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    dependencies: list = field(default_factory=list)
    files_changed: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None


@dataclass
class TeamAgent:
    """A specialist agent in the team."""
    role: AgentRole
    name: str
    description: str
    capabilities: list = field(default_factory=list)
    model_override: Optional[str] = None  # Use different model for this agent
    system_prompt: str = ""
    tasks_completed: int = 0
    tasks_failed: int = 0


@dataclass
class Team:
    """A team of agents working on a project."""
    name: str
    agents: list = field(default_factory=list)
    tasks: list = field(default_factory=list)
    coordinator: Optional[TeamAgent] = None
    status: str = "idle"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    project_root: str = "."

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
            "agents": [
                {
                    "role": a.role.value,
                    "name": a.name,
                    "tasks_completed": a.tasks_completed,
                    "tasks_failed": a.tasks_failed,
                }
                for a in self.agents
            ],
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "assigned_to": t.assigned_to.value if t.assigned_to else None,
                    "status": t.status.value,
                    "files_changed": t.files_changed,
                }
                for t in self.tasks
            ],
        }


class TeamManager:
    """Manages multi-agent teams."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.teams: dict[str, Team] = {}
        self._team_dir = os.path.join(self.project_root, ".dev", "teams")
        os.makedirs(self._team_dir, exist_ok=True)
        self._load_teams()

    def _load_teams(self):
        """Load team state from disk."""
        index_path = os.path.join(self._team_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path) as f:
                data = json.load(f)
            for team_data in data.get("teams", []):
                team = Team(
                    name=team_data["name"],
                    status=team_data.get("status", "idle"),
                    created_at=team_data.get("created_at", ""),
                    project_root=self.project_root,
                )
                for agent_data in team_data.get("agents", []):
                    agent = TeamAgent(
                        role=AgentRole(agent_data["role"]),
                        name=agent_data.get("name", agent_data["role"]),
                        description=agent_data.get("description", ""),
                        capabilities=agent_data.get("capabilities", []),
                        tasks_completed=agent_data.get("tasks_completed", 0),
                        tasks_failed=agent_data.get("tasks_failed", 0),
                    )
                    team.agents.append(agent)
                    if agent.role == AgentRole.COORDINATOR:
                        team.coordinator = agent
                
                for task_data in team_data.get("tasks", []):
                    task = SubTask(
                        id=task_data["id"],
                        description=task_data["description"],
                        assigned_to=AgentRole(task_data["assigned_to"]) if task_data.get("assigned_to") else None,
                        status=TaskStatus(task_data.get("status", "pending")),
                        result=task_data.get("result"),
                        files_changed=task_data.get("files_changed", []),
                    )
                    team.tasks.append(task)
                
                self.teams[team.name] = team

    def _save_teams(self):
        """Save team state to disk."""
        index_path = os.path.join(self._team_dir, "index.json")
        data = {
            "teams": [team.to_dict() for team in self.teams.values()]
        }
        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)

    def create_team(self, name: str, task: str) -> Team:
        """Create a new team with default agents."""
        team = Team(name=name, project_root=self.project_root)
        
        # Default team composition
        default_agents = [
            TeamAgent(
                role=AgentRole.COORDINATOR,
                name="Coordinator",
                description="Breaks down tasks and delegates to specialists",
                capabilities=["planning", "delegation", "review"],
            ),
            TeamAgent(
                role=AgentRole.CODER,
                name="Coder",
                description="Writes and modifies code",
                capabilities=["file_edit", "shell_exec", "git"],
            ),
            TeamAgent(
                role=AgentRole.REVIEWER,
                name="Reviewer",
                description="Reviews code for quality and bugs",
                capabilities=["code_review", "security_audit"],
            ),
            TeamAgent(
                role=AgentRole.TESTER,
                name="Tester",
                description="Writes and runs tests",
                capabilities=["test_writing", "test_execution"],
            ),
            TeamAgent(
                role=AgentRole.RESEARCHER,
                name="Researcher",
                description="Researches solutions and best practices",
                capabilities=["web_search", "documentation"],
            ),
        ]
        
        team.agents = default_agents
        team.coordinator = default_agents[0]
        team.status = "active"
        
        # Create initial task breakdown
        coordinator_task = SubTask(
            id="task-0",
            description=f"Coordinate team to: {task}",
            assigned_to=AgentRole.COORDINATOR,
            status=TaskStatus.IN_PROGRESS,
        )
        team.tasks.append(coordinator_task)
        
        self.teams[name] = team
        self._save_teams()
        return team

    def add_agent(self, team_name: str, role: AgentRole, name: str, description: str = "", capabilities: list = None):
        """Add a specialist agent to a team."""
        team = self.teams.get(team_name)
        if not team:
            return None
        
        agent = TeamAgent(
            role=role,
            name=name,
            description=description,
            capabilities=capabilities or [],
        )
        team.agents.append(agent)
        self._save_teams()
        return agent

    def assign_task(self, team_name: str, task_id: str, agent_role: AgentRole) -> bool:
        """Assign a task to an agent."""
        team = self.teams.get(team_name)
        if not team:
            return False
        
        for task in team.tasks:
            if task.id == task_id:
                task.assigned_to = agent_role
                task.status = TaskStatus.ASSIGNED
                self._save_teams()
                return True
        return False

    def complete_task(self, team_name: str, task_id: str, result: str = "", files_changed: list = None) -> bool:
        """Mark a task as completed."""
        team = self.teams.get(team_name)
        if not team:
            return False
        
        for task in team.tasks:
            if task.id == task_id:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.files_changed = files_changed or []
                task.completed_at = datetime.now().isoformat()
                
                # Update agent stats
                if task.assigned_to:
                    for agent in team.agents:
                        if agent.role == task.assigned_to:
                            agent.tasks_completed += 1
                
                self._save_teams()
                return True
        return False

    def fail_task(self, team_name: str, task_id: str, error: str = "") -> bool:
        """Mark a task as failed."""
        team = self.teams.get(team_name)
        if not team:
            return False
        
        for task in team.tasks:
            if task.id == task_id:
                task.status = TaskStatus.FAILED
                task.error = error
                
                if task.assigned_to:
                    for agent in team.agents:
                        if agent.role == task.assigned_to:
                            agent.tasks_failed += 1
                
                self._save_teams()
                return True
        return False

    def decompose_task(self, team_name: str, parent_task_id: str, subtask_descriptions: list[str]) -> list[SubTask]:
        """Decompose a task into subtasks."""
        team = self.teams.get(team_name)
        if not team:
            return []
        
        subtasks = []
        for i, desc in enumerate(subtask_descriptions):
            task_id = f"{parent_task_id}.{i}"
            subtask = SubTask(
                id=task_id,
                description=desc,
                dependencies=[parent_task_id],
            )
            team.tasks.append(subtask)
            subtasks.append(subtask)
        
        self._save_teams()
        return subtasks

    def get_team_status(self, team_name: str) -> dict:
        """Get team status summary."""
        team = self.teams.get(team_name)
        if not team:
            return {"error": f"Team '{team_name}' not found"}
        
        total = len(team.tasks)
        completed = sum(1 for t in team.tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in team.tasks if t.status == TaskStatus.FAILED)
        in_progress = sum(1 for t in team.tasks if t.status == TaskStatus.IN_PROGRESS)
        
        return {
            "name": team.name,
            "status": team.status,
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "agents": len(team.agents),
            "progress_pct": (completed / total * 100) if total > 0 else 0,
        }

    def list_teams(self) -> list[dict]:
        """List all teams."""
        return [
            {
                "name": t.name,
                "status": t.status,
                "agents": len(t.agents),
                "tasks": len(t.tasks),
                "completed": sum(1 for task in t.tasks if task.status == TaskStatus.COMPLETED),
            }
            for t in self.teams.values()
        ]

    def delete_team(self, team_name: str) -> bool:
        """Delete a team."""
        if team_name in self.teams:
            del self.teams[team_name]
            self._save_teams()
            return True
        return False
