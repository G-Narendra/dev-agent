#!/usr/bin/env node
/**
 * Postinstall script for narendra CLI
 * 
 * Sets up Python virtual environment and installs dependencies.
 * Runs automatically after: npm install -g narendra
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const ROOT = __dirname;
const VENV_DIR = path.join(ROOT, '.venv');
const REQUIREMENTS = path.join(ROOT, 'requirements.txt');
const IS_WINDOWS = os.platform() === 'win32';

// Colors
const GREEN = '\x1b[32m';
const YELLOW = '\x1b[33m';
const RED = '\x1b[31m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';

function log(msg) { console.log(`${GREEN}✓${RESET} ${msg}`); }
function warn(msg) { console.log(`${YELLOW}⚠${RESET} ${msg}`); }
function error(msg) { console.error(`${RED}✗${RESET} ${msg}`); }

/**
 * Find Python 3.11+ on the system.
 */
function findPython() {
    const candidates = IS_WINDOWS 
        ? ['python', 'python3', 'py -3']
        : ['python3', 'python'];
    
    for (const cmd of candidates) {
        try {
            const version = execSync(`${cmd} --version 2>&1`, { 
                encoding: 'utf-8', 
                timeout: 5000,
                stdio: ['pipe', 'pipe', 'pipe']
            }).trim();
            const match = version.match(/Python (\d+)\.(\d+)/);
            if (match && parseInt(match[1]) >= 3 && parseInt(match[2]) >= 11) {
                return cmd;
            }
        } catch { /* not found */ }
    }
    return null;
}

/**
 * Create Python virtual environment.
 */
function createVenv(python) {
    if (fs.existsSync(VENV_DIR)) {
        const pythonPath = IS_WINDOWS
            ? path.join(VENV_DIR, 'Scripts', 'python.exe')
            : path.join(VENV_DIR, 'bin', 'python');
        if (fs.existsSync(pythonPath)) {
            log('Virtual environment already exists');
            return true;
        }
        // Venv dir exists but is incomplete — remove and recreate
        warn('Incomplete venv detected, recreating...');
        fs.rmSync(VENV_DIR, { recursive: true, force: true });
    }
    
    console.log(`${DIM}  Creating Python virtual environment...${RESET}`);
    try {
        execSync(`${python} -m venv "${VENV_DIR}"`, { 
            stdio: ['pipe', 'pipe', 'pipe'],
            timeout: 60000
        });
        log('Virtual environment created');
        return true;
    } catch (e) {
        error(`Failed to create venv: ${e.message}`);
        return false;
    }
}

/**
 * Install Python dependencies into the venv.
 */
function installDeps(python) {
    const pip = IS_WINDOWS
        ? path.join(VENV_DIR, 'Scripts', 'pip.exe')
        : path.join(VENV_DIR, 'bin', 'pip');
    
    if (!fs.existsSync(pip)) {
        warn('pip not found in venv, skipping dependency installation');
        return false;
    }
    
    if (!fs.existsSync(REQUIREMENTS)) {
        warn('requirements.txt not found, skipping dependency installation');
        return false;
    }
    
    // Check if deps are already installed (check for key packages)
    const venvPython = IS_WINDOWS
        ? path.join(VENV_DIR, 'Scripts', 'python.exe')
        : path.join(VENV_DIR, 'bin', 'python');
    
    try {
        execSync(`"${venvPython}" -c "import httpx; import rich; import typer" 2>&1`, {
            encoding: 'utf-8',
            timeout: 5000,
            stdio: ['pipe', 'pipe', 'pipe']
        });
        log('Dependencies already installed');
        return true;
    } catch {
        // Need to install
    }
    
    console.log(`${DIM}  Installing Python dependencies...${RESET}`);
    try {
        execSync(`"${pip}" install -r "${REQUIREMENTS}" --quiet --disable-pip-version-check`, {
            stdio: ['pipe', 'pipe', 'pipe'],
            timeout: 120000
        });
        log('Dependencies installed');
        return true;
    } catch (e) {
        error(`Failed to install dependencies: ${e.message}`);
        return false;
    }
}

/**
 * Install the dev package itself in development mode.
 */
function installDevPackage(python) {
    const venvPython = IS_WINDOWS
        ? path.join(VENV_DIR, 'Scripts', 'python.exe')
        : path.join(VENV_DIR, 'bin', 'python');
    
    if (!fs.existsSync(venvPython)) return false;
    
    // Check if dev is already importable
    try {
        execSync(`"${venvPython}" -c "from dev.cli.main import app" 2>&1`, {
            encoding: 'utf-8',
            timeout: 5000,
            stdio: ['pipe', 'pipe', 'pipe']
        });
        return true;
    } catch {
        // Need to install dev package
    }
    
    console.log(`${DIM}  Installing dev package...${RESET}`);
    try {
        const pip = IS_WINDOWS
            ? path.join(VENV_DIR, 'Scripts', 'pip.exe')
            : path.join(VENV_DIR, 'bin', 'pip');
        execSync(`"${pip}" install -e "${ROOT}" --quiet --disable-pip-version-check`, {
            stdio: ['pipe', 'pipe', 'pipe'],
            timeout: 120000
        });
        log('Dev package installed');
        return true;
    } catch (e) {
        warn(`Could not install dev package: ${e.message}`);
        return false;
    }
}

/**
 * Print setup instructions.
 */
function printInstructions() {
    console.log('');
    console.log(`${GREEN}═══════════════════════════════════════════════════${RESET}`);
    console.log(`${GREEN}  🚀 Dev Agent installed successfully!${RESET}`);
    console.log(`${GREEN}═══════════════════════════════════════════════════${RESET}`);
    console.log('');
    console.log('  Quick start:');
    console.log(`    ${DIM}narendra setup${RESET}              # Configure API keys`);
    console.log(`    ${DIM}narendra chat${RESET}               # Interactive chat`);
    console.log(`    ${DIM}narendra run "build a website"${RESET}  # Single task`);
    console.log('');
    console.log(`  ${DIM}Get free API keys at: https://build.nvidia.com${RESET}`);
    console.log('');
}

// Main
try {
    const python = findPython();
    if (!python) {
        console.error('');
        console.error(`${RED}Error: Python 3.11+ is required but not found.${RESET}`);
        console.error('');
        console.error('Install Python from: https://python.org/downloads');
        console.error('Or use: winget install Python.Python.3.12');
        console.error('');
        process.exit(1);
    }
    
    const venvCreated = createVenv(python);
    const depsInstalled = installDeps(python);
    installDevPackage(python);
    
    if (venvCreated && depsInstalled) {
        printInstructions();
    }
} catch (e) {
    warn(`Setup warning: ${e.message}`);
    console.log(`${DIM}You may need to run manually: python -m dev setup${RESET}`);
}
