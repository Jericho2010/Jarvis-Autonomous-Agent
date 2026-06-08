import os
import glob
import logging
import importlib.util
import subprocess
from pathlib import Path
from typing import Any, List, Optional
from agent_framework import tool, FunctionTool

logger = logging.getLogger("jarvis.skills")

def load_skills_from_dir(skills_dir: Path) -> List[FunctionTool]:
    """Dynamically loads and returns all FunctionTools from the specified directory."""
    tools = []
    skills_dir = Path(skills_dir)
    if not skills_dir.exists():
        skills_dir.mkdir(parents=True, exist_ok=True)
        return tools
        
    for py_file in glob.glob(str(skills_dir / "*.py")):
        if py_file.endswith("__init__.py"):
            continue
        module_name = Path(py_file).stem
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # Find all FunctionTool instances defined in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, FunctionTool):
                        # Avoid duplicates
                        if attr not in tools:
                            tools.append(attr)
        except Exception as e:
            logger.error(f"Failed to load skill module {module_name} from {py_file}: {e}")
            
    return tools

@tool(approval_mode="never_require")
def forge_skill(
    skill_name: str,
    code: str,
    test_command: Optional[str] = None
) -> str:
    """
    Forges a new capability for Jarvis by creating or updating a python skill module.
    The module should define functions decorated with @tool from agent_framework.
    
    Args:
        skill_name: The filename of the skill (e.g. 'network_utilities' - do not include .py suffix).
        code: The complete python code of the module.
        test_command: Optional shell command to verify the script (e.g. 'pytest tests/test_net.py').
    
    Returns:
        A report summarizing the compilation, test verification, and loaded tools.
    """
    skills_dir = Path("/home/shaun/jarvis/skills")
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = skills_dir / f"{skill_name}.py"
    
    # Save current code for rollback
    backup_code = None
    if file_path.exists():
        backup_code = file_path.read_text(encoding="utf-8")
        
    try:
        # Write module code
        file_path.write_text(code, encoding="utf-8")
        
        # 1. Compilation check
        try:
            subprocess.run(
                ["python3", "-m", "py_compile", str(file_path)],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as compile_err:
            # Rollback if failed
            if backup_code is not None:
                file_path.write_text(backup_code, encoding="utf-8")
            else:
                file_path.unlink(missing_ok=True)
            return f"❌ Skill compilation failed:\n{compile_err.stderr}"
            
        # 2. Optional Test Command Execution
        if test_command:
            try:
                res = subprocess.run(
                    test_command,
                    shell=True,
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd="/home/shaun/jarvis"
                )
                test_output = res.stdout + "\n" + res.stderr
            except subprocess.CalledProcessError as test_err:
                # Rollback if failed
                if backup_code is not None:
                    file_path.write_text(backup_code, encoding="utf-8")
                else:
                    file_path.unlink(missing_ok=True)
                return f"❌ Verification tests failed:\n{test_err.stdout}\n{test_err.stderr}"
        else:
            test_output = "No test command specified. Compilation check passed."
            
        # 3. Verify module can be loaded and exposes tools
        try:
            spec = importlib.util.spec_from_file_location(skill_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                tools_loaded = []
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, FunctionTool):
                        tools_loaded.append(attr.name)
                        
                if not tools_loaded:
                    return f"⚠️ Warning: Skill saved successfully, but no @tool instances were discovered in {skill_name}.py."
                    
                return (
                    f"✓ Skill '{skill_name}' forged successfully!\n"
                    f"Test Output:\n{test_output}\n"
                    f"Loaded tools: {', '.join(tools_loaded)}"
                )
        except Exception as load_err:
            if backup_code is not None:
                file_path.write_text(backup_code, encoding="utf-8")
            else:
                file_path.unlink(missing_ok=True)
            return f"❌ Failed to load module after writing: {load_err}"
            
    except Exception as e:
        if backup_code is not None:
            file_path.write_text(backup_code, encoding="utf-8")
        return f"❌ Unexpected error during forging: {e}"
