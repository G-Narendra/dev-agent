"""
Commands — Slash Command System

Inspired by Aider's commands.py, this module provides interactive
slash commands for the CLI agent.

Commands:
- /add <file> - Add file to chat context
- /drop <file> - Remove file from chat context
- /run <cmd> - Run a shell command
- /undo - Undo last AI edit (via git)
- /redo - Redo last undone edit
- /diff - Show colored diff of changes
- /commit - Commit all changes with AI message
- /web <url> - Scrape webpage and add to context
- /help - Show available commands
- /clear - Clear conversation history
- /compact - Compress conversation history
- /model <name> - Switch model
- /mode <name> - Switch chat mode (ask/code/architect)
- /cost - Show token usage and cost
- /lint - Run linter on project
- /test - Run tests
"""
import os
import subprocess
import json
from typing import Optional


class Commands:
    """Interactive slash commands for the agent."""
    
    def __init__(self, agent=None, project_path: str = "."):
        self.agent = agent
        self.project_path = os.path.abspath(project_path)
        self.chat_files = set()
        self.read_only_files = set()
    
    def handle(self, user_input: str) -> Optional[str]:
        """
        Handle a slash command.
        
        Returns:
            Response string, or None if not a command
        """
        if not user_input.startswith('/'):
            return None
        
        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        commands = {
            '/add': self.cmd_add,
            '/drop': self.cmd_drop,
            '/run': self.cmd_run,
            '/undo': self.cmd_undo,
            '/redo': self.cmd_redo,
            '/diff': self.cmd_diff,
            '/commit': self.cmd_commit,
            '/web': self.cmd_web,
            '/help': self.cmd_help,
            '/clear': self.cmd_clear,
            '/compact': self.cmd_compact,
            '/model': self.cmd_model,
            '/mode': self.cmd_mode,
            '/cost': self.cmd_cost,
            '/lint': self.cmd_lint,
            '/test': self.cmd_test,
            '/files': self.cmd_files,
            '/status': self.cmd_status,
        }
        
        handler = commands.get(cmd)
        if handler:
            return handler(args)
        
        return f"Unknown command: {cmd}. Type /help for available commands."
    
    def cmd_add(self, args: str) -> str:
        """Add file(s) to chat context."""
        if not args:
            return "Usage: /add <file> [file2] [file3]"
        
        added = []
        for pattern in args.split():
            # Expand glob patterns
            import glob
            matches = glob.glob(os.path.join(self.project_path, pattern))
            if matches:
                for f in matches:
                    rel = os.path.relpath(f, self.project_path)
                    self.chat_files.add(rel)
                    added.append(rel)
            else:
                # Try as relative path
                if os.path.exists(os.path.join(self.project_path, pattern)):
                    self.chat_files.add(pattern)
                    added.append(pattern)
                else:
                    return f"File not found: {pattern}"
        
        if added:
            return f"Added to chat: {', '.join(added)}"
        return "No files added"
    
    def cmd_drop(self, args: str) -> str:
        """Remove file(s) from chat context."""
        if not args:
            return "Usage: /drop <file> [file2]"
        
        dropped = []
        for pattern in args.split():
            if pattern in self.chat_files:
                self.chat_files.remove(pattern)
                dropped.append(pattern)
            else:
                return f"File not in chat: {pattern}"
        
        if dropped:
            return f"Dropped from chat: {', '.join(dropped)}"
        return "No files dropped"
    
    def cmd_run(self, args: str) -> str:
        """Run a shell command."""
        if not args:
            return "Usage: /run <command>"
        
        try:
            result = subprocess.run(
                args,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += "\nSTDERR:\n" + result.stderr
            if result.returncode != 0:
                output += f"\nExit code: {result.returncode}"
            
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out after 30 seconds"
        except Exception as e:
            return f"Error running command: {e}"
    
    def cmd_undo(self, args: str) -> str:
        """Undo last AI edit via git."""
        try:
            # Check if there are uncommitted changes
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            
            if status.stdout.strip():
                # There are uncommitted changes, discard them
                subprocess.run(
                    ["git", "checkout", "."],
                    cwd=self.project_path,
                    capture_output=True,
                )
                return "Discarded uncommitted changes"
            
            # No uncommitted changes, try undoing last commit
            result = subprocess.run(
                ["git", "reset", "--hard", "HEAD~1"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                return "Undid last commit (git reset --hard HEAD~1)"
            else:
                return f"Nothing to undo: {result.stderr}"
        except Exception as e:
            return f"Undo failed: {e}"
    
    def cmd_redo(self, args: str) -> str:
        """Redo last undone edit via git reflog."""
        try:
            result = subprocess.run(
                ["git", "reflog", "-1", "--format=%H"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                commit = result.stdout.strip()
                subprocess.run(
                    ["git", "reset", "--hard", commit],
                    cwd=self.project_path,
                    capture_output=True,
                )
                return f"Redo to commit {commit[:8]}"
            else:
                return "Nothing to redo"
        except Exception as e:
            return f"Redo failed: {e}"
    
    def cmd_diff(self, args: str) -> str:
        """Show colored diff of uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            
            if not result.stdout.strip():
                # Check staged changes
                result = subprocess.run(
                    ["git", "diff", "--cached"],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                )
            
            if not result.stdout.strip():
                return "No changes to diff"
            
            # Color the diff output
            lines = result.stdout.split('\n')
            colored = []
            for line in lines:
                if line.startswith('+'):
                    colored.append(f"\033[32m{line}\033[0m")  # Green
                elif line.startswith('-'):
                    colored.append(f"\033[31m{line}\033[0m")  # Red
                elif line.startswith('@@'):
                    colored.append(f"\033[36m{line}\033[0m")  # Cyan
                else:
                    colored.append(line)
            
            return '\n'.join(colored)
        except Exception as e:
            return f"Diff failed: {e}"
    
    def cmd_commit(self, args: str) -> str:
        """Commit all changes with AI-generated message."""
        try:
            # Stage all changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.project_path,
                capture_output=True,
            )
            
            # Check if there's anything to commit
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            
            if not status.stdout.strip():
                return "Nothing to commit"
            
            # Get diff for commit message
            diff = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            
            # Generate commit message
            commit_msg = args if args else f"Update: {diff.stdout.strip()[:50]}"
            
            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                return f"Committed: {commit_msg}"
            else:
                return f"Commit failed: {result.stderr}"
        except Exception as e:
            return f"Commit failed: {e}"
    
    def cmd_web(self, args: str) -> str:
        """Scrape a webpage and add content to context."""
        if not args:
            return "Usage: /web <url>"
        
        try:
            import urllib.request
            from html.parser import HTMLParser
            
            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self.skip = False
                
                def handle_starttag(self, tag, attrs):
                    if tag in ('script', 'style', 'nav', 'footer'):
                        self.skip = True
                
                def handle_endtag(self, tag):
                    if tag in ('script', 'style', 'nav', 'footer'):
                        self.skip = False
                
                def handle_data(self, data):
                    if not self.skip:
                        text = data.strip()
                        if text:
                            self.text.append(text)
            
            req = urllib.request.Request(args, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='replace')
            
            extractor = TextExtractor()
            extractor.feed(html)
            text = '\n'.join(extractor.text)
            
            # Truncate if too long
            if len(text) > 10000:
                text = text[:10000] + "\n... [truncated]"
            
            return f"Web content from {args}:\n\n{text}"
        except Exception as e:
            return f"Failed to scrape URL: {e}"
    
    def cmd_help(self, args: str) -> str:
        """Show available commands."""
        return """
Commands:
  /add <file>     Add file(s) to chat context
  /drop <file>    Remove file(s) from chat context
  /files          List files in chat context
  /run <cmd>      Run a shell command
  /undo           Undo last AI edit (via git)
  /redo           Redo last undone edit
  /diff           Show colored diff of changes
  /commit [msg]   Commit all changes
  /web <url>      Scrape webpage and add to context
  /clear          Clear conversation history
  /compact        Compress conversation history
  /model <name>   Switch model
  /mode <name>    Switch mode (ask/code/architect)
  /cost           Show token usage
  /lint           Run linter on project
  /test           Run tests
  /status         Show agent status
  /help           Show this help
"""
    
    def cmd_clear(self, args: str) -> str:
        """Clear conversation history."""
        if self.agent:
            self.agent.messages.clear()
            self.agent.done_messages.clear()
        return "Conversation cleared"
    
    def cmd_compact(self, args: str) -> str:
        """Compress conversation history."""
        if self.agent and hasattr(self.agent, 'compressor'):
            compressed = self.agent.compressor.compress(self.agent.messages)
            self.agent.messages = compressed.messages
            return f"Compressed: {compressed.summary}"
        return "Compression not available"
    
    def cmd_model(self, args: str) -> str:
        """Switch model."""
        if not args:
            return "Usage: /model <model-name>\nAvailable: fast, smart, vision, tool"
        
        if self.agent:
            if hasattr(self.agent, 'config'):
                self.agent.config.force_model = args
            return f"Model switched to: {args}"
        return "Agent not available"
    
    def cmd_mode(self, args: str) -> str:
        """Switch chat mode."""
        modes = {
            'ask': 'Read-only, ask questions',
            'code': 'Full access, make changes',
            'architect': 'Plan changes, then execute',
        }
        
        if not args:
            return "Modes:\n" + "\n".join(f"  {k}: {v}" for k, v in modes.items())
        
        if args.lower() in modes:
            if self.agent and hasattr(self.agent, 'config'):
                self.agent.config.approval_mode = 'full-auto' if args == 'code' else 'suggest'
            return f"Mode switched to: {args}"
        
        return f"Unknown mode: {args}. Available: {', '.join(modes.keys())}"
    
    def cmd_cost(self, args: str) -> str:
        """Show token usage and cost."""
        if self.agent:
            sent = getattr(self.agent, 'total_tokens_sent', 0)
            received = getattr(self.agent, 'total_tokens_received', 0)
            return f"Tokens sent: {sent:,}\nTokens received: {received:,}\nTotal: {sent + received:,}"
        return "No usage data"
    
    def cmd_lint(self, args: str) -> str:
        """Run linter on project."""
        from .auto_quality import AutoQuality
        aq = AutoQuality(project_path=self.project_path)
        
        # Lint all Python files
        import glob
        py_files = glob.glob(os.path.join(self.project_path, "**/*.py"), recursive=True)
        
        results = []
        for f in py_files[:10]:  # Limit to 10 files
            rel = os.path.relpath(f, self.project_path)
            result = aq.lint_file(rel)
            if not result.success:
                results.append(f"{rel}: {', '.join(result.errors[:3])}")
        
        if results:
            return "Lint errors:\n" + "\n".join(results)
        return "All files pass lint"
    
    def cmd_test(self, args: str) -> str:
        """Run tests."""
        from .auto_quality import AutoQuality
        aq = AutoQuality(project_path=self.project_path)
        result = aq.run_tests(args if args else None)
        
        output = f"Tests: {'PASSED' if result.success else 'FAILED'}\n"
        output += f"  Passed: {result.passed}\n"
        output += f"  Failed: {result.failed}\n"
        if result.errors:
            output += "Errors:\n" + "\n".join(result.errors[:5])
        return output
    
    def cmd_files(self, args: str) -> str:
        """List files in chat context."""
        if not self.chat_files:
            return "No files in chat"
        return "Files in chat:\n" + "\n".join(f"  {f}" for f in sorted(self.chat_files))
    
    def cmd_status(self, args: str) -> str:
        """Show agent status."""
        lines = [
            f"Project: {self.project_path}",
            f"Files in chat: {len(self.chat_files)}",
            f"Read-only files: {len(self.read_only_files)}",
        ]
        
        if self.agent:
            lines.append(f"Model: {getattr(self.agent.config, 'default_model', 'unknown')}")
            lines.append(f"Mode: {getattr(self.agent.config, 'approval_mode', 'unknown')}")
            lines.append(f"Steps: {len(self.agent.messages)}")
        
        # Git status
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            changes = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            lines.append(f"Git changes: {changes}")
        except Exception:
            lines.append("Git: not a repo")
        
        return "\n".join(lines)
