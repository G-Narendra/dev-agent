"""
Prompt Templates — Save and Load Reusable Prompts

Provides prompt template management.
"""
import os
import json
from typing import Optional
from dataclasses import dataclass


@dataclass
class PromptTemplate:
    """A saved prompt template."""
    name: str
    template: str
    description: str = ""
    variables: list = None
    
    def __post_init__(self):
        if self.variables is None:
            self.variables = []


class TemplateManager:
    """
    Manage prompt templates.
    
    Usage:
        manager = TemplateManager(project_path=".")
        
        # Save a template
        manager.save("build-api", "Create a REST API with {framework}", 
                     variables=["framework"])
        
        # Load a template
        template = manager.load("build-api")
        
        # Render a template
        prompt = manager.render("build-api", framework="Express")
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.templates_dir = os.path.join(self.project_path, ".dev", "templates")
        os.makedirs(self.templates_dir, exist_ok=True)
    
    def save(self, name: str, template: str, description: str = "",
             variables: list = None):
        """Save a prompt template."""
        path = os.path.join(self.templates_dir, f"{name}.json")
        data = {
            "name": name,
            "template": template,
            "description": description,
            "variables": variables or [],
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self, name: str) -> Optional[PromptTemplate]:
        """Load a prompt template."""
        path = os.path.join(self.templates_dir, f"{name}.json")
        if not os.path.exists(path):
            return None
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        return PromptTemplate(**data)
    
    def render(self, name: str, **kwargs) -> Optional[str]:
        """Render a template with variables."""
        template = self.load(name)
        if not template:
            return None
        
        result = template.template
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        
        return result
    
    def list_templates(self) -> list[dict]:
        """List all templates."""
        templates = []
        for fname in os.listdir(self.templates_dir):
            if fname.endswith('.json'):
                try:
                    path = os.path.join(self.templates_dir, fname)
                    with open(path, 'r') as f:
                        data = json.load(f)
                    templates.append({
                        "name": data.get("name", fname[:-5]),
                        "description": data.get("description", ""),
                        "variables": data.get("variables", []),
                    })
                except Exception:
                    pass
        return templates
    
    def delete(self, name: str) -> bool:
        """Delete a template."""
        path = os.path.join(self.templates_dir, f"{name}.json")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False


# ============================================================================
# Module-level helpers (used by __init__.py)
# ============================================================================

# Built-in templates shipped with Dev
BUILTIN_TEMPLATES = [
    {
        "name": "full-stack-app",
        "description": "Build a full-stack web application",
        "steps": [
            "1. Initialize project structure",
            "2. Set up backend (Express/FastAPI)",
            "3. Create database schema",
            "4. Build API endpoints",
            "5. Create frontend (React/Next.js)",
            "6. Add authentication",
            "7. Write tests",
            "8. Deploy",
        ],
    },
    {
        "name": "bug-fix",
        "description": "Fix a bug in existing code",
        "steps": [
            "1. Reproduce the bug",
            "2. Identify root cause",
            "3. Implement fix",
            "4. Add regression test",
        ],
    },
    {
        "name": "api-design",
        "description": "Design and implement a REST API",
        "steps": [
            "1. Define API spec",
            "2. Set up routing",
            "3. Implement handlers",
            "4. Add validation",
            "5. Write tests",
        ],
    },
    {
        "name": "refactor",
        "description": "Refactor existing code for better quality",
        "steps": [
            "1. Analyze existing code",
            "2. Identify code smells",
            "3. Plan refactoring steps",
            "4. Apply changes incrementally",
            "5. Verify tests pass",
        ],
    },
    {
        "name": "startup-mvp",
        "description": "Build a minimum viable product for a startup",
        "steps": [
            "1. Define core features",
            "2. Set up project",
            "3. Build MVP frontend",
            "4. Build MVP backend",
            "5. Add payment integration",
            "6. Deploy to production",
        ],
    },
    {
        "name": "cli-tool",
        "description": "Build a command-line tool",
        "steps": [
            "1. Design CLI interface",
            "2. Implement core logic",
            "3. Add argument parsing",
            "4. Add error handling",
            "5. Write tests",
            "6. Add documentation",
        ],
    },
    {
        "name": "mobile-app",
        "description": "Build a mobile application",
        "steps": [
            "1. Choose framework (React Native/Flutter)",
            "2. Design UI",
            "3. Implement navigation",
            "4. Add state management",
            "5. Integrate APIs",
            "6. Test on device",
        ],
    },
]

# Workflow templates (alias for CLI imports)
WORKFLOW_TEMPLATES = BUILTIN_TEMPLATES

_default_manager: Optional[TemplateManager] = None


def get_template(name: str, project_path: str = ".") -> Optional[dict]:
    """Get a prompt template by name (checks built-in first, then user)."""
    # Check built-in templates first
    for t in BUILTIN_TEMPLATES:
        if t["name"] == name:
            return t
    # Fall back to user templates
    global _default_manager
    if _default_manager is None:
        _default_manager = TemplateManager(project_path=project_path)
    pt = _default_manager.load(name)
    if pt:
        return {"name": pt.name, "description": pt.description, "steps": [pt.template]}
    return None


def list_templates(project_path: str = ".") -> list[dict]:
    """List all available prompt templates (built-in + user)."""
    result = [t.copy() for t in BUILTIN_TEMPLATES]
    global _default_manager
    if _default_manager is None:
        _default_manager = TemplateManager(project_path=project_path)
    for t in _default_manager.list_templates():
        if not any(r["name"] == t["name"] for r in result):
            result.append(t)
    return result


class CostDashboard:
    """Display cost and token usage dashboard."""

    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.cost_file = os.path.join(self.project_path, ".dev", "cost.json")
        self._records: list[dict] = []

    def _load(self) -> dict:
        if os.path.exists(self.cost_file):
            with open(self.cost_file) as f:
                return json.load(f)
        return {"total_tokens": 0, "total_cost": 0.0, "sessions": []}

    def _save(self, data: dict):
        os.makedirs(os.path.dirname(self.cost_file), exist_ok=True)
        with open(self.cost_file, "w") as f:
            json.dump(data, f, indent=2)

    def record(self, tokens_in: int, tokens_out: int, model: str = ""):
        """Record token usage (matches test API)."""
        self._records.append({
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "model": model,
        })
        # Also persist
        data = self._load()
        data["total_tokens"] += tokens_in + tokens_out
        data["sessions"].append({
            "tokens_sent": tokens_in,
            "tokens_received": tokens_out,
            "model": model,
        })
        self._save(data)

    # Alias
    record_usage = record

    def get_summary(self) -> dict:
        """Get usage summary."""
        tokens_in = sum(r["tokens_in"] for r in self._records)
        tokens_out = sum(r["tokens_out"] for r in self._records)
        return {
            "total_requests": len(self._records),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "cost": 0.0,
        }

    def format_dashboard(self) -> str:
        """Format a dashboard display."""
        summary = self.get_summary()
        lines = [
            "COST DASHBOARD",
            "=" * 40,
            f"Requests: {summary['total_requests']}",
            f"Tokens In: {summary['tokens_in']:,}",
            f"Tokens Out: {summary['tokens_out']:,}",
            f"Total: {summary['total_tokens']:,}",
            f"Cost: $0.00 (free tier)",
        ]
        return "\n".join(lines)

    def display(self) -> str:
        return self.format_dashboard()


class _EffortConfig:
    """Configuration for a reasoning effort level."""
    def __init__(self, effort: str, max_tokens: int, temperature: float):
        self.effort = effort
        self.max_tokens = max_tokens
        self.temperature = temperature


class ReasoningController:
    """Control reasoning effort level (low/medium/high)."""

    def __init__(self, effort: str = "medium"):
        self.effort = effort
        self._efforts = {
            "low": _EffortConfig("low", 512, 0.3),
            "medium": _EffortConfig("medium", 2048, 0.5),
            "high": _EffortConfig("high", 4096, 0.7),
        }

    def set_effort(self, level: str) -> _EffortConfig:
        """Set effort level, returns config."""
        if level in self._efforts:
            self.effort = level
            return self._efforts[level]
        return self._efforts["medium"]

    def auto_adjust(self, task_type: str) -> _EffortConfig:
        """Auto-adjust effort based on task complexity."""
        complex_keywords = [
            "complex", "feature", "refactor", "architect", "design",
            "full", "complete", "startup", "production",
        ]
        simple_keywords = [
            "fix typo", "rename", "format", "lint", "simple",
        ]
        task_lower = task_type.lower()
        if any(kw in task_lower for kw in complex_keywords):
            self.effort = "high"
            return self._efforts["high"]
        elif any(kw in task_lower for kw in simple_keywords):
            self.effort = "low"
            return self._efforts["low"]
        else:
            self.effort = "medium"
            return self._efforts["medium"]

    def get_params(self) -> dict:
        cfg = self._efforts.get(self.effort, self._efforts["medium"])
        return {"max_tokens": cfg.max_tokens, "temperature": cfg.temperature}
