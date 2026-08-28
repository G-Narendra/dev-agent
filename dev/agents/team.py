"""
Multi-Agent Team System for Dev.

Allows creating teams of specialized agents that collaborate on complex tasks.
Modeled after Claude Code's sub-agent pattern.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TeamRole(Enum):
    """Roles for team agents."""
    LEADER = "leader"
    SPECIALIST = "specialist"
    REVIEWER = "reviewer"


class TeamTaskStatus(Enum):
    """Status of a team task."""
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


@dataclass
class TeamTask:
    """A task assigned to a team agent."""
    description: str
    agent_id: str = ""
    status: TeamTaskStatus = TeamTaskStatus.ASSIGNED
    result: str = ""
    context: str = ""
    priority: int = 0


@dataclass
class TeamMessage:
    """A message between team agents."""
    sender: str
    content: str
    message_type: str = "info"  # info, request, result, error
    timestamp: float = field(default_factory=time.time)


class Mailbox:
    """Simple mailbox for agent communication."""
    
    def __init__(self):
        self._messages: dict[str, list[TeamMessage]] = {}
    
    def send(self, sender: str, recipient: str, content: str, msg_type: str = "info"):
        """Send a message."""
        if recipient not in self._messages:
            self._messages[recipient] = []
        self._messages[recipient].append(
            TeamMessage(sender=sender, content=content, message_type=msg_type)
        )
    
    def receive(self, agent_id: str) -> list[TeamMessage]:
        """Get messages for an agent."""
        return self._messages.pop(agent_id, [])
    
    def get_all(self) -> dict:
        """Get all messages."""
        return dict(self._messages)


class TeamAgent:
    """An agent in a team."""
    
    def __init__(self, agent_id: str, role: TeamRole, specialties: list[str] = None):
        self.agent_id = agent_id
        self.role = role
        self.specialties = specialties or []
        self.mailbox = Mailbox()
        self._tasks: list[TeamTask] = []
    
    def check_messages(self) -> list[TeamMessage]:
        """Check for new messages."""
        return self.mailbox.receive(self.agent_id)
    
    def send_message(self, recipient: str, content: str, msg_type: str = "info"):
        """Send a message to another agent."""
        self.mailbox.send(self.agent_id, recipient, content, msg_type)


class Team:
    """
    A team of agents working together.
    
    The leader delegates tasks to specialists and reviews results.
    """
    
    def __init__(self, name: str):
        self.name = name
        self._agents: dict[str, TeamAgent] = {}
        self._tasks: list[TeamTask] = []
        self._shared_mailbox = Mailbox()
        self._runtime = None  # Set by parent to enable real agent execution
    
    def add_agent(self, agent_id: str, role: TeamRole, specialties: list[str] = None) -> TeamAgent:
        """Add an agent to the team."""
        agent = TeamAgent(agent_id, role, specialties)
        agent.mailbox = self._shared_mailbox
        self._agents[agent_id] = agent
        return agent
    
    def get_leader(self) -> Optional[TeamAgent]:
        """Get the team leader."""
        for agent in self._agents.values():
            if agent.role == TeamRole.LEADER:
                return agent
        return None
    
    def get_specialists(self) -> list[TeamAgent]:
        """Get all specialist agents."""
        return [a for a in self._agents.values() if a.role == TeamRole.SPECIALIST]
    
    def get_status(self) -> dict:
        """Get team status."""
        return {
            "name": self.name,
            "agents": len(self._agents),
            "tasks": len(self._tasks),
            "completed": sum(1 for t in self._tasks if t.status == TeamTaskStatus.COMPLETED),
            "in_progress": sum(1 for t in self._tasks if t.status == TeamTaskStatus.IN_PROGRESS),
            "failed": sum(1 for t in self._tasks if t.status == TeamTaskStatus.FAILED),
        }
    
    def delegate_task(self, description: str, agent_id: str = None, context: str = "") -> TeamTask:
        """Delegate a task to an agent."""
        # Auto-assign to best specialist if no agent specified
        if not agent_id:
            agent_id = self._find_best_agent(description)
        
        task = TeamTask(
            description=description,
            agent_id=agent_id,
            context=context,
            priority=len(self._tasks),
        )
        self._tasks.append(task)
        return task
    
    def _find_best_agent(self, description: str) -> str:
        """Find the best agent for a task based on specialties."""
        desc_lower = description.lower()
        best_agent = None
        best_score = -1
        
        for agent in self._agents.values():
            if agent.role == TeamRole.LEADER:
                continue
            score = sum(1 for s in agent.specialties if s.lower() in desc_lower)
            if score > best_score:
                best_score = score
                best_agent = agent.agent_id
        
        # Fallback to first specialist
        if not best_agent:
            specialists = self.get_specialists()
            if specialists:
                best_agent = specialists[0].agent_id
            else:
                best_agent = list(self._agents.keys())[0] if self._agents else "default"
        
        return best_agent
    
    async def execute_tasks(self, provider=None, tool_registry=None) -> list[dict]:
        """
        Execute all assigned tasks using real agent loops.
        
        If provider and tool_registry are provided, spawns actual ProductionAgentLoop
        instances for each task. Otherwise returns task descriptions for manual execution.
        """
        results = []
        
        for task in self._tasks:
            if task.status != TeamTaskStatus.ASSIGNED:
                continue
            
            task.status = TeamTaskStatus.IN_PROGRESS
            
            if provider and tool_registry:
                # Execute with real agent loop
                try:
                    from .production_loop import ProductionAgentLoop, LoopConfig
                    
                    loop = ProductionAgentLoop(
                        provider=provider,
                        tool_registry=tool_registry,
                        config=LoopConfig(
                            approval_mode="full-auto",
                            auto_commit=False,  # Don't commit in team tasks
                        ),
                    )
                    
                    system_prompt = f"You are agent '{task.agent_id}' in team '{self.name}'. {task.context}"
                    
                    result = await loop.run(
                        prompt=task.description,
                        system_prompt=system_prompt,
                        max_steps=20,
                    )
                    
                    task.result = result.get("content", str(result))
                    task.status = TeamTaskStatus.COMPLETED if result.get("status") == "completed" else TeamTaskStatus.FAILED
                    
                    results.append({
                        "task": task.description,
                        "agent": task.agent_id,
                        "status": task.status.value,
                        "result": task.result[:1000],
                    })
                except Exception as e:
                    task.status = TeamTaskStatus.FAILED
                    task.result = str(e)
                    results.append({
                        "task": task.description,
                        "agent": task.agent_id,
                        "status": "failed",
                        "error": str(e),
                    })
            else:
                # No provider — return task for manual execution
                task.status = TeamTaskStatus.COMPLETED
                results.append({
                    "task": task.description,
                    "agent": task.agent_id,
                    "status": "pending_manual",
                    "message": f"Agent '{task.agent_id}' should execute: {task.description}",
                })
        
        return results
    
    def review_results(self) -> dict:
        """Review all task results."""
        completed = [t for t in self._tasks if t.status == TeamTaskStatus.COMPLETED]
        failed = [t for t in self._tasks if t.status == TeamTaskStatus.FAILED]
        
        return {
            "total": len(self._tasks),
            "completed": len(completed),
            "failed": len(failed),
            "results": [
                {"task": t.description, "agent": t.agent_id, "status": t.status.value, "result": t.result[:500]}
                for t in self._tasks
            ],
        }


class TeamManager:
    """Manages multiple teams."""
    
    def __init__(self):
        self._teams: dict[str, Team] = {}
    
    def create_team(self, name: str) -> Team:
        """Create a new team."""
        team = Team(name)
        self._teams[name] = team
        return team
    
    def get_team(self, name: str) -> Optional[Team]:
        """Get a team by name."""
        return self._teams.get(name)
    
    def list_teams(self) -> list[dict]:
        """List all teams."""
        return [
            {"name": t.name, "agents": len(t._agents), "tasks": len(t._tasks)}
            for t in self._teams.values()
        ]
    
    def delete_team(self, name: str):
        """Delete a team."""
        self._teams.pop(name, None)
