#!/usr/bin/env node
/**
 * Postinstall script for dev-agent
 * Sets up Python virtual environment and installs dependencies
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const VENV_DIR = path.join(ROOT, '.venv');
const REQUIREMENTS = path.join(ROOT, 'requirements.txt');

console.log('🚀 Setting up Dev Agent...');

// Check if Python is available
function checkPython() {
    const commands = ['python3', 'python', 'py'];
    for (const cmd of commands) {
        try {
            execSync(`${cmd} --version`, { stdio: 'pipe' });
            return cmd;
        } catch (e) {
            continue;
        }
    }
    return null;
}

// Create virtual environment
function createVenv(python) {
    if (fs.existsSync(VENV_DIR)) {
        console.log('✅ Virtual environment already exists');
        return;
    }
    
    console.log('📦 Creating virtual environment...');
    execSync(`${python} -m venv "${VENV_DIR}"`, { stdio: 'pipe' });
}

// Install dependencies
function installDeps(python) {
    const pip = path.join(VENV_DIR, 'Scripts', 'pip.exe');
    const pipUnix = path.join(VENV_DIR, 'bin', 'pip');
    const pipCmd = fs.existsSync(pip) ? pip : pipUnix;
    
    if (!fs.existsSync(pipCmd)) {
        console.log('⚠️  pip not found, skipping dependency installation');
        return;
    }
    
    if (fs.existsSync(REQUIREMENTS)) {
        console.log('📚 Installing dependencies...');
        execSync(`"${pipCmd}" install -r "${REQUIREMENTS}" --quiet`, { stdio: 'pipe' });
    }
}

// Main
try {
    const python = checkPython();
    if (!python) {
        console.error('❌ Python not found. Please install Python 3.10+');
        process.exit(1);
    }
    
    createVenv(python);
    installDeps(python);
    
    console.log('');
    console.log('✅ Dev Agent installed successfully!');
    console.log('');
    console.log('Quick start:');
    console.log('  narendra setup     # Configure API keys');
    console.log('  narendra chat      # Start interactive chat');
    console.log('  narendra run "build a website"  # Single task');
    console.log('');
} catch (e) {
    console.error('⚠️  Setup warning:', e.message);
    console.log('You may need to run manually: python -m dev setup');
}
