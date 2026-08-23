"""
Analytics — Usage Statistics and Cost Tracking

Tracks token usage, costs, and session statistics.
"""
import os
import json
import time
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UsageStats:
    """Usage statistics for a session."""
    total_tokens_sent: int = 0
    total_tokens_received: int = 0
    total_cost: float = 0.0
    total_requests: int = 0
    total_tool_calls: int = 0
    total_files_created: int = 0
    total_files_edited: int = 0
    session_start: str = ""
    session_end: str = ""
    models_used: list = field(default_factory=list)
    
    def __post_init__(self):
        if not self.session_start:
            self.session_start = datetime.now().isoformat()


class Analytics:
    """
    Track usage analytics and costs.
    
    Features:
    1. Token counting
    2. Cost estimation
    3. Session statistics
    4. Usage history
    """
    
    # Estimated costs per 1K tokens (NIM free tier = $0)
    MODEL_COSTS = {
        "meta/llama-3.1-8b-instruct": {"input": 0.0, "output": 0.0},
        "meta/llama-3.1-70b-instruct": {"input": 0.0, "output": 0.0},
        "nvidia/llama-3.1-nemotron-70b-instruct": {"input": 0.0, "output": 0.0},
    }
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.stats = UsageStats()
        self.history_file = os.path.join(self.project_path, ".dev", "analytics.json")
        self._load_history()
    
    def _load_history(self):
        """Load usage history."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        else:
            self.history = []
    
    def _save_history(self):
        """Save usage history."""
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, 'w') as f:
            json.dump(self.history[-100:], f, indent=2)  # Keep last 100 entries
    
    def record_request(self, model: str, tokens_sent: int, tokens_received: int):
        """Record a single request."""
        self.stats.total_tokens_sent += tokens_sent
        self.stats.total_tokens_received += tokens_received
        self.stats.total_requests += 1
        
        # Calculate cost
        costs = self.MODEL_COSTS.get(model, {"input": 0.0, "output": 0.0})
        cost = (tokens_sent / 1000 * costs["input"]) + (tokens_received / 1000 * costs["output"])
        self.stats.total_cost += cost
        
        # Track models used
        if model not in self.stats.models_used:
            self.stats.models_used.append(model)
    
    def record_tool_call(self):
        """Record a tool call."""
        self.stats.total_tool_calls += 1
    
    def record_file_created(self):
        """Record a file creation."""
        self.stats.total_files_created += 1
    
    def record_file_edited(self):
        """Record a file edit."""
        self.stats.total_files_edited += 1
    
    def end_session(self):
        """End the current session."""
        self.stats.session_end = datetime.now().isoformat()
        
        # Save to history
        self.history.append({
            "session": self.stats.session_start,
            "tokens_sent": self.stats.total_tokens_sent,
            "tokens_received": self.stats.total_tokens_received,
            "cost": self.stats.total_cost,
            "requests": self.stats.total_requests,
            "tool_calls": self.stats.total_tool_calls,
            "files_created": self.stats.total_files_created,
            "files_edited": self.stats.total_files_edited,
            "models": self.stats.models_used,
        })
        
        self._save_history()
    
    def get_summary(self) -> str:
        """Get formatted usage summary."""
        return f"""Usage Summary:
  Tokens sent: {self.stats.total_tokens_sent:,}
  Tokens received: {self.stats.total_tokens_received:,}
  Total tokens: {self.stats.total_tokens_sent + self.stats.total_tokens_received:,}
  Requests: {self.stats.total_requests}
  Tool calls: {self.stats.total_tool_calls}
  Files created: {self.stats.total_files_created}
  Files edited: {self.stats.total_files_edited}
  Cost: ${self.stats.total_cost:.4f}
  Models: {', '.join(self.stats.models_used) or 'None'}"""
    
    def get_history_summary(self) -> str:
        """Get summary of all sessions."""
        if not self.history:
            return "No usage history"
        
        total_tokens = sum(h.get("tokens_sent", 0) + h.get("tokens_received", 0) for h in self.history)
        total_cost = sum(h.get("cost", 0) for h in self.history)
        
        return f"""Usage History ({len(self.history)} sessions):
  Total tokens: {total_tokens:,}
  Total cost: ${total_cost:.4f}"""
