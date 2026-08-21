#!/usr/bin/env node

/**
 * Narendra CLI - Node.js wrapper
 *
 * Finds the Python environment and spawns the Dev CLI.
 * Handles cross-platform path resolution and virtual environments.
 */

const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const PACKAGE_DIR = path.resolve(__dirname, "..");
const VENV_DIR = path.join(PACKAGE_DIR, ".venv");
const IS_WINDOWS = os.platform() === "win32";

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
        // Check if dev package is importable
        try {
          execSync(cmd + ' -c "from dev.cli.main import app" 2>&1', { encoding: "utf-8", timeout: 5000 });
          return cmd;
        } catch {
          // dev not installed, but Python exists
        }
      }
    } catch { /* not found */ }
  }
  return null;
}

function main() {
  const args = process.argv.slice(2);

  // Handle --version
  if (args.includes("--version") || args.includes("-v")) {
    const pkg = require(path.join(PACKAGE_DIR, "package.json"));
    console.log("narendra v" + pkg.version);
    console.log("Free 24/7 AI coding agent powered by NVIDIA NIMs");
    process.exit(0);
  }

  const python = findPython();
  if (!python) {
    console.error("\x1b[31mError: Python 3.11+ is required but not found.\x1b[0m");
    console.error("\x1b[33mInstall Python from https://python.org\x1b[0m");
    process.exit(1);
  }

  // Build environment with PYTHONPATH
  const env = Object.assign({}, process.env);
  const pythonpath = env.PYTHONPATH || "";
  env.PYTHONPATH = PACKAGE_DIR + (pythonpath ? path.delimiter + pythonpath : "");

  // Create .dev directory if it doesn't exist
  const devDir = path.join(process.cwd(), ".dev");
  if (!fs.existsSync(devDir)) {
    fs.mkdirSync(devDir, { recursive: true });
  }

  // Build the Python command string
  // We write args as a Python list literal
  const pyArgs = args.map(function(a) {
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
    console.error("\x1b[31mError: " + err.message + "\x1b[0m");
    process.exit(1);
  });
}

main();
