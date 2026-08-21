"""
Workflow Templates, Cost Dashboard, and Reasoning Effort for Dev.

Improvement #19: Workflow templates
Improvement #20: Cost/token dashboard
Improvement #21: Reasoning effort control
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


# ============================================================================
# Workflow Templates (#19)
# ============================================================================

WORKFLOW_TEMPLATES = {
    "full-stack-app": {
        "name": "Full Stack Application",
        "description": "Build a complete full-stack application",
        "steps": [
            {"agent": "planner", "prompt": "Plan the architecture for a full-stack application"},
            {"agent": "coder", "prompt": "Set up the project structure"},
            {"agent": "coder", "prompt": "Implement the backend API"},
            {"agent": "coder", "prompt": "Implement the frontend UI"},
            {"agent": "reviewer", "prompt": "Review all code for issues"},
        ],
    },
    "api-service": {
        "name": "REST API Service",
        "description": "Build a REST API service",
        "steps": [
            {"agent": "planner", "prompt": "Plan the API endpoints and data models"},
            {"agent": "coder", "prompt": "Implement the API endpoints"},
            {"agent": "coder", "prompt": "Add validation and error handling"},
            {"agent": "reviewer", "prompt": "Review the API implementation"},
        ],
    },
    "cli-tool": {
        "name": "CLI Tool",
        "description": "Build a command-line tool",
        "steps": [
            {"agent": "planner", "prompt": "Plan the CLI interface and commands"},
            {"agent": "coder", "prompt": "Implement the CLI entry point"},
            {"agent": "coder", "prompt": "Implement the core logic"},
            {"agent": "coder", "prompt": "Add tests"},
        ],
    },
    "refactor": {
        "name": "Refactor Code",
        "description": "Refactor existing codebase",
        "steps": [
            {"agent": "researcher", "prompt": "Analyze the current codebase structure"},
            {"agent": "planner", "prompt": "Create a refactoring plan"},
            {"agent": "coder", "prompt": "Execute the refactoring"},
            {"agent": "reviewer", "prompt": "Review the refactored code"},
        ],
    },
    "bug-fix": {
        "name": "Bug Fix",
        "description": "Find and fix a bug",
        "steps": [
            {"agent": "researcher", "prompt": "Investigate the bug and find root cause"},
            {"agent": "coder", "prompt": "Implement the fix"},
            {"agent": "reviewer", "prompt": "Review the fix"},
        ],
    },
    "test-coverage": {
        "name": "Add Test Coverage",
        "description": "Add tests to existing code",
        "steps": [
            {"agent": "researcher", "prompt": "Analyze existing code for test coverage gaps"},
            {"agent": "coder", "prompt": "Write unit tests"},
            {"agent": "coder", "prompt": "Write integration tests"},
            {"agent": "reviewer", "prompt": "Review all tests"},
        ],
    },
    "documentation": {
        "name": "Write Documentation",
        "description": "Create comprehensive documentation",
        "steps": [
            {"agent": "researcher", "prompt": "Analyze the codebase"},
            {"agent": "coder", "prompt": "Write README and setup docs"},
            {"agent": "coder", "prompt": "Write API documentation"},
            {"agent": "coder", "prompt": "Write usage examples"},
        ],
    },
    "docker-deploy": {
        "name": "Docker Deployment",
        "description": "Containerize and prepare for deployment",
        "steps": [
            {"agent": "coder", "prompt": "Create Dockerfile"},
            {"agent": "coder", "prompt": "Create docker-compose.yml"},
            {"agent": "coder", "prompt": "Add health checks and monitoring"},
            {"agent": "reviewer", "prompt": "Review deployment configuration"},
        ],
    },
}


def get_template(name: str) -> dict | None:
    """Get a workflow template by name."""
    return WORKFLOW_TEMPLATES.get(name)


def list_templates() -> list[dict]:
    """List all available templates."""
    return [
        {"name": k, "description": v["description"], "steps": len(v["steps"])}
        for k, v in WORKFLOW_TEMPLATES.items()
    ]


# ============================================================================
# Cost Dashboard (#20)
# ============================================================================

@dataclass
class CostEntry:
    """A single cost entry."""
    timestamp: float
    tokens_in: int
    tokens_out: int
    model: str
    cost: float = 0.0
    operation: str = ""


class CostDashboard:
    """
    Cost and token usage dashboard.
    
    Tracks:
    - Token usage per request
    - Cost per session
    - Rate limiting stats
    - Model usage breakdown
    """
    
    def __init__(self):
        self._entries: list[CostEntry] = []
        self._session_start = time.time()
    
    def record(
        self,
        tokens_in: int,
        tokens_out: int,
        model: str = "",
        cost: float = 0.0,
        operation: str = "",
    ):
        """Record a cost entry."""
        self._entries.append(CostEntry(
            timestamp=time.time(),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model,
            cost=cost,
            operation=operation,
        ))
    
    def get_summary(self) -> dict:
        """Get cost summary."""
        total_in = sum(e.tokens_in for e in self._entries)
        total_out = sum(e.tokens_out for e in self._entries)
        total_cost = sum(e.cost for e in self._entries)
        
        # Model breakdown
        model_usage = {}
        for e in self._entries:
            if e.model not in model_usage:
                model_usage[e.model] = {"count": 0, "tokens": 0}
            model_usage[e.model]["count"] += 1
            model_usage[e.model]["tokens"] += e.tokens_in + e.tokens_out
        
        # Requests per minute
        elapsed = time.time() - self._session_start
        rpm = len(self._entries) / (elapsed / 60) if elapsed > 0 else 0
        
        return {
            "session_duration_seconds": elapsed,
            "total_requests": len(self._entries),
            "requests_per_minute": round(rpm, 1),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_total": total_in + total_out,
            "total_cost": total_cost,
            "model_usage": model_usage,
            "avg_tokens_per_request": (total_in + total_out) // max(len(self._entries), 1),
        }
    
    def get_breakdown(self) -> list[dict]:
        """Get detailed breakdown by operation."""
        operations = {}
        for e in self._entries:
            op = e.operation or "unknown"
            if op not in operations:
                operations[op] = {"count": 0, "tokens": 0, "cost": 0.0}
            operations[op]["count"] += 1
            operations[op]["tokens"] += e.tokens_in + e.tokens_out
            operations[op]["cost"] += e.cost
        
        return [
            {"operation": op, **data}
            for op, data in sorted(operations.items(), key=lambda x: -x[1]["tokens"])
        ]
    
    def format_dashboard(self) -> str:
        """Format dashboard as text."""
        summary = self.get_summary()
        
        lines = [
            "=" * 50,
            "  DEV COST DASHBOARD",
            "=" * 50,
            "",
            f"  Session Duration: {summary['session_duration_seconds']:.0f}s",
            f"  Total Requests:   {summary['total_requests']}",
            f"  Requests/min:     {summary['requests_per_minute']}",
            "",
            f"  Tokens In:        {summary['tokens_in']:,}",
            f"  Tokens Out:       {summary['tokens_out']:,}",
            f"  Tokens Total:     {summary['tokens_total']:,}",
            f"  Avg per Request:  {summary['avg_tokens_per_request']:,}",
            "",
            f"  Total Cost:       ${summary['total_cost']:.4f}",
            "",
            "  Model Usage:",
        ]
        
        for model, data in summary["model_usage"].items():
            lines.append(f"    {model}: {data['count']} requests, {data['tokens']:,} tokens")
        
        lines.append("=" * 50)
        
        return "\n".join(lines)


# ============================================================================
# Reasoning Effort Control (#21)
# ============================================================================

@dataclass
class ReasoningConfig:
    """Configuration for reasoning effort."""
    effort: str = "medium"  # low, medium, high
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


REASONING_PRESETS = {
    "low": ReasoningConfig(
        effort="low",
        max_tokens=1024,
        temperature=0.3,
        top_p=0.9,
    ),
    "medium": ReasoningConfig(
        effort="medium",
        max_tokens=4096,
        temperature=0.7,
        top_p=1.0,
    ),
    "high": ReasoningConfig(
        effort="high",
        max_tokens=8192,
        temperature=0.8,
        top_p=0.95,
    ),
    "creative": ReasoningConfig(
        effort="high",
        max_tokens=4096,
        temperature=1.0,
        top_p=0.95,
        frequency_penalty=0.3,
        presence_penalty=0.3,
    ),
    "precise": ReasoningConfig(
        effort="high",
        max_tokens=4096,
        temperature=0.1,
        top_p=0.8,
    ),
}


class ReasoningController:
    """
    Controls reasoning effort.
    
    From Codex's reasoning effort control:
    - Adjust token limits based on task complexity
    - Control temperature for different tasks
    - Manage conversation complexity
    """
    
    def __init__(self):
        self._current_preset = "medium"
        self._config = ReasoningConfig()
    
    def set_effort(self, effort: str) -> ReasoningConfig:
        """Set reasoning effort level."""
        if effort in REASONING_PRESETS:
            self._current_preset = effort
            self._config = REASONING_PRESETS[effort]
        return self._config
    
    def get_config(self) -> ReasoningConfig:
        """Get current reasoning config."""
        return self._config
    
    def auto_adjust(self, task_type: str) -> ReasoningConfig:
        """Auto-adjust reasoning based on task type."""
        adjustments = {
            "simple_edit": "low",
            "complex_feature": "high",
            "refactor": "medium",
            "research": "high",
            "quick_fix": "low",
            "architecture": "high",
            "documentation": "medium",
            "testing": "medium",
        }
        
        effort = adjustments.get(task_type, "medium")
        return self.set_effort(effort)
    
    def get_for_model(self, model: str) -> dict:
        """Get parameters optimized for a specific model."""
        base = {
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
            "max_tokens": self._config.max_tokens,
        }
        
        # Model-specific adjustments
        if "nemotron" in model.lower():
            base["temperature"] = min(base["temperature"], 0.7)
        elif "deepseek" in model.lower():
            base["temperature"] = min(base["temperature"], 0.6)
        elif "qwen" in model.lower():
            base["temperature"] = min(base["temperature"], 0.7)
        
        return base
