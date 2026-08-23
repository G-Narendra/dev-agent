"""
Editor Integration — Open files in $EDITOR

Provides editor integration for the agent.
"""
import os
import subprocess
from typing import Optional


class EditorIntegration:
    """
    Open files in the user's preferred editor.
    
    Features:
    1. Open file in $EDITOR
    2. Open file at specific line
    3. Pipe content through editor
    """
    
    def __init__(self):
        self.editor = os.environ.get('EDITOR', os.environ.get('VISUAL', 'nano'))
    
    def open_file(self, path: str, line: int = 0) -> dict:
        """Open a file in the editor."""
        try:
            cmd = [self.editor]
            if line > 0:
                # Try to open at specific line
                if 'vim' in self.editor or 'nvim' in self.editor:
                    cmd.extend([f'+{line}', path])
                elif 'nano' in self.editor:
                    cmd.extend(['+' + str(line), path])
                else:
                    cmd.append(path)
            else:
                cmd.append(path)
            
            subprocess.Popen(cmd)
            return {"success": True, "editor": self.editor, "file": path}
        except Exception as e:
            return {"error": str(e)}
    
    def open_diff(self, old_file: str, new_file: str) -> dict:
        """Open diff in editor."""
        try:
            if 'vim' in self.editor or 'nvim' in self.editor:
                cmd = [self.editor, '-d', old_file, new_file]
            elif 'code' in self.editor:
                cmd = [self.editor, '--diff', old_file, new_file]
            else:
                # Fallback: create temp diff file
                import tempfile
                diff_cmd = ['diff', '-u', old_file, new_file]
                result = subprocess.run(diff_cmd, capture_output=True, text=True)
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.diff', delete=False) as f:
                    f.write(result.stdout)
                    diff_path = f.name
                
                cmd = [self.editor, diff_path]
            
            subprocess.Popen(cmd)
            return {"success": True, "editor": self.editor}
        except Exception as e:
            return {"error": str(e)}
    
    def pipe_through_editor(self, content: str) -> Optional[str]:
        """Pipe content through editor and return result."""
        try:
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.tmp', delete=False) as f:
                f.write(content)
                tmp_path = f.name
            
            subprocess.run([self.editor, tmp_path])
            
            with open(tmp_path, 'r') as f:
                result = f.read()
            
            os.unlink(tmp_path)
            return result
        except Exception:
            return None
