#!/usr/bin/env node

/**
 * Narendra - Postinstall Script
 *
 * Automatically sets up the Python virtual environment and installs
 * all dependencies when the user runs `npm install -g narendra`.
 *
 * This runs after npm downloads the package.
 */

const { execSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const PACKAGE_DIR = __dirname;
const VENV_DIR = path.join(PACKAGE_DIR, ".venv");
const IS_WINDOWS = os.platform() === "win32";

// ============================================================================
// Logging
// ============================================================================

function log(msg) {
  console.log(`\x1b[32m[narendra]\x1b[0m ${msg}`);
}

function warn(msg) {
  console.log(`\x1b[33m[narendra]\x1b[0m ${msg}`);
}

function error(msg) {
  console.error(`\x1b[31m[narendra]\x1b[0m ${msg}`);
}

// ============================================================================
// Python Detection
// ============================================================================

function findPython() {
  const candidates = IS_WINDOWS
    ? ["python", "python3", "py -3"]
    : ["python3", "python"];

  for (const cmd of candidates) {
    try {
      const version = execSync(`${cmd} --version 2>&1`, {
        encoding: "utf-8",
        timeout: 10000,
      }).trim();

      // Extract version number
      const match = version.match(/Python (\d+)\.(\d+)/);
      if (match) {
        const major = parseInt(match[1]);
        const minor = parseInt(match[2]);
        if (major >= 3 && minor >= 11) {
          log(`Found ${version} (${cmd})`);
          return cmd;
        }
      }
    } catch {
      // Not found, try next
    }
  }

  return null;
}

// ============================================================================
// Virtual Environment Setup
// ============================================================================

function createVenv(pythonCmd) {
  if (fs.existsSync(VENV_DIR)) {
    log("Virtual environment already exists, upgrading...");
    return;
  }

  log("Creating virtual environment...");
  try {
    execSync(`${pythonCmd} -m venv "${VENV_DIR}"`, {
      cwd: PACKAGE_DIR,
      stdio: "pipe",
      timeout: 120000,
    });
    log("Virtual environment created");
  } catch (err) {
    error(`Failed to create virtual environment: ${err.message}`);
    throw err;
  }
}

function getVenvPython() {
  return IS_WINDOWS
    ? path.join(VENV_DIR, "Scripts", "python.exe")
    : path.join(VENV_DIR, "bin", "python");
}

function getVenvPip() {
  return IS_WINDOWS
    ? path.join(VENV_DIR, "Scripts", "pip.exe")
    : path.join(VENV_DIR, "bin", "pip");
}

// ============================================================================
// Package Installation
// ============================================================================

function installDependencies() {
  const pip = getVenvPip();
  const venvPython = getVenvPython();

  if (!fs.existsSync(pip)) {
    error("pip not found in virtual environment");
    return false;
  }

  log("Installing Python dependencies...");

  // Upgrade pip first
  try {
    execSync(`"${pip}" install --upgrade pip --quiet`, {
      cwd: PACKAGE_DIR,
      stdio: "pipe",
      timeout: 120000,
    });
  } catch {
    warn("pip upgrade failed, continuing...");
  }

  // Install the dev package with all dependencies
  try {
    execSync(
      `"${pip}" install -e ".[full]" --quiet 2>&1`,
      {
        cwd: PACKAGE_DIR,
        stdio: "pipe",
        timeout: 300000,
      }
    );
    log("Dependencies installed successfully");
    return true;
  } catch (err) {
    // Try without optional dependencies
    warn("Some optional dependencies failed, installing core...");
    try {
      execSync(`"${pip}" install -e . --quiet 2>&1`, {
        cwd: PACKAGE_DIR,
        stdio: "pipe",
        timeout: 300000,
      });
      log("Core dependencies installed");
      return true;
    } catch (err2) {
      error(`Failed to install dependencies: ${err2.message}`);
      return false;
    }
  }
}

// ============================================================================
// Verification
// ============================================================================

function verifyInstallation() {
  const venvPython = getVenvPython();

  try {
    const result = execSync(
      `"${venvPython}" -c "from dev.cli.main import app; print('OK')" 2>&1`,
      {
        cwd: PACKAGE_DIR,
        encoding: "utf-8",
        timeout: 30000,
      }
    );

    if (result.trim() === "OK") {
      log("Installation verified!");
      return true;
    }
  } catch {
    // Not verified
  }

  return false;
}

// ============================================================================
// Create Convenience Scripts
// ============================================================================

function createConvenienceScripts() {
  const venvPython = getVenvPython();
  const binDir = path.join(PACKAGE_DIR, "bin");

  // Create dev wrapper for the Python CLI
  const devWrapper = IS_WINDOWS
    ? path.join(binDir, "dev.cmd")
    : path.join(binDir, "dev");

  const shebang = IS_WINDOWS ? "" : "#!/bin/sh\n";
  const pythonPath = IS_WINDOWS
    ? `"${venvPython}"`
    : `"${venvPython}"`;
  const mainPy = path.join(PACKAGE_DIR, "dev", "cli", "main.py");

  const content = IS_WINDOWS
    ? `@echo off\n"${venvPython}" "${mainPy}" %*`
    : `${shebang}exec ${pythonPath} "${mainPy}" "$@"`;

  fs.writeFileSync(devWrapper, content, { mode: 0o755 });
}

// ============================================================================
// Main
// ============================================================================

async function main() {
  log("Setting up Narendra...");

  // Step 1: Find Python
  const python = findPython();
  if (!python) {
    error("Python 3.11+ is required but not found.");
    error("");
    error("Install Python:");
    error("  macOS:   brew install python@3.12");
    error("  Ubuntu:  sudo apt install python3.12");
    error("  Windows: https://python.org/downloads");
    error("");
    error("After installing, run: npm install -g narendra");
    process.exit(1);
  }

  // Step 2: Create virtual environment
  createVenv(python);

  // Step 3: Install dependencies
  const installed = installDependencies();
  if (!installed) {
    warn("Some dependencies may not have installed correctly.");
    warn("You can manually run: pip install -e .");
  }

  // Step 4: Verify
  if (verifyInstallation()) {
    log("");
    log("Narendra is ready! Run: narendra --help");
    log("");
  } else {
    warn("Installation could not be verified.");
    warn("Try running: narendra --help");
  }

  // Step 5: Create convenience scripts
  try {
    createConvenienceScripts();
  } catch {
    // Non-critical
  }
}

main().catch((err) => {
  error(`Setup failed: ${err.message}`);
  process.exit(1);
});
