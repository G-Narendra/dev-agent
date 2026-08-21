"""
Checkpoint system for undo/redo of AI file changes.

Every major CLI coding tool has this:
- Claude Code: checkpoints for undo
- Codex: approval modes with revert
- Cline: checkpoints for all changes
- Aider: git-based undo with /undo command

This implements a lightweight checkpoint system that snapshots file state before AI edits.
"""
from __future__ import annotations
import os
import json
import hashlib
import shutil
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from datetime import datetime


@dataclass
class FileChange:
    """A single file change within a checkpoint."""
    path: str
    action: str  # "create", "modify", "delete"
    old_content: Optional[str] = None  # None for creates
    new_content: Optional[str] = None  # None for deletes
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None


@dataclass
class Checkpoint:
    """A snapshot of file state before an AI edit."""
    id: int
    timestamp: str
    description: str
    changes: list = field(default_factory=list)
    parent_id: Optional[int] = None
    applied: bool = True  # False if undone


class CheckpointManager:
    """Manages checkpoints for undo/redo of AI edits."""
    
    def __init__(self, project_root: str = ".", checkpoint_dir: str = ".dev/checkpoints"):
        self.project_root = os.path.abspath(project_root)
        self.checkpoint_dir = os.path.join(self.project_root, checkpoint_dir)
        self.checkpoints: list[Checkpoint] = []
        self._next_id = 1
        self._max_checkpoints = 50  # Keep last N checkpoints
        
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        self._load_checkpoints()

    def _load_checkpoints(self):
        """Load checkpoints from disk."""
        index_path = os.path.join(self.checkpoint_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path) as f:
                data = json.load(f)
            self._next_id = data.get("next_id", 1)
            for cp_data in data.get("checkpoints", []):
                cp = Checkpoint(
                    id=cp_data["id"],
                    timestamp=cp_data["timestamp"],
                    description=cp_data["description"],
                    changes=[FileChange(**c) for c in cp_data.get("changes", [])],
                    parent_id=cp_data.get("parent_id"),
                    applied=cp_data.get("applied", True),
                )
                self.checkpoints.append(cp)

    def _save_checkpoints(self):
        """Save checkpoints index to disk."""
        index_path = os.path.join(self.checkpoint_dir, "index.json")
        data = {
            "next_id": self._next_id,
            "checkpoints": [
                {
                    "id": cp.id,
                    "timestamp": cp.timestamp,
                    "description": cp.description,
                    "changes": [
                        {
                            "path": c.path,
                            "action": c.action,
                            "old_hash": c.old_hash,
                            "new_hash": c.new_hash,
                        }
                        for c in cp.changes
                    ],
                    "parent_id": cp.parent_id,
                    "applied": cp.applied,
                }
                for cp in self.checkpoints
            ],
        }
        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)

    def _file_hash(self, path: str) -> str:
        """Get hash of file content."""
        if not os.path.exists(path):
            return ""
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _backup_file(self, path: str, cp_id: int) -> Optional[str]:
        """Backup a file to checkpoint storage. Returns backup path."""
        if not os.path.exists(path):
            return None
        rel_path = os.path.relpath(path, self.project_root)
        backup_dir = os.path.join(self.checkpoint_dir, str(cp_id))
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, rel_path.replace("/", "_").replace("\\", "_"))
        shutil.copy2(path, backup_path)
        return backup_path

    def create_checkpoint(self, description: str, files: list[str]) -> Checkpoint:
        """Create a checkpoint before editing files."""
        cp = Checkpoint(
            id=self._next_id,
            timestamp=datetime.now().isoformat(),
            description=description,
            parent_id=self.checkpoints[-1].id if self.checkpoints else None,
        )
        self._next_id += 1

        for filepath in files:
            abs_path = os.path.join(self.project_root, filepath) if not os.path.isabs(filepath) else filepath
            rel_path = os.path.relpath(abs_path, self.project_root)
            
            old_hash = self._file_hash(abs_path)
            action = "modify" if os.path.exists(abs_path) else "create"
            
            # Backup existing file
            backup_path = self._backup_file(abs_path, cp.id)
            
            change = FileChange(
                path=rel_path,
                action=action,
                old_hash=old_hash,
            )
            cp.changes.append(change)

        self.checkpoints.append(cp)
        
        # Trim old checkpoints
        if len(self.checkpoints) > self._max_checkpoints:
            removed = self.checkpoints[:len(self.checkpoints) - self._max_checkpoints]
            self.checkpoints = self.checkpoints[len(self.checkpoints) - self._max_checkpoints:]
            # Clean up old backup dirs
            for old_cp in removed:
                backup_dir = os.path.join(self.checkpoint_dir, str(old_cp.id))
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir, ignore_errors=True)

        self._save_checkpoints()
        return cp

    def record_after(self, checkpoint_id: int, files: list[str]):
        """Record file state after edits (update hashes)."""
        for cp in self.checkpoints:
            if cp.id == checkpoint_id:
                for change in cp.changes:
                    abs_path = os.path.join(self.project_root, change.path)
                    change.new_hash = self._file_hash(abs_path)
                    if change.new_hash and not change.old_hash:
                        change.action = "create"
                    elif not change.new_hash and change.old_hash:
                        change.action = "delete"
                self._save_checkpoints()
                return

    def undo(self, checkpoint_id: Optional[int] = None) -> bool:
        """Undo a checkpoint. If no id, undo the last one."""
        if checkpoint_id is None:
            # Find last applied checkpoint
            applied = [cp for cp in self.checkpoints if cp.applied]
            if not applied:
                return False
            cp = applied[-1]
        else:
            cp = next((c for c in self.checkpoints if c.id == checkpoint_id), None)
            if not cp:
                return False

        backup_dir = os.path.join(self.checkpoint_dir, str(cp.id))
        
        for change in cp.changes:
            abs_path = os.path.join(self.project_root, change.path)
            
            if change.action == "create":
                # Undo create = delete the file
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            
            elif change.action == "modify":
                # Undo modify = restore from backup
                backup_path = os.path.join(backup_dir, change.path.replace("/", "_").replace("\\", "_"))
                if os.path.exists(backup_path):
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    shutil.copy2(backup_path, abs_path)
            
            elif change.action == "delete":
                # Undo delete = restore from backup
                backup_path = os.path.join(backup_dir, change.path.replace("/", "_").replace("\\", "_"))
                if os.path.exists(backup_path):
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    shutil.copy2(backup_path, abs_path)

        cp.applied = False
        self._save_checkpoints()
        return True

    def redo(self, checkpoint_id: int) -> bool:
        """Redo a previously undone checkpoint."""
        cp = next((c for c in self.checkpoints if c.id == checkpoint_id), None)
        if not cp or cp.applied:
            return False

        backup_dir = os.path.join(self.checkpoint_dir, str(cp.id))
        
        for change in cp.changes:
            abs_path = os.path.join(self.project_root, change.path)
            
            if change.action == "create":
                # Redo create = restore from new backup
                backup_path = os.path.join(backup_dir, change.path.replace("/", "_").replace("\\", "_"))
                if os.path.exists(backup_path):
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    shutil.copy2(backup_path, abs_path)
            
            elif change.action == "modify":
                # Redo modify = re-apply (backup has new version)
                backup_path = os.path.join(backup_dir, change.path.replace("/", "_").replace("\\", "_"))
                if os.path.exists(backup_path):
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    shutil.copy2(backup_path, abs_path)
            
            elif change.action == "delete":
                # Redo delete = remove file again
                if os.path.exists(abs_path):
                    os.remove(abs_path)

        cp.applied = True
        self._save_checkpoints()
        return True

    def undo_last(self) -> bool:
        """Undo the most recent checkpoint."""
        return self.undo()

    def list_checkpoints(self, limit: int = 10) -> list[dict]:
        """List recent checkpoints."""
        result = []
        for cp in reversed(self.checkpoints[-limit:]):
            result.append({
                "id": cp.id,
                "timestamp": cp.timestamp,
                "description": cp.description,
                "files_changed": len(cp.changes),
                "applied": cp.applied,
                "files": [c.path for c in cp.changes],
            })
        return result

    def get_diff(self, checkpoint_id: int) -> str:
        """Get a human-readable diff for a checkpoint."""
        cp = next((c for c in self.checkpoints if c.id == checkpoint_id), None)
        if not cp:
            return "Checkpoint not found"
        
        lines = [f"Checkpoint #{cp.id}: {cp.description}", f"Time: {cp.timestamp}", ""]
        for change in cp.changes:
            lines.append(f"  [{change.action.upper()}] {change.path}")
        return "\n".join(lines)

    def clear(self):
        """Clear all checkpoints."""
        shutil.rmtree(self.checkpoint_dir, ignore_errors=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        self.checkpoints.clear()
        self._next_id = 1
        self._save_checkpoints()
