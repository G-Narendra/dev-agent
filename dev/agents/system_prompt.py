"""
System Prompt Builder — extracted from production_loop.py to reduce file size.

Handles:
- Building the full system prompt with all context
- Compressing for Nemotron's limited context
- Loading project rules, gitignore, auto-memory, git context
- Import resolution for rules files
"""

from __future__ import annotations
import os
import re
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .production_loop import ProductionAgentLoop


class SystemPromptMixin:
    """Mixin providing system prompt building, compression, and context loading."""

    def _build_system_prompt(self, base_prompt: str, repo_map: str = "") -> str:
        """Build the full system prompt with all context. Cached to avoid rebuilds."""
        cache_key = f"{base_prompt[:200]}:{repo_map[:200]}:{self._state.fnames and sorted(self._state.fnames)[0]}"
        if hasattr(self, '_system_prompt_cache') and self._system_prompt_cache.get('key') == cache_key:
            return self._system_prompt_cache['value']
        parts = []

        if base_prompt:
            parts.append(base_prompt)
        if repo_map and self.config.use_repo_map:
            parts.append(f"\n\n## Repository Structure\n{repo_map}")
        if self._state.fnames:
            file_list = "\n".join(f"- {f}" for f in sorted(self._state.fnames))
            parts.append(f"\n\n## Files in Chat\n{file_list}")

        rules = self._load_project_rules()
        if rules:
            parts.append(f"\n\n## Project Rules\n{rules}")

        gitignore = self._load_gitignore()
        if gitignore:
            parts.append(f"\n\n## .gitignore (DO NOT write files here)\n{gitignore}")

        try:
            from ..utils.design_knowledge import get_design_prompt_section
            dk = get_design_prompt_section(self.project_path)
            if dk:
                parts.append(f"\n\n{dk}")
        except Exception:
            pass  # Intentional: design_knowledge not available

        memory = self._load_auto_memory()
        if memory:
            parts.append(f"\n\n## Auto Memory\n{memory}")

        git_ctx = self._get_git_context()
        if git_ctx:
            parts.append(f"\n\n## Git Status\n{git_ctx}")

        if self.config.enforce_plan_mode:
            parts.append("\n\n## CURRENT MODE: PLAN (read-only)\nUse only read-only tools.")

        try:
            if not hasattr(self, '_skill_integration'):
                from .skill_integration import SkillIntegration
                self._skill_integration = SkillIntegration(skills_path=os.path.join(self.project_path, "skills"))
            task = ""
            for msg in self._state.done_messages + self._state.cur_messages:
                if msg.role == "user":
                    task = msg.content or ""
                    break
            if task:
                sp = self._skill_integration.build_skill_prompt(task)
                if sp and len(sp) > 400:
                    sp = sp[:400] + "\n[truncated]"
                if sp:
                    parts.append(f"\n\n{sp}")
        except Exception:
            pass  # Intentional: skills folder not available

        parts.append("""

## RULES: use write_file tool, ONE FILE per call. Path must end in extension. No placeholders. No local images. Keep each file <120 lines. Create ALL files from todo list. Install deps last.""")

        parts.append("""
## TOOLS: research->web_search+read_url | code->code_search+read_files | run->run_terminal_command | install->venv ONLY | images->remote URLs | track->write_todos | APIs->free_api | design->visual_review+design_fetch""")

        result = "\n".join(parts)
        result = self._compress_prompt_for_nim(result)

        if not hasattr(self, '_system_prompt_cache'):
            self._system_prompt_cache = {}
        self._system_prompt_cache = {'key': cache_key, 'value': result}
        return result

    def _compress_prompt_for_nim(self, prompt: str) -> str:
        """Compress system prompt to fit Nemotron's limited context."""
        estimated_tokens = len(prompt) // 4
        if estimated_tokens < 1500:
            return prompt
        self._log(f"System prompt: {estimated_tokens:,} tokens — compressing")

        prompt = prompt.replace("\n\n**Rule Precedence:** .devrules overrides DEV.md. When rules conflict, follow the most specific source.", "")

        gi_match = re.search(r'## \.gitignore.*?(?=\n## |$)', prompt, re.DOTALL)
        if gi_match:
            gi_text = gi_match.group(0)
            if len(gi_text) > 300:
                lines = gi_text.split('\n')[:12]
                prompt = prompt.replace(gi_text, '\n'.join(lines))

        mem_match = re.search(r'## Auto Memory.*?(?=\n## |$)', prompt, re.DOTALL)
        if mem_match:
            mem_text = mem_match.group(0)
            if len(mem_text) > 600:
                prompt = prompt.replace(mem_text, mem_text[:500] + '\n[truncated]')

        git_match = re.search(r'## Git Status.*?(?=\n## |$)', prompt, re.DOTALL)
        if git_match:
            git_text = git_match.group(0)
            if len(git_text) > 300:
                prompt = prompt.replace(git_text, git_text[:200] + '\n[truncated]')

        instr_match = re.search(r'## Instructions\n(.*?)(?=\n## |$)', prompt, re.DOTALL)
        if instr_match:
            instr_text = instr_match.group(0)
            if len(instr_text) > 500:
                lines = instr_text.split('\n')[:5]
                prompt = prompt.replace(instr_text, '\n'.join(lines) + '\n[truncated]')

        design_match = re.search(r'## AUTO-LOADED DESIGN.*?(?=\n## |$)', prompt, re.DOTALL)
        if design_match:
            design_text = design_match.group(0)
            if len(design_text) > 800:
                prompt = prompt.replace(design_text, design_text[:600] + '\n[truncated]')

        if len(prompt) > 8000:
            rules_match = re.search(r'## RULES.*', prompt, re.DOTALL)
            if rules_match:
                rules_text = rules_match.group(0)
                prompt = prompt[:6000] + '\n\n' + rules_text[:1500]
            else:
                prompt = prompt[:7500] + '\n[truncated for context budget]'

        new_tokens = len(prompt) // 4
        self._log(f"Compressed: {estimated_tokens:,} -> {new_tokens:,} tokens")
        return prompt

    def _load_gitignore(self) -> str:
        """Load .gitignore patterns."""
        try:
            gi_path = os.path.join(self.project_path, '.gitignore')
            if not os.path.isfile(gi_path):
                return ''
            with open(gi_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            patterns = [l.strip() for l in lines if l.strip() and not l.strip().startswith('#') and not l.strip().startswith('!')]
            if not patterns:
                return ''
            return 'These paths are gitignored — DO NOT create or modify files here:\n' + '\n'.join(f'- {p}' for p in patterns[:30])
        except Exception:
            return ''  # Intentional: gitignore read error

    def _load_project_rules(self) -> str:
        """Load project rules from DEV.md, .devrules, and .dev/ directory."""
        parts = []
        for name in ["DEV.md", "CLAUDE.md", ".dev.md"]:
            path = os.path.join(self.project_path, name)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if "@import" in content:
                        content = self._resolve_imports(content, self.project_path)
                    parts.append(f"## Project Instructions ({name})\n{content}")
                    break
                except Exception:
                    pass  # Intentional: file read error

        rules_dir = os.path.join(self.project_path, ".devrules")
        rules_file = os.path.join(self.project_path, ".devrules.md")
        if os.path.isfile(rules_file):
            try:
                with open(rules_file, "r", encoding="utf-8", errors="replace") as f:
                    parts.append(f.read())
            except Exception:
                pass  # Intentional: file read error
        if os.path.isdir(rules_dir):
            for fname in sorted(os.listdir(rules_dir)):
                if fname.endswith(".md"):
                    try:
                        with open(os.path.join(rules_dir, fname), "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        if "@import" in content:
                            content = self._resolve_imports(content, rules_dir)
                        parts.append(f"### {fname}\n{content}")
                    except Exception:
                        pass  # Intentional: file read error
        return "\n\n".join(parts)

    def _load_auto_memory(self) -> str:
        """Load auto-memory from .dev/memory/auto_memory.md."""
        mem_file = os.path.join(self.project_path, ".dev", "memory", "auto_memory.md")
        if os.path.isfile(mem_file):
            try:
                with open(mem_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if content.strip():
                    return content
            except Exception:
                pass  # Intentional: file read error
        return ""

    def _resolve_imports(self, content: str, base_dir: str, _seen: set | None = None) -> str:
        """Resolve @import directives in rules files."""
        if _seen is None:
            _seen = set()

        def replace_import(match):
            import_path = match.group(1).strip()
            full_path = os.path.normpath(os.path.join(base_dir, import_path))
            if full_path in _seen:
                return f"[circular import: {import_path}]"
            if os.path.isfile(full_path):
                _seen.add(full_path)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        file_content = f.read()
                    return self._resolve_imports(file_content, os.path.dirname(full_path), _seen)
                except Exception:
                    return f"[import failed: {import_path}]"
            return f"[import not found: {import_path}]"

        return re.sub(r'@import\s+\((.+?)\)', replace_import, content)

    def _get_git_context(self) -> str:
        """Get git context for the system prompt."""
        parts = []
        try:
            result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, cwd=self.project_path, timeout=5)
            if result.returncode == 0:
                parts.append(f"Branch: {result.stdout.strip()}")
            result = subprocess.run(["git", "diff", "--cached", "--stat"], capture_output=True, text=True, cwd=self.project_path, timeout=5)
            if result.stdout.strip():
                parts.append(f"Staged changes:\n{result.stdout.strip()}")
            result = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True, cwd=self.project_path, timeout=5)
            if result.stdout.strip():
                untracked = result.stdout.strip().split("\n")[:10]
                parts.append(f"Untracked files: {', '.join(untracked)}")
            result = subprocess.run(["git", "log", "--oneline", "-3"], capture_output=True, text=True, cwd=self.project_path, timeout=5)
            if result.stdout.strip():
                parts.append(f"Recent commits:\n{result.stdout.strip()}")
        except Exception:
            pass  # Not a git repo
        return "\n".join(parts)
