"""
Project-specific rules loader (.devrules).

Like Cline's .clinerules:
- Define project-specific rules in .devrules files
- Rules are picked up automatically
- Covers coding standards, architecture, deployment, testing
"""
from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class Rule:
    """A single project rule."""
    name: str
    content: str
    priority: str = "medium"  # critical, high, medium, low
    category: str = "general"  # general, security, testing, deployment, style


@dataclass
class RulesConfig:
    """Loaded rules configuration."""
    rules: list = field(default_factory=list)
    global_rules: list = field(default_factory=list)  # From ~/.devrules
    project_rules: list = field(default_factory=list)  # From .devrules in project
    file_rules: dict = field(default_factory=dict)  # Per-file-type rules

    def get_all_rules(self) -> list[Rule]:
        """Get all rules combined, project rules override global."""
        combined = self.global_rules.copy()
        # Project rules override global by name
        global_names = {r.name for r in combined}
        for rule in self.project_rules:
            if rule.name in global_names:
                combined = [r for r in combined if r.name != rule.name]
            combined.append(rule)
        return combined

    def get_rules_for_file(self, filepath: str) -> list[Rule]:
        """Get rules that apply to a specific file."""
        ext = Path(filepath).suffix
        applicable = self.get_all_rules()
        
        # Add file-type specific rules
        if ext in self.file_rules:
            applicable.extend(self.file_rules[ext])
        
        return applicable

    def to_prompt(self, filepath: str = None) -> str:
        """Format rules as a system prompt addition."""
        if filepath:
            rules = self.get_rules_for_file(filepath)
        else:
            rules = self.get_all_rules()
        
        if not rules:
            return ""
        
        lines = ["## Project Rules (MUST FOLLOW)"]
        for rule in sorted(rules, key=lambda r: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r.priority, 2)):
            prefix = "🔴" if rule.priority == "critical" else "🟡" if rule.priority == "high" else "🔵" if rule.priority == "medium" else "⚪"
            lines.append(f"\n{prefix} **{rule.name}** [{rule.category}]")
            lines.append(rule.content)
        
        return "\n".join(lines)


class RulesLoader:
    """Loads and manages project rules from .devrules files."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.config = RulesConfig()

    def load(self) -> RulesConfig:
        """Load all rules from disk."""
        self.config = RulesConfig()
        
        # Load global rules from ~/.devrules
        global_path = os.path.expanduser("~/.devrules")
        if os.path.isfile(global_path):
            self.config.global_rules = self._parse_rules_file(global_path)
        elif os.path.isdir(global_path):
            for f in os.listdir(global_path):
                if f.endswith((".md", ".txt", ".yaml", ".yml")):
                    rules = self._parse_rules_file(os.path.join(global_path, f))
                    self.config.global_rules.extend(rules)
        
        # Load project rules from .devrules
        project_path = os.path.join(self.project_root, ".devrules")
        if os.path.isfile(project_path):
            self.config.project_rules = self._parse_rules_file(project_path)
        elif os.path.isdir(project_path):
            for f in sorted(os.listdir(project_path)):
                if f.endswith((".md", ".txt", ".yaml", ".yml")):
                    rules = self._parse_rules_file(os.path.join(project_path, f))
                    self.config.project_rules.extend(rules)
        
        # Load file-type specific rules from .devrules/types/
        types_dir = os.path.join(self.project_root, ".devrules", "types")
        if os.path.isdir(types_dir):
            for f in os.listdir(types_dir):
                if f.endswith((".md", ".txt")):
                    ext = f.rsplit(".", 1)[0]  # e.g., "py" from "py.md"
                    rules = self._parse_rules_file(os.path.join(types_dir, f))
                    self.config.file_rules[f".{ext}"] = rules
        
        return self.config

    def _parse_rules_file(self, filepath: str) -> list[Rule]:
        """Parse a rules file into Rule objects."""
        rules = []
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return rules
        
        # Parse markdown-style rules (## Rule Name, content, ## Next Rule)
        current_name = None
        current_content = []
        current_priority = "medium"
        current_category = "general"
        
        for line in content.split("\n"):
            if line.startswith("## "):
                # Save previous rule
                if current_name:
                    rules.append(Rule(
                        name=current_name,
                        content="\n".join(current_content).strip(),
                        priority=current_priority,
                        category=current_category,
                    ))
                current_name = line[3:].strip()
                current_content = []
                # Extract priority from name if tagged
                if "[critical]" in current_name.lower():
                    current_priority = "critical"
                    current_name = current_name.replace("[critical]", "").strip()
                elif "[high]" in current_name.lower():
                    current_priority = "high"
                    current_name = current_name.replace("[high]", "").strip()
                elif "[low]" in current_name.lower():
                    current_priority = "low"
                    current_name = current_name.replace("[low]", "").strip()
                # Extract category
                if "[security]" in current_name.lower():
                    current_category = "security"
                    current_name = current_name.replace("[security]", "").strip()
                elif "[testing]" in current_name.lower():
                    current_category = "testing"
                    current_name = current_name.replace("[testing]", "").strip()
                elif "[style]" in current_name.lower():
                    current_category = "style"
                    current_name = current_name.replace("[style]", "").strip()
            else:
                current_content.append(line)
        
        # Don't forget last rule
        if current_name:
            rules.append(Rule(
                name=current_name,
                content="\n".join(current_content).strip(),
                priority=current_priority,
                category=current_category,
            ))
        
        return rules

    def create_default_rules(self):
        """Create a default .devrules file for the project."""
        rules_path = os.path.join(self.project_root, ".devrules")
        if os.path.exists(rules_path):
            return  # Don't overwrite existing
        
        default_content = """# Dev Agent Project Rules
# Edit these rules to customize how Dev works in your project.
# Rules are loaded automatically when Dev starts.

## Code Quality [high]
- Write clean, readable code with meaningful variable names
- Add docstrings to all public functions and classes
- Keep functions under 50 lines when possible

## Testing [high]
- Write tests for all new features
- Ensure all tests pass before marking work complete
- Use descriptive test names that explain what is being tested

## Git [medium]
- Use conventional commits: feat:, fix:, docs:, refactor:, test:
- One logical change per commit
- Never commit directly to main branch

## Security [critical]
- Never commit API keys, passwords, or secrets
- Use environment variables for all sensitive configuration
- Validate all user input
- Use parameterized queries for database access

## Performance [medium]
- Profile before optimizing
- Prefer async I/O for network operations
- Cache expensive computations

## Documentation [medium]
- Update README.md when adding new features
- Document all API endpoints with request/response examples
- Keep CHANGELOG.md up to date
"""
        with open(rules_path, "w", encoding="utf-8") as f:
            f.write(default_content)

    def add_rule(self, name: str, content: str, priority: str = "medium", category: str = "general"):
        """Add a rule to the project .devrules file."""
        rules_path = os.path.join(self.project_root, ".devrules")
        
        tag = ""
        if priority != "medium":
            tag = f" [{priority}]"
        if category != "general":
            tag += f" [{category}]"
        
        rule_text = f"\n## {name}{tag}\n{content}\n"
        
        with open(rules_path, "a", encoding="utf-8") as f:
            f.write(rule_text)
        
        # Reload
        self.load()
