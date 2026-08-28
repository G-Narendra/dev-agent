"""Skill Tool — Load and use skills from the skills/ folder."""
from __future__ import annotations
import os
from typing import Any
from .base import Tool


class SkillTool(Tool):
    """Load and execute a built-in skill to get specialized instructions for a task domain."""
    
    name = "skill"
    description = (
        "Load a skill by name to get its full instructions. Skills provide reusable behaviors "
        "and domain-specific knowledge. The skill is always read fresh from disk."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The name of the skill to load",
            },
        },
        "required": ["name"],
    }
    
    async def execute(self, input_data: dict, state: Any = None, project_path: str = "") -> dict:
        skill_name = input_data.get("name", "").strip()
        if not skill_name:
            return {"error": "No skill name provided"}
        
        # Find the skills directory relative to project root
        dev_root = project_path or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        skills_dir = os.path.join(dev_root, "skills")
        
        # Search for the skill in multiple locations
        skill_content = None
        
        # 1. Direct skill file match: skills/<name>.md
        direct_path = os.path.join(skills_dir, f"{skill_name}.md")
        if os.path.isfile(direct_path):
            with open(direct_path, "r", encoding="utf-8") as f:
                skill_content = f.read()
        
        # 2. Skills catalog match: skills/ECOSYSTEM_CATALOG.md
        if not skill_content:
            catalog_path = os.path.join(skills_dir, "ECOSYSTEM_CATALOG.md")
            if os.path.isfile(catalog_path):
                with open(catalog_path, "r", encoding="utf-8") as f:
                    catalog = f.read()
                # Check if skill name appears in catalog
                if skill_name.lower() in catalog.lower():
                    # Find the relevant section
                    lines = catalog.split("\n")
                    capturing = False
                    section_lines = []
                    for line in lines:
                        if skill_name.lower() in line.lower():
                            capturing = True
                        if capturing:
                            section_lines.append(line)
                            if len(section_lines) > 50:
                                break
                    if section_lines:
                        skill_content = "\n".join(section_lines)
        
        # 3. Role-based search: skills/roles/<name>/skills/*.yaml
        if not skill_content and os.path.isdir(os.path.join(skills_dir, "roles")):
            roles_dir = os.path.join(skills_dir, "roles")
            for role_name in os.listdir(roles_dir):
                if skill_name.lower() in role_name.lower():
                    role_path = os.path.join(roles_dir, role_name)
                    skills_sub = os.path.join(role_path, "skills")
                    if os.path.isdir(skills_sub):
                        # Find .yaml or .md files in this role's skills
                        for fname in sorted(os.listdir(skills_sub)):
                            if fname.endswith((".yaml", ".md", ".txt")):
                                fpath = os.path.join(skills_sub, fname)
                                with open(fpath, "r", encoding="utf-8") as f:
                                    content = f.read()
                                if len(content) > 50:
                                    skill_content = content
                                    break
        
        # 4. Subagent search: skills/subagents/<name>.md
        if not skill_content:
            subagents_dir = os.path.join(skills_dir, "subagents")
            if os.path.isdir(subagents_dir):
                for fname in os.listdir(subagents_dir):
                    if skill_name.lower() in fname.lower() and fname.endswith(".md"):
                        fpath = os.path.join(subagents_dir, fname)
                        with open(fpath, "r", encoding="utf-8") as f:
                            skill_content = f.read()
                        break
        
        if not skill_content:
            # List available skills
            available = []
            if os.path.isdir(skills_dir):
                for fname in os.listdir(skills_dir):
                    if fname.endswith(".md"):
                        available.append(fname.replace(".md", ""))
                roles_dir = os.path.join(skills_dir, "roles")
                if os.path.isdir(roles_dir):
                    for rname in sorted(os.listdir(roles_dir)):
                        # Check if this role has skills
                        skills_sub = os.path.join(roles_dir, rname, "skills")
                        if os.path.isdir(skills_sub):
                            for sfile in os.listdir(skills_sub):
                                if sfile.endswith((".yaml", ".md")):
                                    available.append(f"{rname}/{sfile.replace('.yaml', '').replace('.md', '')}")
            
            return {
                "error": f"Skill not found: {skill_name}",
                "available_skills": available[:50],
            }
        
        return {
            "skill_name": skill_name,
            "instructions": skill_content[:10000],  # Cap at 10K chars
            "source": skills_dir,
        }
__all__ = ["SkillTool"]
