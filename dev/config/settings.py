"""
Configuration system for Dev.

Handles:
- Project-level config (.dev/config.yaml)
- User-level config (~/.dev/config.yaml)
- Environment variables
- Defaults
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ProviderConfig:
    """LLM provider configuration."""
    type: str = "nvidia_nims"  # nvidia_nims
    base_url: str = "https://integrate.api.nvidia.com/v1"
    api_keys: list[str] = field(default_factory=list)
    model: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    coding_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    reasoning_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    fast_model: str = "nvidia/llama-3.1-8b-instruct"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class AgentConfig:
    """Agent behavior configuration."""
    max_steps: int = 50
    max_reflections: int = 3
    auto_lint: bool = True
    auto_test: bool = False
    auto_commit: bool = True
    verbose: bool = False


@dataclass
class SandboxSettings:
    """Sandbox configuration."""
    enabled: bool = True
    mode: str = "default"  # default, strict, permissive, none
    read_only: bool = False


@dataclass
class ContextConfig:
    """Context management configuration."""
    max_tokens: int = 100_000
    use_repo_map: bool = True
    repo_map_tokens: int = 1024
    auto_prune: bool = True


@dataclass
class DevConfig:
    """Main configuration."""
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    sandbox: SandboxSettings = field(default_factory=SandboxSettings)
    context: ContextConfig = field(default_factory=ContextConfig)
    project_path: str = "."
    
    @classmethod
    def load(cls, project_path: str = ".") -> "DevConfig":
        """Load configuration from files and environment."""
        config = cls(project_path=os.path.abspath(project_path))
        
        # Try to load YAML config
        config_paths = [
            Path(project_path) / ".dev" / "config.yaml",
            Path(project_path) / ".dev" / "config.json",
            Path.home() / ".dev" / "config.yaml",
            Path.home() / ".dev" / "config.json",
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    if config_path.suffix == ".yaml" or config_path.suffix == ".yml":
                        import yaml
                        with open(config_path) as f:
                            data = yaml.safe_load(f)
                    else:
                        import json
                        with open(config_path) as f:
                            data = json.load(f)
                    
                    config._apply_dict(data)
                except Exception:
                    pass
        
        # Override with environment variables
        if os.environ.get("DEV_MODEL"):
            config.provider.model = os.environ["DEV_MODEL"]
        if os.environ.get("DEV_API_KEY"):
            config.provider.api_keys.append(os.environ["DEV_API_KEY"])
        if os.environ.get("DEV_BASE_URL"):
            config.provider.base_url = os.environ["DEV_BASE_URL"]
        if os.environ.get("DEV_MAX_STEPS"):
            try:
                config.agent.max_steps = int(os.environ["DEV_MAX_STEPS"])
            except ValueError:
                pass
        if os.environ.get("DEV_AUTO_LINT"):
            config.agent.auto_lint = os.environ["DEV_AUTO_LINT"].lower() in ("true", "1", "yes")
        if os.environ.get("DEV_AUTO_COMMIT"):
            config.agent.auto_commit = os.environ["DEV_AUTO_COMMIT"].lower() in ("true", "1", "yes")
        if os.environ.get("DEV_SANDBOX_MODE"):
            config.sandbox.mode = os.environ["DEV_SANDBOX_MODE"]
        
        # Validate after loading
        errors = config.validate()
        if errors:
            import sys
            print(f"[dev:config] Config warnings: {'; '.join(errors)}", file=sys.stderr)
        
        return config
    
    def _apply_dict(self, data: dict):
        """Apply a dictionary to the config."""
        if "provider" in data:
            for k, v in data["provider"].items():
                if hasattr(self.provider, k):
                    setattr(self.provider, k, v)
        
        if "agent" in data:
            for k, v in data["agent"].items():
                if hasattr(self.agent, k):
                    setattr(self.agent, k, v)
        
        if "sandbox" in data:
            for k, v in data["sandbox"].items():
                if hasattr(self.sandbox, k):
                    setattr(self.sandbox, k, v)
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of warnings/errors."""
        errors = []
        # Check provider config
        if not self.provider.type:
            errors.append("No provider type configured")
        if not self.provider.base_url:
            errors.append("No base URL configured")
        # Check agent config
        if self.agent.max_steps < 1:
            errors.append(f"Invalid max_steps: {self.agent.max_steps}")
        if self.agent.max_steps > 200:
            errors.append(f"max_steps too high: {self.agent.max_steps} (recommended: 50)")
        # Check sandbox config
        if self.sandbox.mode not in ("none", "docker", "process"):
            errors.append(f"Invalid sandbox mode: {self.sandbox.mode}")
        return errors
    
    def save(self, project_path: str | None = None):
        """Save configuration to file."""
        save_path = Path(project_path or self.project_path) / ".dev" / "config.yaml"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            import yaml
            data = {
                "provider": {
                    "type": self.provider.type,
                    "base_url": self.provider.base_url,
                    "model": self.provider.model,
                },
                "agent": {
                    "max_steps": self.agent.max_steps,
                    "auto_lint": self.agent.auto_lint,
                    "auto_test": self.agent.auto_test,
                    "auto_commit": self.agent.auto_commit,
                },
                "sandbox": {
                    "mode": self.sandbox.mode,
                    "read_only": self.sandbox.read_only,
                },
            }
            
            with open(save_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False)
        except ImportError:
            # Fallback to JSON
            import json
            save_path = save_path.with_suffix(".json")
            data = {
                "provider": {"type": self.provider.type, "model": self.provider.model},
                "agent": {"max_steps": self.agent.max_steps},
            }
            with open(save_path, "w") as f:
                json.dump(data, f, indent=2)
