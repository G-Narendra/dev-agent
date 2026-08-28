"""
Slash Command Handler — extracted from main.py to reduce file size.
Handles all /slash commands in the chat loop.
"""

from __future__ import annotations
import asyncio
import os
from typing import Any


async def handle_slash_command(
    cmd: str,
    user_input: str,
    console: Any,
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
) -> tuple[str, bool]:
    """
    Handle a slash command.

    Returns (action, should_continue):
    - ('continue', True) = command handled, skip to next iteration
    - ('quit', False) = exit the chat loop
    """
    if cmd == "/help":
        from .main import _show_help
        _show_help()
        return "continue", True

    elif cmd == "/agents":
        from ..agents.agent_definition import list_agents
        agents = list_agents()
        console.print("[bold]Available agents:[/bold]")
        for a in agents:
            console.print(f"  {a}")
        return "continue", True

    elif cmd == "/stats":
        stats = provider.get_stats()
        console.print_json(stats)
        return "continue", True

    elif cmd == "/detect":
        info = detector.detect()
        console.print(f"  Language: {info.language}")
        console.print(f"  Framework: {info.framework}")
        console.print(f"  Package: {info.package_manager}")
        console.print(f"  Tests: {info.test_framework}")
        return "continue", True

    elif cmd == "/cost":
        console.print(cost_dashboard.format_dashboard())
        return "continue", True

    elif cmd == "/save":
        await asyncio.to_thread(history.save_conversation, conv)
        console.print(f"[green]Saved: {conv.id}[/green]")
        return "continue", True

    elif cmd == "/history":
        convs = history.list_conversations()
        for c in convs:
            console.print(f"  {c['id'][:8]}  {c['message_count']} msgs")
        return "continue", True

    elif cmd == "/fork":
        await asyncio.to_thread(history.save_conversation, conv)
        conv = history.create_conversation()
        agent_loop.reset()
        console.print(f"[green]Session forked. New: {conv.id[:8]}[/green]")
        return "continue", True

    elif cmd == "/clear":
        console.clear()
        return "continue", True

    elif cmd == "/undo":
        result = agent_loop.undo_last()
        if result["success"]:
            console.print(f"[green]Undone: {result.get('backup_path', '')}[/green]")
        else:
            console.print(f"[yellow]{result['message']}[/yellow]")
        return "continue", True

    elif cmd == "/redo":
        result = agent_loop.redo_last()
        if result["success"]:
            console.print(f"[green]Redone: {result.get('restored', '')}[/green]")
        else:
            console.print(f"[yellow]{result['message']}[/yellow]")
        return "continue", True

    elif cmd == "/diff":
        from .main import _show_colored_diff
        _show_colored_diff(abs_project)
        return "continue", True

    elif cmd == "/verbose":
        agent_loop.config.verbose = not agent_loop.config.verbose
        state = "ON" if agent_loop.config.verbose else "OFF"
        console.print(f"[green]Verbose: {state}[/green]")
        return "continue", True

    elif cmd == "/plan":
        if agent_loop.config.enforce_plan_mode:
            agent_loop.config.enforce_plan_mode = False
            console.print("[green]Plan mode OFF[/green]")
        else:
            agent_loop.config.enforce_plan_mode = True
            console.print("[green]Plan mode ON[/green]")
        return "continue", True

    elif cmd == "/compact":
        state = agent_loop.get_state()
        before = agent_loop._count_tokens(state.done_messages + state.cur_messages)
        if len(state.done_messages) > 10:
            summary = "[Previous messages compacted]\n"
            for msg in state.done_messages[-10:]:
                if msg.role == "user":
                    summary += f"User: {msg.content[:100]}\n"
                elif msg.role == "assistant" and msg.content:
                    summary += f"Assistant: {msg.content[:100]}\n"
            state.done_messages = [type(msg)(role="system", content=summary)]
        after = agent_loop._count_tokens(state.done_messages + state.cur_messages)
        console.print(f"[green]Compacted: {before:,} -> {after:,} tokens[/green]")
        return "continue", True

    elif cmd == "/model":
        parts = user_input.split()
        if len(parts) > 1:
            agent_loop.config.model = parts[1]
            console.print(f"[green]Model: {parts[1]}[/green]")
        else:
            console.print(f"[dim]Current: {agent_loop.config.model}[/dim]")
        return "continue", True

    elif cmd == "/approve":
        parts = user_input.split()
        mode = parts[1] if len(parts) > 1 else "suggest"
        agent_loop.config.approval_mode = mode
        console.print(f"[green]Approval: {mode}[/green]")
        return "continue", True

    elif cmd == "/config":
        console.print(f"  Model: {agent_loop.config.model}")
        console.print(f"  Approval: {agent_loop.config.approval_mode}")
        console.print(f"  Plan: {agent_loop.config.enforce_plan_mode}")
        console.print(f"  Verbose: {agent_loop.config.verbose}")
        return "continue", True

    elif cmd == "/memory":
        try:
            from dev.utils.memory import AutoMemory
            mem = AutoMemory(abs_project)
            if mem.entries:
                console.print("[bold]Auto Memory:[/bold]")
                for key, entry in list(mem.entries.items())[:20]:
                    console.print(f"  [{entry.category}] {key}: {entry.value[:80]}")
            else:
                console.print("[dim]No memories yet[/dim]")
        except Exception as e:
            console.print(f"[red]Memory error: {e}[/red]")
        return "continue", True

    elif cmd == "/context":
        msgs = agent_loop.get_state().done_messages + agent_loop.get_state().cur_messages
        tokens = agent_loop._count_tokens(msgs)
        console.print(f"  Messages: {len(msgs)}")
        console.print(f"  Tokens: ~{tokens:,}")
        return "continue", True

    elif cmd == "/reset":
        agent_loop.reset()
        console.print("[green]Agent reset[/green]")
        return "continue", True

    elif cmd == "/commit":
        msg = console.input("  Commit message: ").strip()
        if msg:
            import subprocess as _sp
            _sp.run(["git", "add", "-A"], cwd=abs_project, capture_output=True)
            result = _sp.run(["git", "commit", "-m", msg], cwd=abs_project, capture_output=True, text=True)
            if result.returncode == 0:
                console.print("[green]Committed[/green]")
            else:
                console.print(f"[red]{result.stderr}[/red]")
        return "continue", True

    elif cmd == "/act":
        agent_loop.config.enforce_plan_mode = False
        console.print("[green]Switched to ACT mode[/green]")
        return "continue", True

    elif cmd == "/export":
        export_path = user_input[len("/export"):].strip() or "dev-export.md"
        with open(export_path, "w", encoding="utf-8") as f:
            for msg in (agent_loop.get_state().done_messages + agent_loop.get_state().cur_messages):
                if msg.content:
                    f.write(f"## {msg.role.title()}\n\n{msg.content}\n\n")
        console.print(f"[green]Exported to {export_path}[/green]")
        return "continue", True

    elif cmd == "/fast":
        arg = user_input.replace("/fast", "", 1).strip().lower()
        if arg == "on":
            effort_level["current"] = "low"
            console.print("[green]Fast mode ON[/green]")
        elif arg == "off":
            effort_level["current"] = "medium"
            console.print("[green]Fast mode OFF[/green]")
        else:
            if effort_level["current"] == "low":
                effort_level["current"] = "medium"
            else:
                effort_level["current"] = "low"
            console.print(f"[green]Effort: {effort_level['current']}[/green]")
        return "continue", True

    elif cmd == "/act":
        agent_loop.config.enforce_plan_mode = False
        console.print("[green]Switched to ACT mode[/green]")
        return "continue", True

    elif cmd == "/permissions":
        from rich.panel import Panel
        console.print(Panel(
            f"Current: [bold]{agent_loop.config.approval_mode}[/bold]\n\n"
            "Commands:\n"
            "  /approve suggest     - Ask before every write\n"
            "  /approve auto-edit   - Auto-edit files, ask for commands\n"
            "  /approve full-auto   - Auto-approve everything",
            title="Permissions", border_style="yellow",
        ))
        return "continue", True

    elif cmd == "/export":
        export_path = user_input[len("/export"):].strip() or "dev-export.md"
        with open(export_path, "w", encoding="utf-8") as f:
            for msg in (agent_loop.get_state().done_messages + agent_loop.get_state().cur_messages):
                if msg.content:
                    f.write(f"## {msg.role.title()}\n\n{msg.content}\n\n")
        console.print(f"[green]Exported to {export_path}[/green]")
        return "continue", True

    elif cmd == "/release-notes":
        console.print("[bold]Dev Agent v1.0.0[/bold]")
        console.print("Features: 106+ commands, 31 tools, 137 APIs, 57 MCPs, 465+ skills")
        return "continue", True

    elif cmd == "/feedback":
        console.print("[dim]GitHub: https://github.com/G-Narendra/dev-agent[/dim]")
        return "continue", True

    elif cmd == "/session-id":
        import uuid
        console.print(f"[dim]Session: {str(uuid.uuid4())[:8]}[/dim]")
        return "continue", True

    elif cmd == "/snapshot":
        import subprocess as _sp
        _sp.run(["git", "add", "-A"], cwd=abs_project, capture_output=True)
        _sp.run(["git", "stash", "push", "-m", f"snapshot-{int(__import__('time').time())}"], cwd=abs_project, capture_output=True)
        console.print("[green]Snapshot saved[/green]")
        return "continue", True

    elif cmd == "/init":
        dev_dir = os.path.join(abs_project, ".dev")
        os.makedirs(dev_dir, exist_ok=True)
        devmd = os.path.join(abs_project, "DEV.md")
        if not os.path.exists(devmd):
            with open(devmd, "w") as f:
                f.write("# Project Instructions\n\nAdd your project-specific instructions here.\n")
            console.print("[green]Created DEV.md[/green]")
        console.print("[green]Initialized .dev directory[/green]")
        return "continue", True

    elif cmd == "/review":
        import subprocess as _sp
        result = _sp.run(["git", "diff", "--stat"], cwd=abs_project, capture_output=True, text=True)
        diff = result.stdout or "No changes"
        prompt_review = f"Review these code changes and suggest improvements:\n\n{diff[:3000]}"
        result = await agent_loop.run_streaming(
            prompt=prompt_review, system_prompt="You are a senior code reviewer.", max_steps=5,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:2000]))
        return "continue", True

    elif cmd == "/security":
        prompt_sec = "Perform a security audit of this codebase. Check for vulnerabilities, hardcoded secrets, SQL injection, XSS."
        result = await agent_loop.run_streaming(
            prompt=prompt_sec, system_prompt="You are a security expert.", max_steps=15,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:3000]))
        return "continue", True

    elif cmd == "/explain":
        prompt_explain = "Explain the current project structure, key files, and architecture."
        result = await agent_loop.run_streaming(
            prompt=prompt_explain, system_prompt="You are a technical writer.", max_steps=10,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:3000]))
        return "continue", True

    elif cmd == "/optimize":
        prompt_opt = "Analyze the codebase for performance issues and suggest optimizations."
        result = await agent_loop.run_streaming(
            prompt=prompt_opt, system_prompt="You are a performance expert.", max_steps=15,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:3000]))
        return "continue", True

    elif cmd == "/refactor":
        prompt_refactor = "Analyze the codebase for refactoring opportunities. Find code smells and duplication."
        result = await agent_loop.run_streaming(
            prompt=prompt_refactor, system_prompt="You are a refactoring expert.", max_steps=15,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:3000]))
        return "continue", True

    elif cmd == "/document":
        prompt_doc = "Generate comprehensive documentation for this project: README, API docs, inline comments."
        result = await agent_loop.run_streaming(
            prompt=prompt_doc, system_prompt="You are a documentation expert.", max_steps=20,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:3000]))
        return "continue", True

    elif cmd == "/btw":
        btw_text = user_input.replace("/btw", "", 1).strip()
        if not btw_text:
            console.print("[dim]Usage: /btw <question>[/dim]")
            return "continue", True
        result = await agent_loop.run_streaming(
            prompt=btw_text, system_prompt="Answer concisely. Do not modify files.", max_steps=1,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:2000]))
        return "continue", True

    elif cmd == "/grill":
        import subprocess as _sp
        result = _sp.run(["git", "diff", "--stat"], cwd=abs_project, capture_output=True, text=True)
        diff_stat = result.stdout.strip() if result.stdout else "No changes"
        prompt_grill = f"Be extremely critical of these changes:\n{diff_stat}\n\nFind every bug, anti-pattern, security issue. Rate 1-10."
        result = await agent_loop.run_streaming(
            prompt=prompt_grill, system_prompt="You are a strict senior engineer.", max_steps=10,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:3000]))
        return "continue", True

    elif cmd == "/simplify":
        import subprocess as _sp
        result = _sp.run(["git", "diff", "--stat"], cwd=abs_project, capture_output=True, text=True)
        diff_stat = result.stdout.strip() if result.stdout else "No changes"
        prompt_simplify = f"Review for simplification:\n{diff_stat}\n\nCheck: 1) Architecture 2) Duplicates 3) Performance"
        result = await agent_loop.run_streaming(
            prompt=prompt_simplify, system_prompt="You are a code simplification expert.", max_steps=10,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:3000]))
        return "continue", True

    elif cmd == "/usage":
        state = agent_loop.get_state()
        from rich.panel import Panel
        console.print(Panel(
            f"Tokens sent: {state.total_tokens_sent:,}\n"
            f"Tokens received: {state.total_tokens_received:,}\n"
            f"Total: {state.total_tokens_sent + state.total_tokens_received:,}\n"
            f"Cost: ${state.total_cost:.4f}\n"
            f"Edited files: {len(state.edited_files)}",
            title="Usage", border_style="blue",
        ))
        return "continue", True

    elif cmd == "/watch":
        console.print("[dim]File watching: use /doctor to check status[/dim]")
        return "continue", True

    elif cmd == "/remember":
        text = user_input.replace("/remember", "", 1).strip()
        if text:
            from dev.utils.memory import AutoMemory
            mem = AutoMemory(abs_project)
            key = f"manual_{len(mem.entries)}"
            mem.remember(key, text, "manual")
            console.print(f"[green]Remembered: {text[:100]}[/green]")
        return "continue", True

    elif cmd == "/forget":
        key = user_input.replace("/forget", "", 1).strip()
        if key:
            from dev.utils.memory import AutoMemory
            mem = AutoMemory(abs_project)
            if mem.forget(key):
                console.print(f"[green]Forgot: {key}[/green]")
            else:
                console.print(f"[yellow]Key not found: {key}[/yellow]")
        return "continue", True

    elif cmd == "/worktree":
        import subprocess as _sp
        parts = user_input.split()
        if len(parts) > 1 and parts[1] == "list":
            result = _sp.run(["git", "worktree", "list"], cwd=abs_project, capture_output=True, text=True)
            console.print(result.stdout)
        elif len(parts) > 1 and parts[1] == "add":
            branch = parts[2] if len(parts) > 2 else f"experiment-{int(__import__('time').time())}"
            result = _sp.run(["git", "worktree", "add", "-b", branch], cwd=abs_project, capture_output=True, text=True)
            if result.returncode == 0:
                console.print(f"[green]Worktree created: {branch}[/green]")
        else:
            console.print("[dim]Usage: /worktree list|add [branch][/dim]")
        return "continue", True

    elif cmd == "/deps":
        import subprocess as _sp
        if os.path.exists("package.json"):
            result = _sp.run(["npm", "outdated"], cwd=abs_project, capture_output=True, text=True, timeout=30)
            if result.stdout:
                console.print(result.stdout[:2000])
            else:
                console.print("[green]All deps up to date[/green]")
        elif os.path.exists("requirements.txt"):
            result = _sp.run(["pip", "list", "--outdated"], cwd=abs_project, capture_output=True, text=True, timeout=30)
            if result.stdout:
                console.print(result.stdout[:2000])
        else:
            console.print("[dim]No package.json or requirements.txt[/dim]")
        return "continue", True

    elif cmd == "/schema":
        prompt_schema = "Find and document any database schemas, models, or data structures."
        result = await agent_loop.run_streaming(
            prompt=prompt_schema, system_prompt="You are a database expert.", max_steps=10,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:2000]))
        return "continue", True

    elif cmd == "/deploy":
        prompt_deploy = "Analyze this project and suggest deployment options. Check for Dockerfile, vercel.json, etc."
        result = await agent_loop.run_streaming(
            prompt=prompt_deploy, system_prompt="You are a DevOps expert.", max_steps=10,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:2000]))
        return "continue", True

    elif cmd == "/verify":
        prompt_verify = "Verify this project works: deps installed, tests pass, build succeeds."
        result = await agent_loop.run_streaming(
            prompt=prompt_verify, system_prompt="You are a QA engineer.", max_steps=15,
        )
        content = result.get("content", "")
        if content:
            from rich.markdown import Markdown
            console.print(Markdown(content[:2000]))
        return "continue", True

    elif cmd == "/ultra-think":
        console.print("[dim]Ultra-think mode activated[/dim]")
        effort_level["current"] = "high"
        return "continue", True

    elif cmd == "/debug":
        from .main import _run_doctor
        _run_doctor(abs_project, provider, agent_loop.tools)
        return "continue", True

    elif cmd == "/statusline":
        state = agent_loop.get_state()
        ctx_usage = state.context_tokens / max(state.max_context_tokens, 1) * 100
        bar_len = 30
        filled = int(ctx_usage / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        console.print(f"Context: {bar} {ctx_usage:.1f}%")
        return "continue", True

    elif cmd.startswith("/add "):
        file_path = user_input[5:].strip()
        if file_path:
            abs_f = os.path.join(abs_project, file_path)
            if os.path.isfile(abs_f):
                agent_loop._state.fnames.add(file_path)
                agent_loop._state.abs_fnames.add(abs_f)
                console.print(f"[green]Added {file_path}[/green]")
            else:
                console.print(f"[red]File not found: {file_path}[/red]")
        return "continue", True

    elif cmd.startswith("/drop "):
        file_path = user_input[6:].strip()
        if file_path in agent_loop._state.fnames:
            agent_loop._state.fnames.discard(file_path)
            agent_loop._state.abs_fnames.discard(os.path.join(abs_project, file_path))
            console.print(f"[green]Removed {file_path}[/green]")
        return "continue", True

    elif cmd == "/files":
        if agent_loop._state.fnames:
            console.print("[bold]Files in context:[/bold]")
            for f in sorted(agent_loop._state.fnames):
                console.print(f"  {f}")
        else:
            console.print("[dim]No files in context[/dim]")
        return "continue", True

    elif cmd == "/name":
        parts = user_input.split(maxsplit=1)
        if len(parts) > 1:
            conv.metadata["name"] = parts[1].strip()
            console.print(f"[green]Named: {parts[1].strip()}[/green]")
        return "continue", True

    else:
        console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
        console.print("[dim]Type /help for commands[/dim]")
        return "continue", True
