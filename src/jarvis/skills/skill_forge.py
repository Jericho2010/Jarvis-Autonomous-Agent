import os
import glob
import logging
import importlib.util
import subprocess
from pathlib import Path
from typing import Any, List, Optional
from agent_framework import tool, FunctionTool

logger = logging.getLogger("jarvis.skills")

def extract_imports(code: str) -> List[str]:
    """Extracts all top-level import names from python source code using AST."""
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
        
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # absolute imports only
                imports.append(node.module.split('.')[0])
    return list(set(imports))

def is_standard_library(module_name: str) -> bool:
    """Checks if a module name is part of Python's standard library."""
    import sys
    return module_name in sys.builtin_module_names or module_name in getattr(sys, "stdlib_module_names", set())

def is_module_available(module_name: str) -> bool:
    """Checks if a module is installed and importable."""
    import importlib.util
    try:
        if is_standard_library(module_name):
            return True
        spec = importlib.util.find_spec(module_name)
        return spec is not None
    except Exception:
        return False

def install_dependency(import_name: str) -> bool:
    """Installs PyPI package for a given import name using uv/pip."""
    import subprocess
    
    IMPORT_TO_PYPI = {
        "PIL": "pillow",
        "sklearn": "scikit-learn",
        "bs4": "beautifulsoup4",
        "yaml": "pyyaml",
        "dotenv": "python-dotenv",
        "fitz": "pymupdf",
    }
    pypi_name = IMPORT_TO_PYPI.get(import_name, import_name.lower())
    
    # Try using uv first
    try:
        subprocess.run(
            ["uv", "pip", "install", pypi_name],
            check=True,
            capture_output=True,
            cwd="/home/shaun/jarvis"
        )
        logger.info(f"Successfully installed package {pypi_name} using uv")
        return True
    except Exception:
        # Fallback to local venv pip
        try:
            subprocess.run(
                ["/home/shaun/jarvis/.venv/bin/python3", "-m", "pip", "install", pypi_name],
                check=True,
                capture_output=True
            )
            logger.info(f"Successfully installed package {pypi_name} using venv pip")
            return True
        except Exception as e:
            logger.error(f"Failed to install package {pypi_name}: {e}")
            return False

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
    # 0. Check and install missing dependencies
    try:
        LOCAL_IGNORE = {"agent_framework", "jarvis"}
        imported_modules = extract_imports(code)
        for mod in imported_modules:
            if mod in LOCAL_IGNORE:
                continue
            if not is_module_available(mod):
                logger.info(f"Dependency '{mod}' is missing. Attempting autonomous installation...")
                install_dependency(mod)
    except Exception as e:
        logger.error(f"Error checking/installing dependencies: {e}")

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
        # Try loading with dynamic recovery on ModuleNotFoundError
        max_retries = 3
        for attempt in range(max_retries):
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
            except ModuleNotFoundError as e:
                missing_mod = e.name
                top_level_mod = missing_mod.split('.')[0] if missing_mod else None
                if top_level_mod and top_level_mod not in {"agent_framework", "jarvis"} and attempt < max_retries - 1:
                    logger.info(f"ModuleNotFoundError: {missing_mod} not found during loading. Retrying installation...")
                    if install_dependency(top_level_mod):
                        continue
                if backup_code is not None:
                    file_path.write_text(backup_code, encoding="utf-8")
                else:
                    file_path.unlink(missing_ok=True)
                return f"❌ Failed to load module after writing: {e}"
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
