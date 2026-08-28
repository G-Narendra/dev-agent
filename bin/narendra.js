#!/usr/bin/env node

/**
 * Narendra CLI — Node.js wrapper for Dev Agent.
 * 
 * Finds the Python environment and spawns the Dev CLI.
 * Handles cross-platform path resolution and virtual environments.
 * 
 * Usage:
 *   narendra              # Interactive chat (default)
 *   narendra chat         # Interactive chat
 *   narendra run "task"   # Single task
 *   narendra setup        # Configure API keys
 *   narendra --version    # Show version
 *   narendra --completion # Generate shell completion
 */

const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const PACKAGE_DIR = path.resolve(__dirname, "..");
const VENV_DIR = path.join(PACKAGE_DIR, ".venv");
const IS_WINDOWS = os.platform() === "win32";

// Colors
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";

/**
 * Find Python 3.11+ in venv or system.
 */
function findPython() {
    // 1. Check for venv Python
    const venvPython = IS_WINDOWS
        ? path.join(VENV_DIR, "Scripts", "python.exe")
        : path.join(VENV_DIR, "bin", "python");

    if (fs.existsSync(venvPython)) return venvPython;

    // 2. Check system Python
    const candidates = IS_WINDOWS ? ["python", "python3", "py -3"] : ["python3", "python"];
    for (const cmd of candidates) {
        try {
            const version = execSync(cmd + " --version 2>&1", { encoding: "utf-8", timeout: 5000 }).trim();
            const match = version.match(/Python (\d+)\.(\d+)/);
            if (match && parseInt(match[1]) >= 3 && parseInt(match[2]) >= 11) {
                return cmd;
            }
        } catch { /* not found */ }
    }
    return null;
}

/**
 * Create venv if it doesn't exist.
 */
function ensureVenv(python) {
    if (fs.existsSync(VENV_DIR)) {
        const venvPy = IS_WINDOWS
            ? path.join(VENV_DIR, "Scripts", "python.exe")
            : path.join(VENV_DIR, "bin", "python");
        if (fs.existsSync(venvPy)) return venvPy;
    }
    
    console.log(`${DIM}Setting up Python environment...${RESET}`);
    try {
        execSync(`${python} -m venv "${VENV_DIR}"`, { stdio: "pipe", timeout: 60000 });
        
        // Install deps
        const pip = IS_WINDOWS
            ? path.join(VENV_DIR, "Scripts", "pip.exe")
            : path.join(VENV_DIR, "bin", "pip");
        const reqFile = path.join(PACKAGE_DIR, "requirements.txt");
        
        if (fs.existsSync(pip) && fs.existsSync(reqFile)) {
            execSync(`"${pip}" install -r "${reqFile}" --quiet --disable-pip-version-check`, {
                stdio: "pipe",
                timeout: 120000
            });
        }
        
        // Install dev package
        if (fs.existsSync(pip)) {
            try {
                execSync(`"${pip}" install -e "${PACKAGE_DIR}" --quiet --disable-pip-version-check`, {
                    stdio: "pipe",
                    timeout: 120000
                });
            } catch { /* optional */ }
        }
        
        const venvPy = IS_WINDOWS
            ? path.join(VENV_DIR, "Scripts", "python.exe")
            : path.join(VENV_DIR, "bin", "python");
        if (fs.existsSync(venvPy)) {
            console.log(`${GREEN}✓${RESET} Environment ready`);
            return venvPy;
        }
    } catch (e) {
        console.error(`${RED}✗${RESET} Failed to create environment: ${e.message}`);
    }
    return null;
}

/**
 * Generate shell completion script.
 */
function generateCompletion(shell) {
    const pkg = require(path.join(PACKAGE_DIR, "package.json"));
    
    if (shell === "bash") {
        console.log(`#!/bin/bash
# narendra bash completion
_narendra_completions() {
    local cur prev commands
    COMPREPLY=()
    cur="\${COMP_WORDS[COMP_CWORD]}"
    prev="\${COMP_WORDS[COMP_CWORD-1]}"
    commands="chat run setup models status first-run mode-set mode-get undo redo checkpoints headless rules attach commit branch skill skills-list hooks memory ci validate init cost effort detect profile conversations loop sessions fork search-sessions doctor git-diff review batch resume stop respawn rm logs login logout auth-status update powerup config settings gitlab-ci set-author link-pr pr-sessions validate-schema ultrareview purge tool-rules-list tool-rules-add tools-list version daemon agents mcp auto-mode sessions-picker typo onboard shell-completion templates template-run skills plugins-list plugin-install vscode tool-create mailbox plan workflow-list workflow-run tool-rules approval checkpoint team mode schedule connect design"
    
    if [[ \${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=($(compgen -W "\$commands" -- "\$cur"))
    elif [[ "\$prev" == "run" || "\$prev" == "chat" ]]; then
        COMPREPLY=()
    fi
    return 0
}
complete -F _narendra_completions narendra
`);
    } else if (shell === "zsh") {
        console.log(`#compdef narendra

# narendra zsh completion
_narendra() {
    _arguments \
        '1:command:->commands' \
        '*:: :->args'
    
    case $state in
        commands)
            local commands=(
                'chat:Interactive chat with streaming output'
                'run:Run a task with streaming output'
                'setup:Configure Dev with NVIDIA NIM API keys'
                'models:List available models'
                'status:Show Dev status'
                'help:Show help'
            )
            _describe 'command' commands
            ;;
    esac
}

_narendra "$@"
`);
    } else if (shell === "fish") {
        console.log(`# fish completion for narendra

complete -c narendra -f
complete -c narendra -n '__fish_use_subcommand' -a chat -d 'Interactive chat'
complete -c narendra -n '__fish_use_subcommand' -a run -d 'Run a task'
complete -c narendra -n '__fish_use_subcommand' -a setup -d 'Configure API keys'
complete -c narendra -n '__fish_use_subcommand' -a models -d 'List models'
complete -c narendra -n '__fish_use_subcommand' -a status -d 'Show status'
complete -c narendra -n '__fish_use_subcommand' -a help -d 'Show help'
complete -c narendra -n '__fish_use_subcommand' -a version -d 'Show version'
`);
    }
}

