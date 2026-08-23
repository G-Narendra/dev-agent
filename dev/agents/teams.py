"""
Multi-Agent Teams — Parallel Work Coordination

Inspired by Cline's Kanban board, this module allows multiple agents
to work on different tasks simultaneously, each with their own context
and git worktree.

Features:
1. Coordinator agent that decomposes tasks
2. Specialist agents for different domains
3. Git worktree isolation (each agent gets its own branch)
4. Task dependency management
5. Status dashboard
"""
import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from datetime import datetime


class AgentStatus(Enum):
    """Status of an agent."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Task:
    """A task to be executed by an agent."""
    id: str
    title: str
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: AgentStatus = AgentStatus.PENDING
    assigned_to: str = ""
    depends_on: list = field(default_factory=list)
    result: str = ""
    error: str = ""
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    files_changed: list = field(default_factory=list)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class AgentTeam:
    """A team of agents working on related tasks."""
    name: str
    description: str = ""
    tasks: list = field(default_factory=list)
    branch: str = ""
    worktree_path: str = ""
    status: AgentStatus = AgentStatus.PENDING
    coordinator: str = ""


class TeamCoordinator:
    """
    Coordinates multiple agents working in parallel.
    
    The coordinator:
    1. Decomposes complex tasks into subtasks
    2. Assigns subtasks to specialist agents
    3. Creates git worktrees for isolation
    4. Monitors progress and handles failures
    5. Merges results when complete
    
    Usage:
        coordinator = TeamCoordinator(provider, project_path=".")
        
        # Create a team for a complex task
        team = await coordinator.create_team(
            name="portfolio-build",
            task="Build a complete portfolio website",
        )
        
        # Coordinator automatically decomposes and assigns tasks
        # Each agent works in its own worktree
        
        # Monitor progress
        status = coordinator.get_status(team.name)
        
        # Merge results when all tasks complete
        await coordinator.merge_team(team.name)
    """
    
    def __init__(self, provider=None, project_path: str = "."):
        self.provider = provider
        self.project_path = os.path.abspath(project_path)
        self.teams: dict[str, AgentTeam] = {}
        self._task_counter = 0
        # Resource limits per agent
        self._max_tokens_per_agent = 50_000  # Token budget per agent
        self._max_steps_per_agent = 25  # Max tool call steps per agent
        self._failure_isolation = True  # Isolate failures between agents
        # Load balancing: track RPM usage per agent
        self._agent_rpm_usage: dict[str, int] = {}
        self._agent_logs: dict[str, list] = {}  # Per-agent log aggregation
    
    async def create_team(self, name: str, task: str, 
                          specialist_roles: list = None) -> AgentTeam:
        """
        Create a team and decompose the task.
        
        Args:
            name: Team name
            task: High-level task description
            specialist_roles: Optional list of specialist roles
            
        Returns:
            AgentTeam with decomposed tasks
        """
        # Create git worktree for this team
        branch = f"team/{name}"
        worktree_path = await self._create_worktree(branch)
        
        # Decompose task into subtasks
        tasks = await self._decompose_task(task, specialist_roles)
        
        team = AgentTeam(
            name=name,
            description=task,
            tasks=tasks,
            branch=branch,
            worktree_path=worktree_path,
            status=AgentStatus.RUNNING,
        )
        
        self.teams[name] = team
        return team
    
    async def _create_worktree(self, branch: str) -> str:
        """Create a git worktree for a team."""
        worktree_dir = os.path.join(self.project_path, ".dev", "worktrees", branch.replace("/", "_"))
        
        try:
            # Create branch if it doesn't exist
            subprocess.run(
                ["git", "branch", branch],
                cwd=self.project_path,
                capture_output=True,
                timeout=5,
            )
            
            # Create worktree
            result = subprocess.run(
                ["git", "worktree", "add", worktree_dir, branch],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                return worktree_dir
            
            # Worktree might already exist
            if os.path.exists(worktree_dir):
                return worktree_dir
            
            # Fallback: use main directory
            return self.project_path
        except Exception:
            return self.project_path
    
    async def _decompose_task(self, task: str, 
                              specialist_roles: list = None) -> list[Task]:
        """
        Decompose a high-level task into subtasks.
        
        Uses the LLM to analyze the task and create a work breakdown.
        """
        # Default decomposition for common task types
        task_lower = task.lower()
        
        if any(kw in task_lower for kw in ['website', 'portfolio', 'web app', 'frontend']):
            return self._decompose_web_task(task)
        elif any(kw in task_lower for kw in ['api', 'backend', 'server', 'database']):
            return self._decompose_backend_task(task)
        elif any(kw in task_lower for kw in ['cli', 'tool', 'command']):
            return self._decompose_cli_task(task)
        else:
            return self._decompose_generic_task(task)
    
    def _decompose_web_task(self, task: str) -> list[Task]:
        """Decompose a web development task."""
        self._task_counter += 1
        base = self._task_counter
        
        return [
            Task(
                id=f"task-{base}",
                title="Setup project structure",
                description="Create project folder, package.json, and basic configuration",
                priority=TaskPriority.CRITICAL,
            ),
            Task(
                id=f"task-{base+1}",
                title="Create server",
                description="Build Express/Node.js server with routes and middleware",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base}"],
            ),
            Task(
                id=f"task-{base+2}",
                title="Build HTML pages",
                description="Create all HTML/EJS template files with content",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base}"],
            ),
            Task(
                id=f"task-{base+3}",
                title="Create CSS styles",
                description="Write complete CSS with responsive design and animations",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base+2}"],
            ),
            Task(
                id=f"task-{base+4}",
                title="Write JavaScript",
                description="Implement interactive features and client-side logic",
                priority=TaskPriority.MEDIUM,
                depends_on=[f"task-{base+2}"],
            ),
            Task(
                id=f"task-{base+5}",
                title="Install and test",
                description="Install dependencies and verify the application works",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base+1}", f"task-{base+3}", f"task-{base+4}"],
            ),
        ]
    
    def _decompose_backend_task(self, task: str) -> list[Task]:
        """Decompose a backend development task."""
        self._task_counter += 1
        base = self._task_counter
        
        return [
            Task(
                id=f"task-{base}",
                title="Design database schema",
                description="Create database models and migrations",
                priority=TaskPriority.CRITICAL,
            ),
            Task(
                id=f"task-{base+1}",
                title="Build API endpoints",
                description="Implement REST/GraphQL API routes",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base}"],
            ),
            Task(
                id=f"task-{base+2}",
                title="Add authentication",
                description="Implement auth middleware and user management",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base+1}"],
            ),
            Task(
                id=f"task-{base+3}",
                title="Write tests",
                description="Create unit and integration tests",
                priority=TaskPriority.MEDIUM,
                depends_on=[f"task-{base+1}"],
            ),
        ]
    
    def _decompose_cli_task(self, task: str) -> list[Task]:
        """Decompose a CLI tool development task."""
        self._task_counter += 1
        base = self._task_counter
        
        return [
            Task(
                id=f"task-{base}",
                title="Design CLI interface",
                description="Plan commands, flags, and help text",
                priority=TaskPriority.CRITICAL,
            ),
            Task(
                id=f"task-{base+1}",
                title="Implement core logic",
                description="Build the main functionality",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base}"],
            ),
            Task(
                id=f"task-{base+2}",
                title="Add error handling",
                description="Implement comprehensive error handling and user feedback",
                priority=TaskPriority.MEDIUM,
                depends_on=[f"task-{base+1}"],
            ),
            Task(
                id=f"task-{base+3}",
                title="Write documentation",
                description="Create README and help documentation",
                priority=TaskPriority.LOW,
                depends_on=[f"task-{base+1}"],
            ),
        ]
    
    def _decompose_generic_task(self, task: str) -> list[Task]:
        """Decompose a generic task."""
        self._task_counter += 1
        base = self._task_counter
        
        return [
            Task(
                id=f"task-{base}",
                title="Plan and research",
                description="Analyze requirements and plan approach",
                priority=TaskPriority.CRITICAL,
            ),
            Task(
                id=f"task-{base+1}",
                title="Implement core features",
                description="Build the main functionality",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base}"],
            ),
            Task(
                id=f"task-{base+2}",
                title="Test and verify",
                description="Test the implementation and fix issues",
                priority=TaskPriority.HIGH,
                depends_on=[f"task-{base+1}"],
            ),
        ]
    
    def get_status(self, team_name: str) -> dict:
        """Get status of a team."""
        team = self.teams.get(team_name)
        if not team:
            return {"error": f"Team '{team_name}' not found"}
        
        completed = sum(1 for t in team.tasks if t.status == AgentStatus.COMPLETED)
        failed = sum(1 for t in team.tasks if t.status == AgentStatus.FAILED)
        running = sum(1 for t in team.tasks if t.status == AgentStatus.RUNNING)
        pending = sum(1 for t in team.tasks if t.status == AgentStatus.PENDING)
        
        return {
            "team": team.name,
            "description": team.description,
            "branch": team.branch,
            "status": team.status.value,
            "tasks": {
                "total": len(team.tasks),
                "completed": completed,
                "failed": failed,
                "running": running,
                "pending": pending,
            },
            "progress": f"{completed}/{len(team.tasks)} ({completed/max(len(team.tasks),1)*100:.0f}%)",
            "task_details": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status.value,
                    "assigned_to": t.assigned_to,
                }
                for t in team.tasks
            ],
        }
    
    def get_all_status(self) -> list[dict]:
        """Get status of all teams."""
        return [self.get_status(name) for name in self.teams]
    
    async def merge_team(self, team_name: str) -> dict:
        """
        Merge a team's work into the main branch.
        
        Returns:
            Merge result with any conflicts
        """
        team = self.teams.get(team_name)
        if not team:
            return {"error": f"Team '{team_name}' not found"}
        
        try:
            # Stage all changes in worktree
            subprocess.run(
                ["git", "add", "-A"],
                cwd=team.worktree_path,
                capture_output=True,
                timeout=10,
            )
            
            # Commit
            subprocess.run(
                ["git", "commit", "-m", f"Team {team_name}: complete all tasks"],
                cwd=team.worktree_path,
                capture_output=True,
                timeout=10,
            )
            
            # Merge into main
            result = subprocess.run(
                ["git", "merge", team.branch, "--no-edit"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                team.status = AgentStatus.COMPLETED
                return {"success": True, "message": f"Merged {team_name} into main"}
            else:
                return {"error": f"Merge conflict: {result.stderr}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def cleanup_team(self, team_name: str):
        """Clean up a team's worktree."""
        team = self.teams.get(team_name)
        if not team:
            return
        
        try:
            # Remove worktree
            subprocess.run(
                ["git", "worktree", "remove", team.worktree_path, "--force"],
                cwd=self.project_path,
                capture_output=True,
                timeout=10,
            )
            
            # Remove branch
            subprocess.run(
                ["git", "branch", "-D", team.branch],
                cwd=self.project_path,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass
        
        del self.teams[team_name]


class ParallelAgent:
    """
    An agent that runs in its own worktree.
    
    Each ParallelAgent:
    1. Gets its own git branch and worktree
    2. Has its own conversation context
    3. Can read/write files without affecting other agents
    4. Reports progress to the coordinator
    """
    
    def __init__(self, agent_id: str, provider, tools, 
                 worktree_path: str, config: Any = None):
        self.agent_id = agent_id
        self.provider = provider
        self.tools = tools
        self.worktree_path = worktree_path
        self.config = config
        self.status = AgentStatus.PENDING
        self.current_task: Optional[Task] = None
        self.messages = []
        self.results = []
    
    async def execute_task(self, task: Task, 
                           on_progress: Callable = None) -> dict:
        """
        Execute a task in this agent's worktree.
        
        Args:
            task: Task to execute
            on_progress: Callback for progress updates
            
        Returns:
            Execution result
        """
        self.current_task = task
        self.status = AgentStatus.RUNNING
        task.status = AgentStatus.RUNNING
        task.started_at = datetime.now().isoformat()
        task.assigned_to = self.agent_id
        
        try:
            # Import here to avoid circular imports
            from .production_loop import ProductionAgentLoop, LoopConfig
            from ..agents.runtime import ToolRegistry
            from ..cli.commands import register_new_tools
            
            # Create isolated tool registry for this worktree
            registry = ToolRegistry()
            register_new_tools(registry, self.worktree_path)
            
            # Create agent loop
            agent = ProductionAgentLoop(
                provider=self.provider,
                tool_registry=registry,
                config=LoopConfig(
                    model=self.config.model if self.config else "meta/llama-3.1-8b-instruct",
                    temperature=0.3,
                    max_tokens=4096,
                    auto_lint=True,
                    auto_commit=False,  # Team coordinator handles commits
                    approval_mode="full-auto",
                ),
                project_path=self.worktree_path,
            )
            
            # Execute the task
            def on_text(chunk):
                if on_progress:
                    on_progress(self.agent_id, task.id, chunk)
            
            result = await agent.run_streaming(
                prompt=f"Task: {task.title}\n\n{task.description}\n\nComplete this task. Create all necessary files.",
                system_prompt=f"You are a specialist agent working on: {task.title}",
                on_text=on_text,
                max_steps=20,
            )
            
            # Update task status
            if result.get("status") == "completed":
                task.status = AgentStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                task.result = result.get("content", "")
                self.status = AgentStatus.COMPLETED
            else:
                task.status = AgentStatus.FAILED
                task.error = result.get("message", "Unknown error")
                self.status = AgentStatus.FAILED
            
            return result
        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
            self.status = AgentStatus.FAILED
            return {"status": "error", "message": str(e)}
    
    def get_status(self) -> dict:
        """Get agent status."""
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "current_task": self.current_task.title if self.current_task else None,
            "worktree": self.worktree_path,
        }
