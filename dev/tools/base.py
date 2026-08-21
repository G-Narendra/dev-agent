"""
Base tool class for Dev.

Adapted from Freebuff's tool pattern:
- Each tool has a name, definition (OpenAI schema), and execute method
- Tools receive state and project context
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Base class for all Dev tools."""
    
    name: str = ""
    description: str = ""
    parameters: dict = None  # type: ignore[assignment]
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Ensure each subclass gets its own parameters dict
        if 'parameters' not in cls.__dict__ or cls.__dict__['parameters'] is None:
            cls.parameters = {}
    
    @property
    def definition(self) -> dict:
        """OpenAI-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {},
            },
        }
    
    @abstractmethod
    async def execute(
        self,
        input_data: dict,
        state: Any,
        project_path: str,
    ) -> Any:
        """Execute the tool with given input."""
        pass
