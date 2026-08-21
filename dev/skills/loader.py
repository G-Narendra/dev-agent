"""
Skills System for Dev.

Adapted from Freebuff's skill system and Qwen Code's skill.ts.
Skills are loadable instruction sets that give the agent
domain-specific knowledge on demand.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Skill:
    """A loadable skill with instructions."""
    name: str
    description: str
    instructions: str
    source: str = ""  # file path or "builtin"
    tags: list[str] = field(default_factory=list)


# Built-in skills
BUILTIN_SKILLS: dict[str, Skill] = {
    "python": Skill(
        name="python",
        description="Python development best practices",
        instructions="""## Python Development

- Use type hints for all function signatures
- Use f-strings for string formatting
- Prefer `pathlib.Path` over `os.path`
- Use `asyncio` for I/O-bound concurrency
- Write docstrings in Google style
- Use `pytest` for testing
- Run `mypy` for type checking
- Use `ruff` for linting

### Project Structure
```
project/
├── src/
│   └── package/
│       ├── __init__.py
│       └── module.py
├── tests/
│   └── test_module.py
├── pyproject.toml
└── README.md
```

### Common Patterns
- Use dataclasses or Pydantic for data models
- Use context managers for resource management
- Use `functools.lru_cache` for memoization
""",
        tags=["python", "backend", "data science"],
    ),
    
    "javascript": Skill(
        name="javascript",
        description="JavaScript/TypeScript development",
        instructions="""## JavaScript/TypeScript Development

- Use TypeScript for type safety
- Use `const` by default, `let` when needed, never `var`
- Use async/await over .then() chains
- Use optional chaining (?.) and nullish coalescing (??)
- Prefer named exports over default exports
- Use ESLint + Prettier for code quality

### Project Structure
```
project/
├── src/
│   ├── index.ts
│   └── utils/
├── package.json
├── tsconfig.json
└── .eslintrc.json
```

### Node.js Best Practices
- Handle errors with try/catch
- Use `process.env` for configuration
- Use `path.join()` for file paths
- Close file handles and connections
""",
        tags=["javascript", "typescript", "frontend", "node"],
    ),
    
    "react": Skill(
        name="react",
        description="React development patterns",
        instructions="""## React Development

### Component Patterns
- Use functional components with hooks
- Keep components small and focused
- Extract reusable logic into custom hooks
- Use React.memo for expensive renders

### State Management
- Use useState for local state
- Use useContext for shared state
- Consider Zustand or Jotai for complex state

### Performance
- Use React.lazy for code splitting
- Memoize expensive computations with useMemo
- Avoid inline function definitions in JSX
- Use key prop correctly in lists

### File Structure
```
src/
├── components/
│   ├── Button/
│   │   ├── Button.tsx
│   │   ├── Button.test.tsx
│   │   └── index.ts
├── hooks/
├── utils/
└── types/
```
""",
        tags=["react", "frontend", "ui"],
    ),
    
    "nextjs": Skill(
        name="nextjs",
        description="Next.js App Router patterns",
        instructions="""## Next.js App Router

### File-Based Routing
- `app/page.tsx` - Home page
- `app/about/page.tsx` - /about
- `app/blog/[slug]/page.tsx` - Dynamic routes

### Data Fetching
- Use `fetch()` in Server Components
- Use `use()` for promise unwrapping
- Cache with `revalidate` option

### Server vs Client Components
- Server Components (default): Fetch data, access DB
- Client Components (`'use client'`): Interactive UI

### Best Practices
- Keep Server Components as default
- Only add 'use client' when needed
- Use Suspense for loading states
- Use `loading.tsx` for route-level loading
""",
        tags=["nextjs", "react", "fullstack", "vercel"],
    ),
    
    "rust": Skill(
        name="rust",
        description="Rust development patterns",
        instructions="""## Rust Development

### Ownership & Borrowing
- Prefer borrowing (&T) over cloning
- Use owned types (String, Vec) at boundaries
- Return errors, don't panic

### Error Handling
- Use `Result<T, E>` for recoverable errors
- Use `anyhow` for applications, `thiserror` for libraries
- Use `?` operator for error propagation

### Project Structure
```
src/
├── lib.rs      # Library root
├── main.rs     # Binary entry
├── error.rs    # Error types
└── utils/      # Utilities
```

