"""
Multi-file atomic edit tool for Dev.

Lets the agent edit multiple files in a single operation,
with rollback if any edit fails.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any

from .base import Tool


class MultiEditTool(Tool):
    """Edit multiple files atomically — all succeed or all roll back."""

    name = "multi_edit"
    description = "Edit multiple files in a single atomic operation. If any edit fails, all changes are rolled back. Use this when you need to modify several files together."

    parameters = {
        "type": "object",
        "properties": {
            "edits": {
                "type": "array",
                "description": "List of edits to apply",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "New file content (full replacement)"},
                        "old": {"type": "string", "description": "Old string to replace (for str_replace)"},
                        "new": {"type": "string", "description": "New string (for str_replace)"},
                    },
                    "required": ["path"],
                },
            },
        },
        "required": ["edits"],
    }

    async def execute(self, args: dict, state: Any, project_path: str) -> dict:
        edits = args.get("edits", [])
        if not edits:
            return {"error": "No edits provided"}

        # Phase 1: Validate all paths and read originals
        originals = {}
        for edit in edits:
            file_path = edit.get("path", "")
            if not file_path:
                return {"error": "Missing 'path' in edit"}

            abs_path = os.path.join(project_path, file_path) if not os.path.isabs(file_path) else file_path

            # For full replacement, file must exist
            if "content" in edit and not os.path.isfile(abs_path):
                return {"error": f"File not found: {file_path} (cannot create with multi_edit, use write_file)"}

            # For str_replace, file must exist and contain old string
            if "old" in edit:
                if not os.path.isfile(abs_path):
                    return {"error": f"File not found: {file_path}"}
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                normalized_content = content.replace('\r\n', '\n')
                normalized_old = edit["old"].replace('\r\n', '\n')
                if normalized_old not in normalized_content:
                    return {"error": f"old string not found in {file_path}"}

            originals[abs_path] = abs_path  # Track files to rollback

        # Phase 2: Apply all edits (backing up first)
        backups = {}
        applied = []
        try:
            for edit in edits:
                file_path = edit.get("path", "")
                abs_path = os.path.join(project_path, file_path) if not os.path.isabs(file_path) else file_path

                # Backup original
                if abs_path in originals and os.path.isfile(abs_path):
                    backup = abs_path + ".multi_edit_backup"
                    shutil.copy2(abs_path, backup)
                    backups[abs_path] = backup

                if "content" in edit:
                    # Full replacement
                    with open(abs_path, "w", encoding="utf-8") as f:
                        f.write(edit["content"])
                    applied.append({"path": file_path, "action": "full_replace"})

                elif "old" in edit and "new" in edit:
                    # str_replace
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    normalized_content = content.replace('\r\n', '\n')
                    normalized_old = edit["old"].replace('\r\n', '\n')
                    new_content = normalized_content.replace(normalized_old, edit["new"], 1)
                    with open(abs_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    applied.append({"path": file_path, "action": "str_replace"})

            return {
                "success": True,
                "files_edited": len(applied),
                "edits": applied,
            }

        except Exception as e:
            # Rollback all applied edits
            for abs_path, backup in backups.items():
                if os.path.isfile(backup):
                    try:
                        shutil.copy2(backup, abs_path)
                    except Exception:
                        pass

            return {"error": f"Multi-edit failed, all changes rolled back: {e}"}

        finally:
            # Clean up backups
            for backup in backups.values():
                try:
                    os.remove(backup)
                except Exception:
                    pass
