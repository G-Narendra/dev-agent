"""
Model Router — Automatic Model Selection Based on Task Complexity

Routes tasks to the appropriate model based on:
1. Task complexity (simple → 8B, complex → 70B)
2. Token budget (if context is large, use bigger model)
3. Tool calling reliability (8B truncates, 70B doesn't)
4. User preference (can override)

Models available on NVIDIA NIM free tier:
- meta/llama-3.1-8b-instruct: Fast, 128K context, truncates tool args
- meta/llama-3.1-70b-instruct: Slow, 128K context, reliable tool calls
- meta/llama-3.2-11b-vision-instruct: Vision + text, 128K context
- nvidia/llama-3.1-nemotron-70b-instruct: Best for tool use
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelSelection:
    """Selected model for a task."""
    model: str
    reason: str
    max_tokens: int = 4096
    temperature: float = 0.3


class ModelRouter:
    """
    Automatically selects the best model for each task.
    
    Decision tree:
    1. If task involves file creation/editing → 70B (reliable tool calls)
    2. If task is simple Q&A → 8B (fast)
    3. If task involves vision/screenshots → 11B Vision
    4. If context is large → 70B (handles long context better)
    5. If user specifies model → use that model
    """
    
    # Model configurations
    MODELS = {
        'fast': {
            'name': 'meta/llama-3.1-8b-instruct',
            'max_tokens': 4096,
            'temperature': 0.3,
            'description': 'Fast responses, 128K context',
        },
        'smart': {
            'name': 'meta/llama-3.1-70b-instruct',
            'max_tokens': 4096,
            'temperature': 0.3,
            'description': 'Best quality, reliable tool calls',
        },
        'vision': {
            'name': 'meta/llama-3.2-11b-vision-instruct',
            'max_tokens': 4096,
            'temperature': 0.3,
            'description': 'Vision + text, 128K context',
        },
        'tool': {
            'name': 'nvidia/llama-3.1-nemotron-70b-instruct',
            'max_tokens': 4096,
            'temperature': 0.3,
            'description': 'Best for tool use and function calling',
        },
    }
    
    # Keywords that indicate task complexity
    COMPLEX_KEYWORDS = {
        'create', 'build', 'implement', 'refactor', 'migrate', 'deploy',
        'test', 'debug', 'fix', 'optimize', 'rewrite', 'design',
        'architecture', 'database', 'api', 'frontend', 'backend',
        'authentication', 'authorization', 'security', 'performance',
        'multi-file', 'project', 'application', 'website', 'portfolio',
    }
    
    SIMPLE_KEYWORDS = {
        'explain', 'what', 'how', 'why', 'show', 'read', 'describe',
        'list', 'find', 'search', 'grep', 'cat', 'head', 'tail',
    }
    
    def __init__(self, default_model: str = 'fast', 
                 force_model: str = None,
                 available_keys: int = 1):
        """
        Args:
            default_model: Default model tier ('fast', 'smart', 'vision', 'tool')
            force_model: Force a specific model (overrides routing)
            available_keys: Number of API keys (affects rate limit)
        """
        self.default_model = default_model
        self.force_model = force_model
        self.available_keys = available_keys
        self._call_count = 0
    
    def route(self, task: str, context_tokens: int = 0,
              has_tool_calls: bool = True,
              needs_vision: bool = False) -> ModelSelection:
        """
        Route a task to the appropriate model.
        
        Args:
            task: Task description
            context_tokens: Estimated context token count
            has_tool_calls: Whether the task requires tool calls
            needs_vision: Whether the task needs vision capabilities
            
        Returns:
            ModelSelection with model name and configuration
        """
        # If user forced a specific model, use it
        if self.force_model:
            model_config = self.MODELS.get(self.force_model, self.MODELS['fast'])
            return ModelSelection(
                model=model_config['name'],
                reason=f"User forced model: {self.force_model}",
                max_tokens=model_config['max_tokens'],
                temperature=model_config['temperature'],
            )
        
        # Vision tasks
        if needs_vision:
            config = self.MODELS['vision']
            return ModelSelection(
                model=config['name'],
                reason="Task requires vision capabilities",
                max_tokens=config['max_tokens'],
                temperature=config['temperature'],
            )
        
        # Analyze task complexity
        complexity = self._analyze_complexity(task)
        
        # Route based on complexity
        if complexity >= 0.7:
            # Complex task → use smart model
            config = self.MODELS['smart']
            return ModelSelection(
                model=config['name'],
                reason=f"Complex task (score: {complexity:.2f})",
                max_tokens=config['max_tokens'],
                temperature=config['temperature'],
            )
        elif complexity >= 0.4 and has_tool_calls:
            # Medium complexity with tools → use smart model (8B truncates)
            config = self.MODELS['smart']
            return ModelSelection(
                model=config['name'],
                reason=f"Medium complexity with tools (score: {complexity:.2f})",
                max_tokens=config['max_tokens'],
                temperature=config['temperature'],
            )
        elif context_tokens > 50000:
            # Large context → use smart model
            config = self.MODELS['smart']
            return ModelSelection(
                model=config['name'],
                reason=f"Large context ({context_tokens:,} tokens)",
                max_tokens=config['max_tokens'],
                temperature=config['temperature'],
            )
        else:
            # Simple task → use fast model
            config = self.MODELS['fast']
            return ModelSelection(
                model=config['name'],
                reason=f"Simple task (score: {complexity:.2f})",
                max_tokens=config['max_tokens'],
                temperature=config['temperature'],
            )
    
    def _analyze_complexity(self, task: str) -> float:
        """
        Analyze task complexity on a 0-1 scale.
        
        Returns:
            Float between 0 (simple) and 1 (complex)
        """
        task_lower = task.lower()
        words = set(task_lower.split())
        
        # Count complexity indicators
        complex_matches = len(words & self.COMPLEX_KEYWORDS)
        simple_matches = len(words & self.SIMPLE_KEYWORDS)
        
        # Check for multi-file indicators
        multi_file_indicators = [
            'project', 'application', 'website', 'portfolio',
            'multiple files', 'all files', 'entire', 'complete',
            'full stack', 'frontend', 'backend', 'database',
        ]
        multi_file_score = sum(1 for indicator in multi_file_indicators 
                              if indicator in task_lower)
        
        # Check for specific file types
        file_indicators = [
            'css', 'html', 'javascript', 'python', 'typescript',
            'react', 'vue', 'angular', 'express', 'django',
            'database', 'sql', 'migration', 'schema',
        ]
        file_score = sum(1 for indicator in file_indicators 
                        if indicator in task_lower)
        
        # Calculate complexity score
        score = 0.0
        score += complex_matches * 0.15
        score -= simple_matches * 0.1
        score += multi_file_score * 0.2
        score += file_score * 0.1
        
        # Length-based complexity (longer = more complex)
        word_count = len(task.split())
        if word_count > 50:
            score += 0.2
        elif word_count > 20:
            score += 0.1
        
        # Clamp to 0-1
        return max(0.0, min(1.0, score))
    
    def should_retry_with_bigger_model(self, error: str, 
                                       current_model: str) -> Optional[str]:
        """
        Check if we should retry with a bigger model after an error.
        
        Returns model name to retry with, or None.
        """
        # If already using the biggest model, can't upgrade
        if current_model == self.MODELS['smart']['name']:
            return None
        
        # Check for errors that suggest model capability issues
        retry_indicators = [
            'truncated',
            'tool_calls',
            'single tool-calls',
            'context length',
            'max_tokens',
            'incomplete',
        ]
        
        error_lower = error.lower()
        if any(indicator in error_lower for indicator in retry_indicators):
            return self.MODELS['smart']['name']
        
        return None
    
    def get_model_for_step(self, step: int, total_steps: int,
                           step_type: str = "general") -> ModelSelection:
        """
        Get model for a specific step in a multi-step task.
        
        Early steps (planning) → smart model
        Middle steps (execution) → fast model (for speed)
        Late steps (verification) → smart model
        """
        progress = step / max(total_steps, 1)
        
        if step_type == "planning":
            config = self.MODELS['smart']
            return ModelSelection(
                model=config['name'],
                reason="Planning step",
            )
        elif step_type == "verification":
            config = self.MODELS['smart']
            return ModelSelection(
                model=config['name'],
                reason="Verification step",
            )
        elif progress < 0.2 or progress > 0.8:
            # Start/end → use smart model
            config = self.MODELS['smart']
            return ModelSelection(
                model=config['name'],
                reason=f"Step {step}/{total_steps} (early/late phase)",
            )
        else:
            # Middle → use fast model for speed
            config = self.MODELS['fast']
            return ModelSelection(
                model=config['name'],
                reason=f"Step {step}/{total_steps} (execution phase)",
            )
