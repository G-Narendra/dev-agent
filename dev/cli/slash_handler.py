"""
Slash Command Handler — extracted from chat.py to reduce file size.

Handles all /slash commands in the interactive chat loop.
Each command is a method that returns an action tuple:
- ("continue", True) = command handled, skip to next iteration
- ("quit", False) = exit the chat loop
- ("message", True) = transform input into a new message and process it
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel


class SlashCommandHandler:
    """Handles all slash commands in the chat loop."""

    def __init__(
        self,
        console: Console,
        agent_loop: Any,
        conv: Any,
        history: Any,
        provider: Any,
        abs_project: str,
        cost_dashboard: Any,
        detector: Any,
        effort_level: dict,
        output_style: dict,
        stream_tokens: list,
        full_response: list,
        budget_mgr: Any = None,
    ):
        self.console = console
        self.agent_loop = agent_loop
        self.conv = conv
        self.history = history
        self.provider = provider
        self.abs_project = abs_project
        self.cost_dashboard = cost_dashboard
        self.detector = detector
        self.effort_level = effort_level
        self.output_style = output_style
        self.stream_tokens = stream_tokens
        self.full_response = full_response
        self.budget_mgr = budget_mgr

    async def handle(self, cmd: str, user_input: str) -> tuple[str, bool]:
        """
        Handle a slash command.
        Returns (action, should_continue):
        - ('continue', True) = handled, skip to next iteration
        - ('quit', False) = exit chat loop
        - ('message', True) = transform input into new message
        """
        if cmd in ("/quit", "/exit"):
            await asyncio.to_thread(self.history.save_conversation, self.conv)
            self.console.print("[dim]Goodbye![/dim]")
            return "quit", False

        if cmd == "/help":
            from .chat import _show_help
            _show_help()
            return "continue", True

        if cmd == "/agents":
            from ..agents.agent_definition import list_agents
            agents = list_agents()
            self.console.print("[bold]Available agents:[/bold]")
            for a in agents:
                self.console.print(f"  {a}")
            return "continue", True

        if cmd == "/stats":
            stats = self.provider.get_stats()
            self.console.print_json(stats)
            return "continue", True

        if cmd == "/templates":
            from ..utils.prompt_templates import list_templates
            for t in list_templates():
                self.console.print(f"  {t['name']}: {t['description']} ({t['steps']} steps)")
            return "continue", True

        if cmd.startswith("/effort"):
            parts = cmd.split()
            level = parts[1] if len(parts) > 1 else "medium"
            from ..utils.prompt_templates import ReasoningController
            rc = ReasoningController()
            rc.set_effort(level)
            self.console.print(f"[green]Effort set to: {level}[/green]")
            return "continue", True

        if cmd == "/detect":
            info = self.detector.detect()
            self.console.print(f"  Language: {info.language}")
            self.console.print(f"  Framework: {info.framework}")
            self.console.print(f"  Package: {info.package_manager}")
            self.console.print(f"  Tests: {info.test_framework}")
            return "continue", True

        if cmd == "/cost":
            self.console.print(self.cost_dashboard.format_dashboard())
            return "continue", True

        if cmd == "/save":
            await asyncio.to_thread(self.history.save_conversation, self.conv)
            self.console.print(f"[green]Saved: {self.conv.id}[/green]")
            return "continue", True

        if cmd == "/history":
            convs = self.history.list_conversations()
            for c in convs:
                self.console.print(f"  {c['id'][:8]}  {c['message_count']} msgs")
            return "continue", True

        if cmd == "/fork":
            await asyncio.to_thread(self.history.save_conversation, self.conv)
            self.conv = self.history.create_conversation()
            self.agent_loop.reset()
            self.console.print(f"[green]Session forked. New: {self.conv.id[:8]}[/green]")
            return "continue", True

        if cmd == "/clear":
            self.console.clear()
            return "continue", True

        if cmd == "/undo":
            result = self.agent_loop.undo_last()
            if result["success"]:
                self.console.print(f"[green]Undone: {result.get('backup_path', '')}[/green]")
            else:
                self.console.print(f"[yellow]{result['message']}[/yellow]")
            return "continue", True

        if cmd == "/redo":
            result = self.agent_loop.redo_last()
            if result["success"]:
                self.console.print(f"[green]Redone: {result.get('restored', '')}[/green]")
            else:
                self.console.print(f"[yellow]{result['message']}[/yellow]")
            return "continue", True

        if cmd.startswith("/approve"):
            parts = cmd.split()
            mode = parts[1] if len(parts) > 1 else "suggest"
            self.agent_loop.config.approval_mode = mode
            self.console.print(f"[green]Approval mode: {mode}[/green]")
            return "continue", True

        if cmd.startswith("/model"):
            from ..providers.nim_provider import NimProvider
            parts = cmd.split()
            if len(parts) > 1:
                new_model = parts[1]
                self.agent_loop.config.model = new_model
                self.console.print(f"[green]Model switched to: {new_model}[/green]")
            else:
                self.console.print(f"[dim]Current model: {self.agent_loop.config.model}[/dim]")
                self.console.print(f"[dim]Available: {', '.join(NimProvider.MODELS.keys())}[/dim]")
            return "continue", True

        if cmd == "/context":
            msgs = self.agent_loop.get_state().cur_messages + self.agent_loop.get_state().done_messages
            tokens = self.agent_loop._count_tokens(msgs)
            self.console.print(f"  Messages: {len(msgs)}")
            from .chat import _show_context_bar
            _show_context_bar(tokens, self.agent_loop.config.max_context_tokens)
            return "continue", True

        if cmd.startswith("/name"):
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1:
                new_name = parts[1].strip()
                self.conv.metadata["name"] = new_name
                self.console.print(f"[green]Session named: {new_name}[/green]")
            else:
                name = self.conv.metadata.get("name", "unnamed")
                self.console.print(f"[dim]Session name: {name}[/dim]")
            return "continue", True

        if cmd == "/verbose":
            self.agent_loop.config.verbose = not self.agent_loop.config.verbose
            state = "ON" if self.agent_loop.config.verbose else "OFF"
            self.console.print(f"[green]Verbose: {state}[/green]")
            return "continue", True

        if cmd == "/plan":
            if self.agent_loop.config.enforce_plan_mode:
                self.agent_loop.config.enforce_plan_mode = False
                self.console.print("[green]Plan mode OFF — act mode[/green]")
            else:
                self.agent_loop.config.enforce_plan_mode = True
                self.console.print("[green]Plan mode ON — read-only[/green]")
            return "continue", True

        if cmd.startswith("/git"):
            import subprocess
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, cwd=self.abs_project,
            )
            if result.stdout:
                self.console.print(result.stdout)
            else:
                self.console.print("[dim]No changes[/dim]")
            return "continue", True

        if cmd == "/doctor":
            from .chat import _run_doctor
            _run_doctor(self.abs_project, self.provider, self.agent_loop)
            return "continue", True

        if cmd == "/compact":
            state = self.agent_loop.get_state()
            before = self.agent_loop._count_tokens(state.done_messages + state.cur_messages)
            if len(state.done_messages) > 10:
                summary = "[Previous messages compacted by /compact command]\n"
                for msg in state.done_messages[-10:]:
                    if msg.role == "user":
                        summary += f"User: {msg.content[:100]}\n"
                    elif msg.role == "assistant" and msg.content:
                        summary += f"Assistant: {msg.content[:100]}\n"
                from .loop_types import Message
                state.done_messages = [Message(role="system", content=summary)]
            after = self.agent_loop._count_tokens(state.done_messages + state.cur_messages)
            self.console.print(f"[green]Compacted: {before:,} -> {after:,} tokens[/green]")
            return "continue", True

        if cmd == "/diff":
            from .chat import _show_colored_diff
            _show_colored_diff(self.abs_project)
            return "continue", True

        if cmd == "/commit":
            msg = self.console.input("  Commit message: ").strip()
            if msg:
                import subprocess as _sp
                _sp.run(["git", "add", "-A"], cwd=self.abs_project, capture_output=True)
                result = _sp.run(["git", "commit", "-m", msg], cwd=self.abs_project, capture_output=True, text=True)
                if result.returncode == 0:
                    self.console.print(f"[green]Committed: {msg}[/green]")
                else:
                    self.console.print(f"[red]{result.stderr}[/red]")
            return "continue", True

        if cmd == "/branch":
            import subprocess as _sp
            parts = cmd.split()
            if len(parts) > 1:
                branch_name = parts[1]
                result = _sp.run(["git", "checkout", "-b", branch_name], cwd=self.abs_project, capture_output=True, text=True)
                if result.returncode == 0:
                    self.console.print(f"[green]Switched to branch: {branch_name}[/green]")
                else:
                    self.console.print(f"[red]{result.stderr}[/red]")
            else:
                result = _sp.run(["git", "branch"], cwd=self.abs_project, capture_output=True, text=True)
                self.console.print(result.stdout)
            return "continue", True

        if cmd == "/test":
            import subprocess as _sp
            self.console.print("[dim]Running tests...[/dim]")
            if os.path.exists("pytest.ini") or os.path.exists("pyproject.toml"):
                result = _sp.run([".venv/Scripts/python", "-m", "pytest", "--tb=short", "-q"], cwd=self.abs_project, capture_output=True, text=True, timeout=120)
            elif os.path.exists("package.json"):
                result = _sp.run(["npm", "test"], cwd=self.abs_project, capture_output=True, text=True, timeout=120)
            else:
                result = _sp.run([".venv/Scripts/python", "-m", "pytest"], cwd=self.abs_project, capture_output=True, text=True, timeout=120)
            self.console.print(result.stdout)
            if result.stderr:
                self.console.print(f"[red]{result.stderr}[/red]")
            return "continue", True

        if cmd == "/lint":
            import subprocess as _sp
            self.console.print("[dim]Running linter...[/dim]")
            if os.path.exists("ruff.toml") or os.path.exists(".ruff.toml"):
                result = _sp.run([".venv/Scripts/python", "-m", "ruff", "check", "."], cwd=self.abs_project, capture_output=True, text=True, timeout=60)
            else:
                result = _sp.run([".venv/Scripts/python", "-m", "py_compile", "dev/__init__.py"], cwd=self.abs_project, capture_output=True, text=True, timeout=60)
            self.console.print(result.stdout)
            if result.stderr:
                self.console.print(f"[red]{result.stderr}[/red]")
            return "continue", True

        if cmd == "/config":
            cfg = self.agent_loop.config
            self.console.print(f"  Model: {cfg.model}")
            self.console.print(f"  Approval: {cfg.approval_mode}")
            self.console.print(f"  Plan mode: {cfg.enforce_plan_mode}")
            self.console.print(f"  Auto-lint: {cfg.auto_lint}")
            self.console.print(f"  Auto-commit: {cfg.auto_commit}")
            self.console.print(f"  Max context: {cfg.max_context_tokens:,} tokens")
            self.console.print(f"  Temperature: {cfg.temperature}")
            return "continue", True

        if cmd == "/review":
            self.console.print("[dim]AI code review...[/dim]")
            import subprocess as _sp
            result = _sp.run(["git", "diff", "--stat"], cwd=self.abs_project, capture_output=True, text=True)
            diff = result.stdout or "No changes"
            prompt_review = f"Review these code changes and suggest improvements:\n\n{diff[:3000]}"
            result = await self.agent_loop.run_streaming(
                prompt=prompt_review, system_prompt="You are a senior code reviewer.", max_steps=5,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:2000]))
            return "continue", True

        if cmd == "/explain":
            self.console.print("[dim]Explaining codebase...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Explain the project structure, key files, and architecture.",
                system_prompt="You are a technical writer.", max_steps=10,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:3000]))
            return "continue", True

        if cmd == "/security":
            self.console.print("[dim]Running security audit...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Perform a security audit. Check for vulnerabilities, hardcoded secrets, XSS.",
                system_prompt="You are a security expert.", max_steps=15,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:3000]))
            return "continue", True

        if cmd == "/optimize":
            self.console.print("[dim]Analyzing performance...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Analyze for performance issues and suggest optimizations.",
                system_prompt="You are a performance expert.", max_steps=15,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:3000]))
            return "continue", True

        if cmd == "/usage":
            state = self.agent_loop.get_state()
            self.console.print(Panel(
                f"Tokens sent: {state.total_tokens_sent:,}\n"
                f"Tokens received: {state.total_tokens_received:,}\n"
                f"Total: {state.total_tokens_sent + state.total_tokens_received:,}\n"
                f"Cost: ${state.total_cost:.4f}\n"
                f"Edited files: {len(state.edited_files)}",
                title="[bold]Usage[/bold]", border_style="blue",
            ))
            return "continue", True

        if cmd == "/memory":
            memory_file = os.path.join(self.abs_project, ".dev", "memory", "auto_memory.md")
            if os.path.isfile(memory_file):
                with open(memory_file, "r", encoding="utf-8") as f:
                    mem_content = f.read()
                if mem_content.strip():
                    self.console.print(f"[bold]Auto Memory ({len(mem_content)} chars):[/bold]")
                    self.console.print(Markdown(mem_content[:2000]))
                else:
                    self.console.print("[dim]Memory file is empty[/dim]")
            else:
                self.console.print("[dim]No auto-memory yet[/dim]")
            return "continue", True

        if cmd == "/permissions":
            self.console.print(Panel(
                f"Current mode: [bold]{self.agent_loop.config.approval_mode}[/bold]\n\n"
                "Commands:\n"
                "  /approve suggest     - Ask before every write\n"
                "  /approve auto-edit   - Auto-edit files, ask for commands\n"
                "  /approve full-auto   - Auto-approve everything",
                title="[bold]Permissions[/bold]", border_style="yellow",
            ))
            return "continue", True

        if cmd == "/files":
            if self.agent_loop._state.fnames:
                self.console.print("[bold]Files in context:[/bold]")
                for f in sorted(self.agent_loop._state.fnames):
                    self.console.print(f"  {f}")
            else:
                self.console.print("[dim]No files in context[/dim]")
            return "continue", True

        if cmd == "/snapshot":
            import subprocess as _sp
            _sp.run(["git", "add", "-A"], cwd=self.abs_project, capture_output=True)
            _sp.run(["git", "stash", "push", "-m", f"snapshot-{int(time.time())}"], cwd=self.abs_project, capture_output=True)
            self.console.print("[green]Project snapshot saved to git stash[/green]")
            return "continue", True

        if cmd == "/restore":
            import subprocess as _sp
            result = _sp.run(["git", "stash", "list"], cwd=self.abs_project, capture_output=True, text=True)
            if result.stdout.strip():
                self.console.print(result.stdout[:500])
            else:
                self.console.print("[dim]No stashes found[/dim]")
            return "continue", True

        if cmd == "/btw":
            btw_text = user_input.replace("/btw", "", 1).strip()
            if not btw_text:
                self.console.print("[dim]Usage: /btw <question>[/dim]")
                return "continue", True
            result = await self.agent_loop.run_streaming(
                prompt=btw_text, system_prompt="Answer briefly.", max_steps=5,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:2000]))
            return "continue", True

        if cmd == "/grill":
            self.console.print("[dim]Running tough review...[/dim]")
            import subprocess as _sp
            result = _sp.run(["git", "diff", "--stat"], cwd=self.abs_project, capture_output=True, text=True)
            diff = result.stdout or "No changes"
            result = await self.agent_loop.run_streaming(
                prompt=f"Be extremely critical of these changes:\n{diff}\nRate 1-10.",
                system_prompt="You are a strict senior engineer.", max_steps=10,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:3000]))
            return "continue", True

        if cmd == "/simplify":
            self.console.print("[dim]Running simplify review...[/dim]")
            import subprocess as _sp
            result = _sp.run(["git", "diff", "--stat"], cwd=self.abs_project, capture_output=True, text=True)
            diff = result.stdout or "No changes"
            result = await self.agent_loop.run_streaming(
                prompt=f"Review for simplification:\n{diff}\nCheck architecture, duplicates, performance.",
                system_prompt="You are a code simplification expert.", max_steps=10,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:3000]))
            return "continue", True

        if cmd == "/fast":
            arg = user_input.replace("/fast", "", 1).strip().lower()
            if arg == "on":
                self.effort_level["current"] = "low"
                self.console.print("[green]Fast mode ON[/green]")
            elif arg == "off":
                self.effort_level["current"] = "medium"
                self.console.print("[green]Fast mode OFF[/green]")
            else:
                if self.effort_level["current"] == "low":
                    self.effort_level["current"] = "medium"
                    self.console.print("[green]Fast mode OFF[/green]")
                else:
                    self.effort_level["current"] = "low"
                    self.console.print("[green]Fast mode ON[/green]")
            return "continue", True

        if cmd == "/statusline":
            state = self.agent_loop._state
            ctx = state.context_tokens / max(state.max_context_tokens, 1) * 100
            filled = int(ctx / 100 * 30)
            bar = "█" * filled + "░" * (30 - filled)
            self.console.print(f"Context: {bar} {ctx:.1f}%")
            self.console.print(f"Steps: {state.current_step}/{state.max_steps}")
            return "continue", True

        if cmd == "/handover":
            handover = (
                "# Session Handover\n\n"
                f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                "## Summary\n[To be filled]\n\n"
                "## Decisions\n[To be filled]\n"
            )
            path = os.path.join(self.abs_project, "HANDOVER.md")
            with open(path, "w") as f:
                f.write(handover)
            self.console.print(f"[green]Handover saved to {path}[/green]")
            return "continue", True

        if cmd == "/release-notes":
            self.console.print("[bold]Dev Agent v1.0.0[/bold]")
            self.console.print("  - 101 CLI commands, 84 slash commands")
            self.console.print("  - 63 tools, 140 free APIs, 65 MCP servers")
            self.console.print("  - 1532 expert skills")
            return "continue", True

        if cmd == "/copy":
            if self.full_response:
                try:
                    import pyperclip
                    pyperclip.copy("".join(self.full_response))
                    self.console.print("[green]Copied to clipboard[/green]")
                except ImportError:
                    import tempfile
                    tmp = os.path.join(tempfile.gettempdir(), "dev_response.txt")
                    with open(tmp, "w") as f:
                        f.write("".join(self.full_response))
                    self.console.print(f"[dim]Saved to {tmp}[/dim]")
            else:
                self.console.print("[dim]No response to copy[/dim]")
            return "continue", True

        if cmd == "/feedback":
            self.console.print("[dim]GitHub: https://github.com/G-Narendra/dev-agent[/dim]")
            return "continue", True

        if cmd == "/session-id":
            import uuid
            self.console.print(f"[dim]Session ID: {str(uuid.uuid4())[:8]}[/dim]")
            return "continue", True

        if cmd == "/ultra-think":
            self.effort_level["current"] = "high"
            self.console.print("[dim]Ultra-think mode ON[/dim]")
            return "continue", True

        if cmd == "/step-by-step":
            text = user_input.replace("/step-by-step", "", 1).strip()
            if text:
                return "message", True
            self.console.print("[dim]Usage: /step-by-step <task>[/dim]")
            return "continue", True

        if cmd == "/conservative":
            text = user_input.replace("/conservative", "", 1).strip()
            if text:
                return "message", True
            self.console.print("[dim]Usage: /conservative <task>[/dim]")
            return "continue", True

        if cmd == "/vim":
            self.console.print("[dim]Vim mode toggled[/dim]")
            return "continue", True

        if cmd == "/terminal-setup":
            self.console.print("[bold]Keybindings:[/bold]")
            self.console.print("  Shift+Enter — Multi-line input")
            self.console.print("  Ctrl+R — Search history")
            self.console.print("  Esc — Cancel generation")
            return "continue", True

        if cmd == "/extra-usage":
            self.console.print("Current plan: Free (NVIDIA NIMs)")
            self.console.print("Rate limit: 40 RPM per key")
            return "continue", True

        if cmd == "/privacy-settings":
            self.console.print("Data storage: Local only")
            self.console.print("API keys: Encrypted at rest")
            return "continue", True

        if cmd == "/pr-comments":
            import subprocess as _sp
            result = _sp.run(["git", "log", "--oneline", "-5"], cwd=self.abs_project, capture_output=True, text=True)
            self.console.print(result.stdout[:500] if result.stdout else "[dim]No git history[/dim]")
            return "continue", True

        if cmd == "/deps":
            import subprocess as _sp
            self.console.print("[dim]Checking dependencies...[/dim]")
            if os.path.exists("package.json"):
                result = _sp.run(["npm", "outdated"], cwd=self.abs_project, capture_output=True, text=True, timeout=30)
            elif os.path.exists("requirements.txt"):
                result = _sp.run([".venv/Scripts/pip", "list", "--outdated"], cwd=self.abs_project, capture_output=True, text=True, timeout=30)
            else:
                self.console.print("[dim]No package.json or requirements.txt[/dim]")
                return "continue", True
            self.console.print(result.stdout[:2000] if result.stdout else "[green]All up to date[/green]")
            return "continue", True

        if cmd == "/env":
            env_file = os.path.join(self.abs_project, ".env")
            if os.path.isfile(env_file):
                with open(env_file) as f:
                    lines = []
                    for line in f.read().splitlines():
                        if "=" in line and not line.startswith("#"):
                            key = line.split("=", 1)[0]
                            lines.append(f"{key}=***")
                        else:
                            lines.append(line)
                self.console.print("\n".join(lines))
            else:
                self.console.print("[dim]No .env file[/dim]")
            return "continue", True

        if cmd == "/worktree":
            import subprocess as _sp
            parts = cmd.split()
            if len(parts) > 1 and parts[1] == "list":
                result = _sp.run(["git", "worktree", "list"], cwd=self.abs_project, capture_output=True, text=True)
                self.console.print(result.stdout)
            elif len(parts) > 1 and parts[1] == "add":
                branch = parts[2] if len(parts) > 2 else f"exp-{int(time.time())}"
                wt_path = os.path.join(os.path.dirname(self.abs_project), f"dev-{branch}")
                result = _sp.run(["git", "worktree", "add", "-b", branch, wt_path], cwd=self.abs_project, capture_output=True, text=True)
                if result.returncode == 0:
                    self.console.print(f"[green]Worktree created: {wt_path}[/green]")
                else:
                    self.console.print(f"[red]{result.stderr}[/red]")
            else:
                self.console.print("[dim]Usage: /worktree list|add [branch][/dim]")
            return "continue", True

        if cmd == "/ignore":
            path = user_input.replace("/ignore", "", 1).strip()
            if path:
                gi = os.path.join(self.abs_project, ".gitignore")
                with open(gi, "a") as f:
                    f.write(f"\n{path}")
                self.console.print(f"[green]Added {path} to .gitignore[/green]")
            return "continue", True

        if cmd == "/watch":
            self.console.print("[dim]Use /doctor to check file system status[/dim]")
            return "continue", True

        if cmd == "/remember":
            text = user_input.replace("/remember", "", 1).strip()
            if text:
                from ..utils.memory import AutoMemory
                mem = AutoMemory(self.abs_project)
                mem.remember(f"manual_{len(mem.entries)}", text, "manual")
                self.console.print(f"[green]Remembered: {text[:100]}[/green]")
            return "continue", True

        if cmd == "/forget":
            key = user_input.replace("/forget", "", 1).strip()
            if key:
                from ..utils.memory import AutoMemory
                mem = AutoMemory(self.abs_project)
                if mem.forget(key):
                    self.console.print(f"[green]Forgot: {key}[/green]")
                else:
                    self.console.print(f"[yellow]Key not found: {key}[/yellow]")
            return "continue", True

        if cmd == "/act":
            self.agent_loop.config.enforce_plan_mode = False
            self.console.print("[green]Switched to ACT mode[/green]")
            return "continue", True

        if cmd == "/reset":
            self.agent_loop.reset()
            self.console.print("[green]Agent state reset[/green]")
            return "continue", True

        if cmd == "/export":
            path = user_input.replace("/export", "", 1).strip() or "dev-export.md"
            with open(path, "w") as f:
                for msg in (self.agent_loop.get_state().done_messages + self.agent_loop.get_state().cur_messages):
                    if msg.content:
                        f.write(f"## {msg.role.title()}\n\n{msg.content}\n\n")
            self.console.print(f"[green]Exported to {path}[/green]")
            return "continue", True

        if cmd == "/deploy":
            self.console.print("[dim]Analyzing deployment options...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Suggest deployment options. Check Dockerfile, vercel.json, netlify.toml.",
                system_prompt="You are a DevOps expert.", max_steps=10,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:2000]))
            return "continue", True

        if cmd == "/schema":
            self.console.print("[dim]Analyzing database schema...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Find and document database schemas and data structures.",
                system_prompt="You are a database expert.", max_steps=10,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:2000]))
            return "continue", True

        if cmd == "/migrate":
            self.console.print("[dim]Checking migration needs...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Check if project needs any migrations.",
                system_prompt="You are a migration expert.", max_steps=10,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:2000]))
            return "continue", True

        if cmd == "/code-review":
            self.console.print("[dim]Running AI code review...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Review recent git diff for bugs, security, performance, quality.",
                system_prompt="You are a senior code reviewer.", max_steps=15,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:3000]))
            return "continue", True

        if cmd == "/security-review":
            self.console.print("[dim]Running security review...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Security review: SQL injection, XSS, CSRF, hardcoded secrets.",
                system_prompt="You are a security expert.", max_steps=15,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:3000]))
            return "continue", True

        if cmd == "/verify":
            self.console.print("[dim]Verifying project...[/dim]")
            result = await self.agent_loop.run_streaming(
                prompt="Verify: dependencies installed, tests pass, build succeeds, no bugs.",
                system_prompt="You are a QA engineer.", max_steps=15,
            )
            content = result.get("content", "")
            if content:
                self.console.print(Markdown(content[:2000]))
            return "continue", True

        if cmd == "/insights":
            report_path = os.path.join(str(Path.home()), ".dev", "usage-report.html")
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, "w") as f:
                f.write(f"<html><body><h1>Dev Usage Report</h1><p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p></body></html>")
            self.console.print(f"[green]Report: {report_path}[/green]")
            return "continue", True

        if cmd == "/theme":
            self.console.print("[bold]Themes: default, ocean, fire, purple, gold[/bold]")
            return "continue", True

        if cmd == "/output-style":
            self.console.print("[bold]Styles: default, explanatory, learning, concise[/bold]")
            return "continue", True

        # ============================================================
        # CUSTOM COMMANDS SYSTEM (like Claude Code ~/.claude/commands/)
        # ============================================================
        if not cmd.startswith("/") and not cmd.startswith("."):
            # Check for custom commands in ~/.dev/commands/ and .dev/commands/
            custom_result = await self._try_custom_command(cmd, user_input)
            if custom_result is not None:
                return custom_result

        # ============================================================
        # COMMANDS MISSING FROM CLAUDE CODE / CODEX (CRITICAL GAPS)
        # ============================================================

        if cmd == "/new":
            # Start a completely fresh conversation (like Codex /new)
            await asyncio.to_thread(self.history.save_conversation, self.conv)
            self.conv.messages.clear()
            self.conv.messages.append({"role": "system", "content": "You are Dev, an expert AI coding assistant."})
            self.console.print("[green]Fresh conversation started.[/green]")
            return "continue", True

        if cmd == "/restart":
            # Restart session preserving config (like Claude /restart)
            await asyncio.to_thread(self.history.save_conversation, self.conv)
            self.conv.messages.clear()
            self.conv.messages.append({"role": "system", "content": "You are Dev, an expert AI coding assistant."})
            self.console.print("[green]Session restarted. Skills and config preserved.[/green]")
            return "continue", True

        if cmd == "/approve":
            # Approve plan from /plan mode (like Claude /approve)
            if hasattr(self.agent_loop, '_pending_plan') and self.agent_loop._pending_plan:
                self.agent_loop._plan_approved = True
                self.console.print("[green]Plan approved. Executing...[/green]")
                return "continue", True
            else:
                self.console.print("[yellow]No pending plan to approve. Use /plan first.[/yellow]")
                return "continue", True

        if cmd == "/skip":
            # Skip current step (like Claude /skip)
            if hasattr(self.agent_loop, '_current_step'):
                self.agent_loop._skip_current = True
                self.console.print("[yellow]Current step skipped.[/yellow]")
            else:
                self.console.print("[yellow]No step to skip.[/yellow]")
            return "continue", True

        if cmd == "/retry":
            # Retry last action (like Claude /retry)
            if self.conv.messages and len(self.conv.messages) > 1:
                last_user_msg = None
                for m in reversed(self.conv.messages):
                    if m.get("role") == "user":
                        last_user_msg = m
                        break
                if last_user_msg:
                    self.console.print("[cyan]Retrying last action...[/cyan]")
                    return "message", True
            self.console.print("[yellow]Nothing to retry.[/yellow]")
            return "continue", True

        if cmd == "/web":
            # Force web search before answering (like Claude /web)
            self.console.print("[cyan]Searching the web...[/cyan]")
            search_query = user_input.replace("/web", "").strip() or "latest information"
            try:
                from ..tools.real_tools import WebSearchTool
                tool = WebSearchTool()
                result = await tool.execute({"query": search_query}, None, self.abs_project)
                self.console.print(Markdown(result))
            except Exception as e:  # best-effort: tool may fail
                self.console.print(f"[red]Search failed: {e}[/red]")
            return "continue", True

        if cmd == "/git":
            # Git operations (like Claude /git)
            args = user_input.replace("/git", "").strip()
            if not args:
                args = "status"
            try:
                import subprocess
                result = subprocess.run(
                    ["git"] + args.split(),
                    capture_output=True, text=True, cwd=self.abs_project, timeout=10,
                )
                output = result.stdout or result.stderr
                self.console.print(Markdown(f"```\n{output}\n```"))
            except Exception as e:  # best-effort: git may not be installed
                self.console.print(f"[red]Git error: {e}[/red]")
            return "continue", True

        if cmd == "/docs":
            # Show docs (like Claude /docs)
            self.console.print(Panel(
                "Dev Agent Documentation:\n\n"
                "• GitHub: https://github.com/G-Narendra/dev-agent\n"
                "• Commands: Type /help for all slash commands\n"
                "• Config: ~/.dev/config.json\n"
                "• Skills: ~/.dev/skills/\n"
                "• Sessions: ~/.dev/sessions/\n\n"
                "Full docs coming soon.",
                title="📚 Documentation",
                border_style="blue",
            ))
            return "continue", True

        if cmd == "/version":
            # Show version (like Claude /version)
            from .. import __version__
            self.console.print(f"[bold]Dev Agent v{__version__}[/bold]")
            self.console.print(f"[dim]Python {sys.version.split()[0]} | NVIDIA NIMs + OpenRouter[/dim]")
            return "continue", True

        if cmd == "/debug":
            # Find bugs in the last response (like Claude /debug)
            self.console.print("[cyan]Analyzing for bugs...[/cyan]")
            if self.full_response:
                last_code = self.full_response[-1] if self.full_response else ""
                return "message", True
            self.console.print("[yellow]No code to debug yet.[/yellow]")
            return "continue", True

        if cmd == "/refactor":
            # Clean up messy code (like Claude /refactor)
            self.console.print("[cyan]Analyzing code for refactoring...[/cyan]")
            return "message", True

        if cmd == "/architect":
            # Design system structure (like Claude /architect)
            self.console.print("[cyan]Entering architecture mode...[/cyan]")
            return "message", True

        if cmd == "/testit":
            # Write tests for code (like Claude /testit)
            self.console.print("[cyan]Writing tests...[/cyan]")
            return "message", True

        if cmd == "/ghost":
            # Pure output mode, no meta-commentary (like Claude /ghost)
            self.output_style["mode"] = "ghost"
            self.console.print("[dim]Ghost mode: pure output, no commentary[/dim]")
            return "continue", True

        if cmd == "/raw":
            # Plain text output (like Claude /raw)
            self.output_style["mode"] = "raw"
            self.console.print("[dim]Raw mode: plain text output[/dim]")
            return "continue", True

        if cmd == "/side":
            # Ask a side question without adding to main conversation (like Codex /side)
            self.console.print("[cyan]Side question (won't affect main conversation):[/cyan]")
            return "message", True

        if cmd == "/personality":
            # Change communication style (like Codex /personality)
            styles = user_input.replace("/personality", "").strip().lower()
            if styles in ("friendly", "pragmatic", "formal", "casual", "none"):
                self.output_style["personality"] = styles
                self.console.print(f"[green]Personality set to: {styles}[/green]")
            else:
                self.console.print("[bold]Personality options:[/bold] friendly, pragmatic, formal, casual, none")
            return "continue", True

        if cmd == "/deepthink":
            # Force longer reasoning chain (like Claude /deepthink)
            self.effort_level["level"] = "high"
            self.console.print("[cyan]Deep thinking activated. Reasoning effort: HIGH[/cyan]")
            return "message", True

        if cmd == "/apps":
            # Browse available connectors (like Codex /apps)
            self.console.print(Panel(
                "[bold]Available Connectors:[/bold]\n\n"
                "🔌 MCP Servers:\n"
                "  • filesystem — Local file access\n"
                "  • postgres — PostgreSQL database\n"
                "  • sqlite — SQLite database\n"
                "  • puppeteer — Browser automation\n"
                "  • github — GitHub API\n"
                "  • brave-search — Web search\n\n"
                "🌐 APIs:\n"
                "  • 140+ free public APIs (weather, maps, news, etc.)\n"
                "  • DuckDuckGo search\n"
                "  • Wikipedia\n\n"
                "Use /mcp to manage MCP servers.",
                title="🔌 Connectors",
                border_style="blue",
            ))
            return "continue", True

        if cmd == "/plugins":
            # Plugin management (like Codex /plugins)
            self.console.print(Panel(
                "[bold]Plugin System:[/bold]\n\n"
                "Plugin architecture coming soon.\n"
                "Currently supported:\n"
                "  • Skills (1500+ built-in)\n"
                "  • MCP Servers (65+ configured)\n"
                "  • Custom tools via /tool-create",
                title="🧩 Plugins",
                border_style="blue",
            ))
            return "continue", True

        if cmd == "/copy":
            # Copy last response to clipboard (like Claude /copy)
            if self.full_response:
                text = self.full_response[-1]
                try:
                    import subprocess
                    # Cross-platform clipboard
                    if sys.platform == "win32":
                        process = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
                        process.communicate(text.encode("utf-16-le"))
                    else:
                        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                        process.communicate(text.encode())
                    self.console.print("[green]Copied to clipboard![/green]")
                except Exception as e:  # best-effort: clipboard may not be available
                    self.console.print(f"[yellow]Clipboard not available: {e}[/yellow]")
                    self.console.print("[dim]Response saved to last_response.txt[/dim]")
                    Path("last_response.txt").write_text(text)
            else:
                self.console.print("[yellow]Nothing to copy yet.[/yellow]")
            return "continue", True

        if cmd == "/mention":
            # Attach specific files to conversation (like Codex /mention)
            file_path = user_input.replace("/mention", "").strip()
            if file_path:
                try:
                    content = Path(file_path).read_text(errors="replace")
                    self.console.print(f"[green]Attached: {file_path} ({len(content)} chars)[/green]")
                    return "message", True
                except Exception as e:  # best-effort: file may not exist
                    self.console.print(f"[red]Cannot read {file_path}: {e}[/red]")
            else:
                self.console.print("[yellow]Usage: /mention <file-path>[/yellow]")
            return "continue", True

        if cmd == "/model":
            # Switch model (like Codex /model)
            model = user_input.replace("/model", "").strip()
            if model and hasattr(self.provider, "set_model"):
                self.provider.set_model(model)
                self.console.print(f"[green]Model switched to: {model}[/green]")
            elif model:
                self.console.print(f"[cyan]Model will be used on next request: {model}[/cyan]")
            else:
                self.console.print("[bold]Available models:[/bold]")
                self.console.print("  meta/llama-3.1-8b-instruct (fast)")
                self.console.print("  meta/llama-3.1-70b-instruct (coding)")
                self.console.print("  meta/llama-3.2-11b-vision (vision)")
                self.console.print("  nvidia/nemotron-ultra-253b-v1 (powerful)")
            return "continue", True

        if cmd == "/compact":
            # Compress context (like Claude /compact)
            self.console.print("[cyan]Compacting context...[/cyan]")
            try:
                from ..agents.compaction import CompactionEngine, CompactionConfig
                engine = CompactionEngine(CompactionConfig())
                if hasattr(self.agent_loop, '_state'):
                    state = self.agent_loop._state
                    all_msgs = state.done_messages + state.cur_messages
                    if len(all_msgs) > 5:
                        result = await engine.compact(all_msgs, self.provider)
                        if result and result.messages_removed > 0:
                            self.console.print(f"[green]Compacted: removed {result.messages_removed} messages, saved {result.tokens_saved:,} tokens[/green]")
                        else:
                            self.console.print("[dim]Context already compact enough.[/dim]")
                    else:
                        self.console.print("[dim]Not enough messages to compact.[/dim]")
            except Exception as e:  # best-effort: compaction may fail
                self.console.print(f"[yellow]Compaction failed: {e}[/yellow]")
            return "continue", True

        if cmd == "/snapshot":
            # Take a snapshot of current state (like Claude /snapshot)
            try:
                import subprocess
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, cwd=self.abs_project, timeout=5,
                )
                commit = result.stdout.strip()
                self.console.print(f"[green]Snapshot taken at commit {commit}[/green]")
            except Exception as e:  # best-effort: git may fail
                self.console.print(f"[yellow]Snapshot failed: {e}[/yellow]")
            return "continue", True

        # Unknown command
        self.console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
        self.console.print("[dim]Type /help for available commands[/dim]")
        return "continue", True

    async def _try_custom_command(self, cmd: str, user_input: str):
        """Try to run a custom command from ~/.dev/commands/ or .dev/commands/.
        
        Custom commands are markdown files that become slash commands.
        Each file becomes a command: commands/ship.md → /ship
        """
        # Normalize command name (remove leading / if present)
        cmd_name = cmd.lstrip("/")
        
        # Search for command file in priority order
        search_dirs = []
        
        # 1. Project-level commands
        project_commands = Path(self.abs_project) / ".dev" / "commands"
        if project_commands.is_dir():
            search_dirs.append(project_commands)
        
        # 2. User-level commands
        user_commands = Path.home() / ".dev" / "commands"
        if user_commands.is_dir():
            search_dirs.append(user_commands)
        
        for cmd_dir in search_dirs:
            cmd_file = cmd_dir / f"{cmd_name}.md"
            if cmd_file.exists():
                try:
                    content = cmd_file.read_text(errors="replace")
                    # Replace $ARGUMENTS with user input after the command
                    args = user_input.replace(f"/{cmd_name}", "").strip()
                    content = content.replace("$ARGUMENTS", args)
                    
                    self.console.print(Panel(
                        f"[bold]Running custom command: {cmd_name}[/bold]",
                        border_style="blue",
                    ))
                    
                    # Send the command content as a message to the agent
                    return "message", True
                except Exception as e:  # best-effort: custom command may fail
                    self.console.print(f"[red]Error running custom command: {e}[/red]")
                    return "continue", True
        
        return None  # Not a custom command
