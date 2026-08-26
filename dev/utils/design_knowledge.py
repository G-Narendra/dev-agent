"""
Design Knowledge Manager — Loads DESIGN.md and injects design patterns into the agent.

This is the "design brain" of the agent. It:
1. Reads DESIGN.md from the project (or uses the default template)
2. Extracts relevant patterns for the current task
3. Injects them into the system prompt
4. Allows the agent to update DESIGN.md with new patterns it discovers
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional


# Default DESIGN.md location
DEFAULT_DESIGN_MD = Path(__file__).parent.parent / "templates" / "DESIGN.md"
PROJECT_DESIGN_MD = Path("DESIGN.md")


def _read_and_trim(path: Path, max_chars: int = 5000) -> str:
    """Read a file and trim to max chars."""
    try:
        content = path.read_text(encoding="utf-8")
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[... truncated ...]"
        return content
    except Exception:
        return ""


def load_design_knowledge(project_path: str = ".") -> str:
    """
    Load DESIGN.md content for injection into system prompt.
    
    Priority:
    1. Project-level DESIGN.md (if exists)
    2. User-level ~/.dev/DESIGN.md (if exists)
    3. Default template from dev/templates/DESIGN.md
    """
    # 1. Check project-level
    project_design = Path(project_path) / "DESIGN.md"
    if project_design.exists():
        return _read_and_trim(project_design)
    
    # 2. Check user-level
    user_design = Path.home() / ".dev" / "DESIGN.md"
    if user_design.exists():
        return _read_and_trim(user_design)
    
    # 3. Default template
    if DEFAULT_DESIGN_MD.exists():
        return _read_and_trim(DEFAULT_DESIGN_MD)
    
    return ""


def save_design_knowledge(content: str, project_path: str = "."):
    """Save updated DESIGN.md to the project."""
    design_path = Path(project_path) / "DESIGN.md"
    design_path.write_text(content, encoding="utf-8")


def append_learning(learning: str, project_path: str = "."):
    """
    Append a new learning to the Learnings section of DESIGN.md.
    This is called when the agent discovers a new pattern.
    """
    design_path = Path(project_path) / "DESIGN.md"
    
    # If no DESIGN.md exists, create one from template
    if not design_path.exists():
        if DEFAULT_DESIGN_MD.exists():
            import shutil
            shutil.copy(DEFAULT_DESIGN_MD, design_path)
        else:
            design_path.write_text("# DESIGN.md\n\n## Learnings\n\n", encoding="utf-8")
    
    content = design_path.read_text(encoding="utf-8")
    
    # Find the Learnings section
    learnings_marker = "## Learnings"
    if learnings_marker in content:
        # Append before the end of the Learnings section
        marker_pos = content.rfind(learnings_marker)
        # Find the next ## or end of file
        next_section = content.find("\n## ", marker_pos + len(learnings_marker))
        if next_section == -1:
            next_section = len(content)
        
        # Insert the learning
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        learning_entry = f"\n### {date_str}: New Pattern\n{learning}\n\n"
        content = content[:next_section] + learning_entry + content[next_section:]
    else:
        # Add Learnings section at the end
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        content += f"\n\n## Learnings\n\n### {date_str}: New Pattern\n{learning}\n"
    
    design_path.write_text(content, encoding="utf-8")


def get_design_prompt_section(project_path: str = ".") -> str:
    """
    Get a condensed version of DESIGN.md for injection into system prompt.
    Extracts only the most relevant patterns to save tokens.
    """
    full_content = load_design_knowledge(project_path)
    if not full_content:
        return ""
    
    # Extract key sections (token usage rules, anti-patterns, etc.)
    sections = []
    
    # Extract Design Token System
    token_match = re.search(
        r"## 1\. Design Token System.*?(?=## \d|\Z)",
        full_content,
        re.DOTALL,
    )
    if token_match:
        # Just get the token usage rules
        rules_match = re.search(
            r"### Token Usage Rules.*?(?=## |\Z)",
            token_match.group(),
            re.DOTALL,
        )
        if rules_match:
            sections.append(rules_match.group().strip())
    
    # Extract Anti-Patterns
    anti_match = re.search(
        r"## 10\. Anti-Patterns.*?(?=## \d|\Z)",
        full_content,
        re.DOTALL,
    )
    if anti_match:
        sections.append(anti_match.group().strip())
    
    # Extract Color Rules
    color_match = re.search(
        r"### Color Rules.*?(?=## |\Z)",
        full_content,
        re.DOTALL,
    )
    if color_match:
        sections.append(color_match.group().strip())
    
    # Extract Typography Rules
    typo_match = re.search(
        r"### Typography Rules.*?(?=## |\Z)",
        full_content,
        re.DOTALL,
    )
    if typo_match:
        sections.append(typo_match.group().strip())
    
    # Extract Learnings
    learnings_match = re.search(
        r"## Learnings.*?(?=## \d|\Z)",
        full_content,
        re.DOTALL,
    )
    if learnings_match:
        sections.append(learnings_match.group().strip())
    
    if not sections:
        # Fallback: return first 2000 chars
        return full_content[:2000]
    
    result = "## DESIGN KNOWLEDGE (from DESIGN.md)\n\n" + "\n\n".join(sections)
    
    # Truncate to save tokens
    if len(result) > 3000:
        result = result[:3000] + "\n\n[... more patterns in DESIGN.md ...]"
    
    return result