/**
 * Main entry point.
 */
function main() {
    const args = process.argv.slice(2);

    // Handle --version
    if (args.includes("--version") || args.includes("-v")) {
        const pkg = require(path.join(PACKAGE_DIR, "package.json"));
        console.log("narendra v" + pkg.version);
        console.log("Free 24/7 AI coding agent powered by NVIDIA NIMs");
        process.exit(0);
    }

    // Handle --completion
    if (args.includes("--completion") || args.includes("--completions")) {
        const shell = args.find(a => ["bash", "zsh", "fish"].includes(a)) || "bash";
        generateCompletion(shell);
        process.exit(0);
    }

    // Handle --install-completion (for typer compatibility)
    if (args.includes("--install-completion")) {
        const shell = process.env.SHELL || "";
        let detected = "bash";
        if (shell.includes("zsh")) detected = "zsh";
        else if (shell.includes("fish")) detected = "fish";
        
        // Write completion file to appropriate location
        const home = os.homedir();
        let installPath;
        if (detected === "bash") {
            installPath = path.join(home, ".bash_completion.d", "narendra");
            fs.mkdirSync(path.dirname(installPath), { recursive: true });
        } else if (detected === "zsh") {
            installPath = path.join(home, ".zsh", "completions", "_narendra");
            fs.mkdirSync(path.dirname(installPath), { recursive: true });
        } else if (detected === "fish") {
            installPath = path.join(home, ".config", "fish", "completions", "narendra.fish");
            fs.mkdirSync(path.dirname(installPath), { recursive: true });
        }
        
        if (installPath) {
            const completion = generateCompletion(detected);
            // generateCompletion prints to stdout, so we need to capture it
            const origLog = console.log;
            let output = "";
            console.log = (msg) => { output += msg + "\n"; };
            generateCompletion(detected);
            console.log = origLog;
            fs.writeFileSync(installPath, output);
            console.log(`${GREEN}✓${RESET} Shell completion installed for ${detected}`);
            console.log(`${DIM}  ${installPath}${RESET}`);
        }
        process.exit(0);
    }

    // Find Python
    let python = findPython();
    if (!python) {
        // Try to create venv first
        const sysPython = IS_WINDOWS ? "python" : "python3";
        python = ensureVenv(sysPython);
        if (!python) {
            console.error("");
            console.error(`${RED}Error: Python 3.11+ is required but not found.${RESET}`);
            console.error("");
            console.error("Install Python from: https://python.org/downloads");
            process.exit(1);
        }
    } else {
        // Python found, but venv might not exist yet
        python = ensureVenv(python) || python;
    }

    // Build environment with PYTHONPATH
    const env = Object.assign({}, process.env);
    const pythonpath = env.PYTHONPATH || "";
    env.PYTHONPATH = PACKAGE_DIR + (pythonpath ? path.delimiter + pythonpath : "");
    env.PYTHONIOENCODING = "utf-8";

    // Create .dev directory if it doesn't exist
    const devDir = path.join(process.cwd(), ".dev");
    if (!fs.existsSync(devDir)) {
        fs.mkdirSync(devDir, { recursive: true });
    }

    // Default to 'chat' when no arguments given
    const finalArgs = args.length === 0 ? ["chat"] : args;

    // Build the Python command
    const pyArgs = finalArgs.map(function(a) {
        return a.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    });
    const pyList = pyArgs.map(function(a) { return "'" + a + "'"; }).join(", ");
    const pyCmd = "from dev.cli.main import app; app([" + pyList + "])";

    // Spawn Python
    var child = spawn(python, ["-c", pyCmd], {
        cwd: process.cwd(),
        env: env,
        stdio: "inherit",
        shell: false,
    });

    process.on("SIGINT", function() {
        if (!child.killed) child.kill("SIGINT");
    });
    process.on("SIGTERM", function() {
        if (!child.killed) child.kill("SIGTERM");
    });

    child.on("close", function(code) {
        process.exit(code || 0);
    });

    child.on("error", function(err) {
        console.error(`${RED}Error: ${err.message}${RESET}`);
        process.exit(1);
    });
}

main();
