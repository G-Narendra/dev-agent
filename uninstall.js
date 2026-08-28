#!/usr/bin/env node
/**
 * Pre-uninstall script for narendra CLI
 * 
 * Cleans up Dev Agent state files when the package is uninstalled.
 * Only removes session data — preserves API keys in ~/.dev/config.json
 * so users don't lose their keys if they reinstall.
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

const GREEN = '\x1b[32m';
const YELLOW = '\x1b[33m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';

const home = os.homedir();
const devDir = path.join(home, '.dev');

console.log('');
console.log(`${YELLOW}Uninstalling Dev Agent...${RESET}`);
console.log('');

// Only remove session/cache data, keep config.json with API keys
if (fs.existsSync(devDir)) {
    const thingsToRemove = [
        path.join(devDir, 'sessions'),
        path.join(devDir, 'conversations'),
        path.join(devDir, 'checkpoints'),
        path.join(devDir, 'cache'),
        path.join(devDir, 'memory'),
        path.join(devDir, 'logs'),
    ];
    
    let removed = 0;
    for (const item of thingsToRemove) {
        if (fs.existsSync(item)) {
            try {
                fs.rmSync(item, { recursive: true, force: true });
                removed++;
            } catch { /* ignore */ }
        }
    }
    
    if (removed > 0) {
        console.log(`${GREEN}✓${RESET} Cleaned up ${removed} session directories`);
    }
    
    // Keep config.json — it contains API keys the user may want to reuse
    if (fs.existsSync(path.join(devDir, 'config.json'))) {
        console.log(`${DIM}  Preserved: ~/.dev/config.json (API keys)${RESET}`);
    }
} else {
    console.log(`${GREEN}✓${RESET} No state files to clean up`);
}

// Remove shell completions
const completionPaths = [
    path.join(home, '.bash_completion.d', 'narendra'),
    path.join(home, '.zsh', 'completions', '_narendra'),
    path.join(home, '.config', 'fish', 'completions', 'narendra.fish'),
];

for (const p of completionPaths) {
    if (fs.existsSync(p)) {
        try {
            fs.unlinkSync(p);
            console.log(`${GREEN}✓${RESET} Removed shell completion: ${path.basename(p)}`);
        } catch { /* ignore */ }
    }
}

console.log('');
console.log(`${GREEN}Dev Agent uninstalled.${RESET}`);
console.log(`${DIM}API keys preserved in ~/.dev/config.json${RESET}`);
console.log(`${DIM}To fully remove: rm -rf ~/.dev${RESET}`);
console.log('');