### Common Patterns
- Use `serde` for serialization
- Use `tokio` for async runtime
- Use `clap` for CLI argument parsing
- Use `tracing` for logging
""",
        tags=["rust", "systems", "performance"],
    ),
    
    "git": Skill(
        name="git",
        description="Git best practices",
        instructions="""## Git Best Practices

### Commit Messages
- Use imperative mood ("Add feature" not "Added feature")
- Keep subject line under 50 characters
- Add body for complex changes

### Branching
- Use feature branches
- Keep main/master clean
- Delete merged branches

### Common Commands
```bash
git status              # Check status
git diff                # See changes
git add -p              # Stage interactively
git commit -m "msg"     # Commit
git log --oneline       # View history
git stash               # Save uncommitted work
```
""",
        tags=["git", "version-control"],
    ),
    
    "docker": Skill(
        name="docker",
        description="Docker containerization",
        instructions="""## Docker Best Practices

### Dockerfile
- Use multi-stage builds
- Minimize layers
- Use .dockerignore
- Don't run as root

### Docker Compose
- Use volumes for persistence
- Use networks for isolation
- Set health checks

### Security
- Don't store secrets in images
- Use non-root users
- Scan images for vulnerabilities
""",
        tags=["docker", "containers", "devops"],
    ),
}


class SkillLoader:
    """
    Loads and manages skills.
    
    From Freebuff's load-skills.ts and Qwen Code's skill.ts.
    """
    
    def __init__(
        self,
        skills_dir: str | None = None,
        include_home_skills: bool = False,
    ):
        self.skills_dir = skills_dir
        self.include_home_skills = include_home_skills
        self._loaded: dict[str, Skill] = {}
        self._load_builtin()
    
    def _load_builtin(self):
        """Load built-in skills."""
        self._loaded.update(BUILTIN_SKILLS)
    
    def load_from_disk(self) -> int:
        """Load skills from disk directories."""
        count = 0
        
        # Load from project .dev/skills/
        if self.skills_dir and os.path.isdir(self.skills_dir):
            count += self._load_from_dir(self.skills_dir)
        
        # Load from home directory
        if self.include_home_skills:
            home_skills = Path.home() / ".dev" / "skills"
            if home_skills.is_dir():
                count += self._load_from_dir(str(home_skills))
        
        return count
    
    def _load_from_dir(self, dir_path: str) -> int:
        """Load skills from a directory."""
        count = 0
        
        for entry in os.listdir(dir_path):
            entry_path = os.path.join(dir_path, entry)
            
            if os.path.isfile(entry_path) and entry.endswith((".md", ".txt")):
                name = entry.rsplit(".", 1)[0]
                try:
                    with open(entry_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    skill = Skill(
                        name=name,
                        description=f"Custom skill: {name}",
                        instructions=content,
                        source=entry_path,
                    )
                    self._loaded[name] = skill
                    count += 1
                except Exception:
                    pass
        
        return count
    
    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._loaded.get(name)
    
    def list_skills(self) -> list[dict]:
        """List all available skills."""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "tags": skill.tags,
                "source": skill.source,
            }
            for skill in self._loaded.values()
        ]
    
    def search_skills(self, query: str) -> list[Skill]:
        """Search skills by query."""
        query_lower = query.lower()
        results = []
        
        for skill in self._loaded.values():
            if (query_lower in skill.name.lower() or
                query_lower in skill.description.lower() or
                any(query_lower in tag.lower() for tag in skill.tags)):
                results.append(skill)
        
        return results


class SkillTool:
    """
    Tool for loading skills on demand.
    
    From Freebuff's skill tool.
    """
    
    name = "skill"
    description = "Load a skill by name to get domain-specific instructions"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name"},
        },
        "required": ["name"],
    }
    
    def __init__(self, loader: SkillLoader):
        self.loader = loader
    
    @property
    def definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
    
    async def execute(self, input_data: dict, state=None, project_path: str = "") -> dict:
        """Load and return a skill's instructions."""
        skill_name = input_data.get("name", "") if isinstance(input_data, dict) else str(input_data)
        skill = self.loader.get_skill(skill_name)
        
        if not skill:
            results = self.loader.search_skills(skill_name)
            if results:
                skill = results[0]
        
        if not skill:
            return {
                "error": f"Skill not found: {skill_name}",
                "available": [s["name"] for s in self.loader.list_skills()],
            }
        
        return {
            "name": skill.name,
            "description": skill.description,
            "instructions": skill.instructions,
        }
