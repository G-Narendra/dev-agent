"""
Skill Integration — Use Skills Folder for Production-Quality Output

The skills/ folder contains 465+ expert roles and structured playbooks.
This module makes the agent read and follow these skills to produce
production-quality work.

Key features:
1. Auto-detect relevant skills based on task
2. Read skill YAML files for implementation checklists
3. Inject expert role instructions into system prompt
4. Follow the LOOP-ENGINEERING.md protocol
"""
import os
import re
from pathlib import Path
from typing import Optional


class SkillIntegration:
    """
    Integrates the skills folder into the agent's workflow.
    
    When the agent receives a task:
    1. Analyze task to determine project type
    2. Find relevant skills from the ecosystem catalog
    3. Read skill YAML files for implementation checklists
    4. Inject expert instructions into the system prompt
    5. Follow the instructions exactly
    """
    
    def __init__(self, skills_path: str = "skills"):
        self.skills_path = os.path.abspath(skills_path)
        self._catalog_cache = None
        self._role_cache = {}
        # Skill caching: avoid re-reading YAML files
        self._skill_content_cache: dict[str, dict] = {}  # skill_name -> parsed content
        self._skill_load_time: dict[str, float] = {}  # skill_name -> last load time
        # Skill priority: higher priority skills override lower ones
        self._skill_priorities: dict[str, int] = {}  # skill_name -> priority (0-10)
    
    def get_relevant_skills(self, task: str) -> list[dict]:
        """
        Find skills relevant to the task.
        
        Returns list of {role, title, description, path}
        """
        task_lower = task.lower()
        relevant = []
        
        # Map task keywords to roles
        keyword_role_map = {
            # Web development
            "website": ["frontend-engineer", "backend-developer-nodejs", "web-performance-engineer"],
            "portfolio": ["frontend-engineer", "brand-strategist", "copywriter"],
            "web app": ["frontend-engineer", "backend-developer-nodejs", "database-engineer"],
            "react": ["frontend-engineer", "react-nextjs-architecture"],
            "nextjs": ["frontend-engineer", "react-nextjs-architecture", "vercel-engineer"],
            "vue": ["frontend-engineer"],
            "angular": ["frontend-engineer"],
            
            # Backend
            "api": ["api-engineer", "backend-engineer"],
            "server": ["backend-engineer", "backend-developer-nodejs"],
            "database": ["database-engineer", "database-administrator"],
            "auth": ["security-engineer", "backend-engineer"],
            
            # Mobile
            "mobile": ["mobile-developer-react-native", "mobile-developer-flutter"],
            "ios": ["ios-engineer", "mobile-developer-swift"],
            "android": ["android-engineer", "mobile-developer-kotlin"],
            
            # DevOps
            "deploy": ["devops-engineer", "cloud-engineer-aws"],
            "docker": ["docker-expert", "kubernetes-engineer"],
            "ci/cd": ["devops-engineer", "release-engineer"],
            
            # AI/ML
            "ai": ["ai-agents-engineer", "machine-learning-engineer"],
            "llm": ["ai-agents-engineer", "prompt-engineer"],
            "chatbot": ["ai-agents-engineer", "nlp-engineer"],
            
            # Security
            "security": ["security-engineer", "chief-security-officer"],
            
            # Design
            "design": ["frontend-engineer", "brand-strategist"],
            "ui/ux": ["frontend-engineer", "customer-experience-designer"],
            
            # CLI
            "cli": ["cli-ux-designer", "backend-engineer"],
            "tool": ["cli-ux-designer", "sdk-engineer"],
            
            # Startup
            "startup": ["ceo", "cto", "co-founder", "business-strategist"],
            "mvp": ["cto", "frontend-engineer", "backend-engineer"],
        }
        
        # Find matching roles
        matched_roles = set()
        for keyword, roles in keyword_role_map.items():
            if keyword in task_lower:
                matched_roles.update(roles)
        
        # If no specific match, use generic roles
        if not matched_roles:
            matched_roles = {"frontend-engineer", "backend-engineer", "cto"}
        
        # Load role details
        for role in matched_roles:
            role_info = self._load_role_info(role)
            if role_info:
                relevant.append(role_info)
        
        return relevant[:10]  # Limit to 10 roles
    
    def _load_role_info(self, role_name: str) -> Optional[dict]:
        """Load role information from the skills folder."""
        if role_name in self._role_cache:
            return self._role_cache[role_name]
        
        # Check for role directory
        role_dir = os.path.join(self.skills_path, "roles", role_name)
        if os.path.isdir(role_dir):
            # Look for skill YAML files
            skills_dir = os.path.join(role_dir, "skills")
            if os.path.isdir(skills_dir):
                yaml_files = [f for f in os.listdir(skills_dir) if f.endswith(('.yaml', '.yml'))]
                if yaml_files:
                    # Load the first skill file
                    skill_path = os.path.join(skills_dir, yaml_files[0])
                    info = self._parse_skill_yaml(skill_path)
                    if info:
                        info["role"] = role_name
                        info["path"] = skill_path
                        self._role_cache[role_name] = info
                        return info
        
        # Fallback: create info from role name
        info = {
            "role": role_name,
            "title": role_name.replace("-", " ").title(),
            "description": f"Expert role for {role_name}",
            "path": "",
        }
        self._role_cache[role_name] = info
        return info
    
    def _parse_skill_yaml(self, path: str) -> Optional[dict]:
        """Parse a skill YAML file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple YAML parsing (without external dependency)
            info = {}
            
            # Extract name
            m = re.search(r'^name:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
            if m:
                info["title"] = m.group(1)
            
            # Extract description
            m = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE | re.DOTALL)
            if m:
                info["description"] = m.group(1)[:500]
            
            # Extract implementation_checklist
            checklist_match = re.search(r'implementation_checklist:(.+?)(?=\n[a-z]|\Z)', content, re.DOTALL)
            if checklist_match:
                info["checklist"] = checklist_match.group(1).strip()[:2000]
            
            # Extract best_practices
            practices_match = re.search(r'best_practices:(.+?)(?=\n[a-z]|\Z)', content, re.DOTALL)
            if practices_match:
                info["best_practices"] = practices_match.group(1).strip()[:1000]
            
            # Extract anti_patterns
            anti_match = re.search(r'anti_patterns:(.+?)(?=\n[a-z]|\Z)', content, re.DOTALL)
            if anti_match:
                info["anti_patterns"] = anti_match.group(1).strip()[:1000]
            
            return info if info.get("title") else None
        except Exception:
            return None
    
    def build_skill_prompt(self, task: str) -> str:
        """
        Build a system prompt incorporating relevant skills.
        
        Returns a prompt that instructs the agent to follow
        the relevant skill playbooks.
        """
        skills = self.get_relevant_skills(task)
        
        if not skills:
            return ""
        
        parts = [
            "## EXPERT SKILLS ACTIVATED",
            "",
            "You have access to specialized expert roles for this task.",
            "Follow their implementation checklists EXACTLY.",
            "",
        ]
        
        for skill in skills:
            parts.append(f"### /{skill['role']}")
            parts.append(f"**{skill.get('title', skill['role'])}**")
            parts.append(f"{skill.get('description', '')[:200]}")
            
            if skill.get("checklist"):
                parts.append("\n**Implementation Checklist:**")
                parts.append(skill["checklist"][:1000])
            
            if skill.get("best_practices"):
                parts.append("\n**Best Practices:**")
                parts.append(skill["best_practices"][:500])
            
            if skill.get("anti_patterns"):
                parts.append("\n**Anti-Patterns to Avoid:**")
                parts.append(skill["anti_patterns"][:500])
            
            parts.append("")
        
        # Add PROJECT-BUILDER.md instructions
        project_builder = self._read_project_builder()
        if project_builder:
            parts.append("## PROJECT BUILDING PROTOCOL")
            parts.append(project_builder[:3000])
        
        return "\n".join(parts)
    
    def _read_project_builder(self) -> Optional[str]:
        """Read the PROJECT-BUILDER.md file."""
        path = os.path.join(self.skills_path, "PROJECT-BUILDER.md")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        return None
    
    def get_project_type(self, task: str) -> str:
        """Detect project type from task description."""
        task_lower = task.lower()
        
        if any(kw in task_lower for kw in ["website", "web app", "frontend", "portfolio"]):
            return "web"
        elif any(kw in task_lower for kw in ["api", "backend", "server", "database"]):
            return "backend"
        elif any(kw in task_lower for kw in ["cli", "tool", "command line"]):
            return "cli"
        elif any(kw in task_lower for kw in ["mobile", "ios", "android", "app"]):
            return "mobile"
        elif any(kw in task_lower for kw in ["ai", "llm", "ml", "chatbot"]):
            return "ai"
        elif any(kw in task_lower for kw in ["startup", "mvp", "product"]):
            return "startup"
        else:
            return "generic"
    
    def get_phases(self, project_type: str) -> list[str]:
        """Get phases for a project type."""
        phases = {
            "web": ["setup", "server", "frontend", "styling", "testing"],
            "backend": ["schema", "api", "auth", "testing"],
            "cli": ["design", "core", "errors", "docs"],
            "mobile": ["design", "screens", "navigation", "testing"],
            "ai": ["data", "model", "api", "testing"],
            "startup": ["ideation", "planning", "build", "ship"],
            "generic": ["plan", "implement", "test"],
        }
        return phases.get(project_type, phases["generic"])
