"""
Budget Management for Dev.

Adapted from Qwen Code's workflow-budget.ts.
Tracks token usage, cost, and enforces limits.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BudgetConfig:
    """Budget configuration."""
    max_tokens_per_session: int = 100_000
    max_tokens_per_request: int = 8_000
    max_cost_per_session: float = 0.0  # 0 = unlimited (free tier)
    max_requests_per_minute: int = 100
    max_session_duration_seconds: int = 3600  # 1 hour


@dataclass
class UsageRecord:
    """A single usage record."""
    timestamp: float
    tokens_in: int
    tokens_out: int
    model: str
    cost: float = 0.0


class BudgetManager:
    """
    Tracks and enforces budget limits.
    
    From Qwen Code's workflow-budget.ts.
    """
    
    def __init__(self, config: BudgetConfig | None = None):
        self.config = config or BudgetConfig()
        self._records: list[UsageRecord] = []
        self._session_start = time.time()
        self._requests_this_minute: list[float] = []
    
    def record_usage(
        self,
        tokens_in: int,
        tokens_out: int,
        model: str = "",
        cost: float = 0.0,
    ):
        """Record token usage."""
        record = UsageRecord(
            timestamp=time.time(),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model,
            cost=cost,
        )
        self._records.append(record)
        
        # Clean old rate limit records
        cutoff = time.time() - 60
        self._requests_this_minute = [
            t for t in self._requests_this_minute if t > cutoff
        ]
    
    def check_budget(self) -> dict:
        """
        Check if budget allows another request.
        
        Returns status with available tokens and whether we can proceed.
        """
        total_tokens = sum(r.tokens_in + r.tokens_out for r in self._records)
        total_cost = sum(r.cost for r in self._records)
        session_duration = time.time() - self._session_start
        
        # Check token limit
        tokens_remaining = self.config.max_tokens_per_session - total_tokens
        if tokens_remaining <= 0:
            return {
                "allowed": False,
                "reason": "Token limit exceeded",
                "tokens_used": total_tokens,
                "tokens_limit": self.config.max_tokens_per_session,
            }
        
        # Check cost limit
        if self.config.max_cost_per_session > 0:
            if total_cost >= self.config.max_cost_per_session:
                return {
                    "allowed": False,
                    "reason": "Cost limit exceeded",
                    "cost_used": total_cost,
                    "cost_limit": self.config.max_cost_per_session,
                }
        
        # Check rate limit
        if len(self._requests_this_minute) >= self.config.max_requests_per_minute:
            return {
                "allowed": False,
                "reason": "Rate limit exceeded",
                "requests_this_minute": len(self._requests_this_minute),
                "rate_limit": self.config.max_requests_per_minute,
            }
        
        # Check session duration
        if session_duration >= self.config.max_session_duration_seconds:
            return {
                "allowed": False,
                "reason": "Session duration limit exceeded",
                "duration_seconds": session_duration,
                "duration_limit": self.config.max_session_duration_seconds,
            }
        
        return {
            "allowed": True,
            "tokens_remaining": tokens_remaining,
            "tokens_used": total_tokens,
            "cost_used": total_cost,
            "session_duration": session_duration,
            "requests_this_minute": len(self._requests_this_minute),
        }
    
    def can_afford(self, estimated_tokens: int) -> bool:
        """Check if we can afford an estimated number of tokens."""
        status = self.check_budget()
        if not status["allowed"]:
            return False
        return status.get("tokens_remaining", 0) >= estimated_tokens
    
    def record_request(self):
        """Record a request for rate limiting."""
        self._requests_this_minute.append(time.time())
    
    def get_stats(self) -> dict:
        """Get usage statistics."""
        total_in = sum(r.tokens_in for r in self._records)
        total_out = sum(r.tokens_out for r in self._records)
        total_cost = sum(r.cost for r in self._records)
        
        return {
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_total": total_in + total_out,
            "total_cost": total_cost,
            "request_count": len(self._records),
            "session_duration": time.time() - self._session_start,
            "budget": {
                "max_tokens": self.config.max_tokens_per_session,
                "max_cost": self.config.max_cost_per_session,
                "max_duration": self.config.max_session_duration_seconds,
            },
        }
    
    def reset(self):
        """Reset budget tracking."""
        self._records.clear()
        self._session_start = time.time()
        self._requests_this_minute.clear()
