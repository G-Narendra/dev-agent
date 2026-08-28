"""
Team Tools — Agent tools for multi-agent team management

These tools allow the agent to:
1. Create teams for complex tasks
2. Monitor team progress
3. Merge team results
4. Clean up completed teams
"""
from typing import Any

from .base import Tool



__all__ = ["TeamCreateTool", "TeamStatusTool", "TeamMergeTool", "TeamCleanupTool", "TeamExecuteTool"]

class TeamCreateTool(Tool):
    """Create a multi-agent team with specialized roles (architect, developer, tester, etc.)."""
    
    name = "team_create"
    description = "Create a team of agents to work on a complex task in parallel."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Team name"},
            "task": {"type": "string", "description": "High-level task description"},
        },
        "required": ["name", "task"],
    }
    
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        name = input_data.get("name", "")
        task = input_data.get("task", "")
        
        if not name or not task:
            return {"error": "Name and task required"}
        
        if not self.coordinator:
            return {"error": "Team coordinator not initialized"}
        
        try:
            team = await self.coordinator.create_team(name, task)
            return {
                "success": True,
                "team": team.name,
                "branch": team.branch,
                "tasks": len(team.tasks),
                "task_list": [
                    {"id": t.id, "title": t.title, "priority": t.priority.name}
                    for t in team.tasks
                ],
            }
        except Exception as e:
            return {"error": str(e)}


class TeamStatusTool(Tool):
    """Show status of all active agent teams including task assignments."""
    
    name = "team_status"
    description = "Get the current status of a team and its tasks."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Team name (empty for all teams)"},
        },
        "required": [],
    }
    
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        name = input_data.get("name", "")
        
        if not self.coordinator:
            return {"error": "Team coordinator not initialized"}
        
        if name:
            return self.coordinator.get_status(name)
        else:
            return {"teams": self.coordinator.get_all_status()}


class TeamMergeTool(Tool):
    """Merge completed work from team member branches into the main branch."""
    
    name = "team_merge"
    description = "Merge a completed team's work into the main branch."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Team name to merge"},
        },
        "required": ["name"],
    }
    
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        name = input_data.get("name", "")
        
        if not name:
            return {"error": "Team name required"}
        
        if not self.coordinator:
            return {"error": "Team coordinator not initialized"}
        
        try:
            result = await self.coordinator.merge_team(name)
            return result
        except Exception as e:
            return {"error": str(e)}


class TeamCleanupTool(Tool):
    """Clean up completed team sessions and temporary branches."""
    
    name = "team_cleanup"
    description = "Clean up a team's worktree and branch after merging."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Team name to clean up"},
        },
        "required": ["name"],
    }
    
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        name = input_data.get("name", "")
        
        if not name:
            return {"error": "Team name required"}
        
        if not self.coordinator:
            return {"error": "Team coordinator not initialized"}
        
        try:
            await self.coordinator.cleanup_team(name)
            return {"success": True, "message": f"Cleaned up team: {name}"}
        except Exception as e:
            return {"error": str(e)}


class TeamExecuteTool(Tool):
    """Dispatch a task to a team member agent for parallel execution."""
    
    name = "team_execute"
    description = "Execute a specific task on a team's worktree."
    parameters = {
        "type": "object",
        "properties": {
            "team": {"type": "string", "description": "Team name"},
            "task_id": {"type": "string", "description": "Task ID to execute"},
        },
        "required": ["team", "task_id"],
    }
    
    def __init__(self, coordinator=None, provider=None):
        self.coordinator = coordinator
        self.provider = provider
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        team_name = input_data.get("team", "")
        task_id = input_data.get("task_id", "")
        
        if not team_name or not task_id:
            return {"error": "Team name and task ID required"}
        
        if not self.coordinator:
            return {"error": "Team coordinator not initialized"}
        
        team = self.coordinator.teams.get(team_name)
        if not team:
            return {"error": f"Team '{team_name}' not found"}
        
        # Find the task
        task = None
        for t in team.tasks:
            if t.id == task_id:
                task = t
                break
        
        if not task:
            return {"error": f"Task '{task_id}' not found"}
        
        # Check dependencies
        for dep_id in task.depends_on:
            dep_task = next((t for t in team.tasks if t.id == dep_id), None)
            if dep_task and dep_task.status != AgentStatus.COMPLETED:
                return {"error": f"Task depends on '{dep_id}' which is not complete"}
        
        # Create and run agent
        agent = ParallelAgent(
            agent_id=f"{team_name}_{task_id}",
            provider=self.provider,
            tools=None,
            worktree_path=team.worktree_path,
        )
        
        result = await agent.execute_task(task)
        return result
