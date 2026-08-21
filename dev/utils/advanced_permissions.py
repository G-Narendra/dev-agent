"""
Advanced permissions and review system for Dev.

Provides:
- UltraReview: AI-powered code review
- ProjectPurger: Clean up Dev state
- AdvancedPermissions: Fine-grained tool permissions
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PermissionRule:
    """A permission rule."""
    pattern: str
    action: str = "allow"
    reason: str = ""


class AdvancedPermissions:
    """Fine-grained permission management."""

    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self._rules: list[PermissionRule] = []

    def add_rule(self, pattern: str, action: str = "allow", reason: str = ""):
        self._rules.append(PermissionRule(pattern=pattern, action=action, reason=reason))

    def check(self, tool_name: str, args: dict) -> dict:
        for rule in self._rules:
            import fnmatch
            if fnmatch.fnmatch(tool_name, rule.pattern):
                return {"allowed": rule.action == "allow", "reason": rule.reason}
        return {"allowed": True, "reason": "No matching rule"}

    def list_rules(self) -> list[dict]:
        return [{"pattern": r.pattern, "action": r.action, "reason": r.reason} for r in self._rules]


class UltraReview:
    """AI-powered code review using the LLM."""

    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)

    async def review(self, prompt: str, provider: Any, runtime: Any) -> dict:
        """Run a code review using the LLM."""
        try:
            # Get git diff for context
            import subprocess
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, cwd=self.project_path, timeout=10,
            )
            git_context = result.stdout.strip() if result.returncode == 0 else "No git changes"

            review_prompt = f"""Review the following code changes and provide a detailed analysis.

Git changes:
{git_context}

Review focus: {prompt}

Provide:
1. Security issues found
2. Performance concerns
3. Code quality issues
4. Suggestions for improvement
5. Overall rating (1-10)"""

            result = await runtime.run_agent(
                agent_id="coder",
                prompt=review_prompt,
                project_path=self.project_path,
            )
            output = result.get("output", {})
            return {"review": output.get("content", "No review generated")}
        except Exception as e:
            return {"review": f"Review failed: {e}"}


class ProjectPurger:
    """Remove all Dev state for a project."""

    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)

    def list_removable(self) -> list[dict]:
        """List all removable Dev artifacts."""
        items = []
        dev_dir = os.path.join(self.project_path, ".dev")
        if os.path.isdir(dev_dir):
            for root, dirs, files in os.walk(dev_dir):
                for f in files:
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(fpath, self.project_path)
                    items.append({"path": rel, "size": os.path.getsize(fpath)})
        return items

    def purge(self, dry_run: bool = False) -> dict:
        """Remove Dev artifacts."""
        dev_dir = os.path.join(self.project_path, ".dev")
        if not os.path.isdir(dev_dir):
            return {"removed": 0, "message": "No .dev directory found"}

        items = self.list_removable()
        if dry_run:
            return {"would_remove": len(items), "items": items}

        shutil.rmtree(dev_dir, ignore_errors=True)
        return {"removed": len(items), "message": f"Removed {len(items)} files"}
