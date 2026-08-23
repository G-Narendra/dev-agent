"""
Shell Completion — Auto-complete commands in bash/zsh

Provides tab completion for all Dev agent commands.
"""
import os

BASH_COMPLETION = """#!/bin/bash
# Dev Agent shell completion for bash

_dev_completions() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    commands="setup run chat task serve models status first-run mode-set mode-get \\
              undo redo checkpoints headless rules attach commit branch skill \\
              skills-list hooks memory ci validate init cost effort detect profile \\
              conversations loop sessions fork search-sessions doctor git-diff review \\
              batch resume stop respawn rm logs login logout auth-status update \\
              powerup config settings gitlab-ci set-author link-pr pr-sessions \\
              validate-schema ultrareview purge tool-rules-list tool-rules-add \\
              tools-list version daemon agents mcp auto-mode sessions-picker typo \\
              onboard shell-compare templates template-run skills plugins-list \\
              plugin-install vscode tool-create mailbox plan workflow-list \\
              workflow-run tool-rules approval checkpoint team mode schedule \\
              connect help"
    
    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "--help --version --verbose --print --yes --model --effort" -- ${cur}) )
        return 0
    fi
    
    COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
    return 0
}

complete -F _dev_completions dev-agent
complete -F _dev_completions narendra
"""

ZSH_COMPLETION = """#compdef narendra dev-agent

# Dev Agent shell completion for zsh

_narendra() {
    local -a commands
    commands=(
        'setup:Configure Dev with NVIDIA NIM API keys'
        'run:Run a task with streaming output'
        'chat:Interactive chat with streaming and tools'
        'task:Manage background tasks'
        'serve:Start the 24/7 background worker'
        'models:List available NVIDIA NIM models'
        'status:Show Dev status'
        'first-run:Run the interactive API key setup wizard'
        'help:Show help message'
        'version:Show version'
        'doctor:Full diagnostic check'
        'undo:Undo the last AI edit'
        'redo:Redo a previously undone checkpoint'
        'diff:Show colored git diff'
        'commit:Auto-commit all changes'
        'branch:Create and switch to a new branch'
        'lint:Run linter on project'
        'test:Run tests'
        'cost:Show cost and token usage'
        'mcp:Configure MCP servers'
        'team:Manage agent teams'
    )
    
    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'
    
    case "$state" in
        command)
            _describe 'command' commands
            ;;
        args)
            case "$words[1]" in
                run)
                    _arguments \
                        '--model[Model to use]:model:' \
                        '--effort[Reasoning effort]:effort:(low medium high)' \
                        '--verbose[Show detailed output]' \
                        '--yes[Auto-approve all changes]'
                    ;;
                chat)
                    _arguments \
                        '--model[Model to use]:model:' \
                        '--effort[Reasoning effort]:effort:(low medium high)' \
                        '--verbose[Show detailed output]'
                    ;;
                setup)
                    _arguments \
                        '--key[NVIDIA NIM API key]:key:'
                    ;;
            esac
            ;;
    esac
}

_narendra "$@"
"""

def get_completion(shell: str = "bash") -> str:
    """Get shell completion script."""
    if shell == "zsh":
        return ZSH_COMPLETION
    return BASH_COMPLETION

def install_completion(shell: str = None):
    """Install shell completion."""
    if shell is None:
        shell = "bash" if os.name != "nt" else "bash"
    
    completion_script = get_completion(shell)
    
    if shell == "bash":
        # Try to add to .bashrc
        bashrc = os.path.expanduser("~/.bashrc")
        marker = "# Dev Agent completion"
        
        if os.path.exists(bashrc):
            with open(bashrc, 'r') as f:
                content = f.read()
            
            if marker not in content:
                with open(bashrc, 'a') as f:
                    f.write(f"\n{marker}\n{completion_script}\n")
                print(f"Added completion to {bashrc}")
            else:
                print(f"Completion already in {bashrc}")
        else:
            print(f"Create {bashrc} first, then re-run")
    
    elif shell == "zsh":
        # Try to add to .zshrc
        zshrc = os.path.expanduser("~/.zshrc")
        marker = "# Dev Agent completion"
        
        if os.path.exists(zshrc):
            with open(zshrc, 'r') as f:
                content = f.read()
            
            if marker not in content:
                with open(zshrc, 'a') as f:
                    f.write(f"\n{marker}\n{completion_script}\n")
                print(f"Added completion to {zshrc}")
            else:
                print(f"Completion already in {zshrc}")
        else:
            print(f"Create {zshrc} first, then re-run")
