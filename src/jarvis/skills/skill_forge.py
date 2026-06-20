import os
import glob
import logging
import importlib.util
import subprocess
from pathlib import Path
from typing import Any, List, Optional
from agent_framework import tool, FunctionTool
from jarvis.config.paths import get_skills_dir, get_venv_python, get_workspace_root

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
            cwd=str(get_workspace_root())
        )
        logger.info(f"Successfully installed package {pypi_name} using uv")
        return True
    except Exception:
        # Fallback to local venv pip
        try:
            subprocess.run(
                [str(get_venv_python()), "-m", "pip", "install", pypi_name],
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

def _forge_skill_to_path(
    skill_name: str,
    code: str,
    file_path: Path,
    test_command: Optional[str] = None,
    *,
    require_test: bool = False,
) -> tuple[bool, str, bool]:
    """Write, compile, test, and load-verify a skill module at file_path."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    backup_code = file_path.read_text(encoding="utf-8") if file_path.exists() else None

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

    test_passed = False
    try:
        file_path.write_text(code, encoding="utf-8")

        try:
            subprocess.run(
                ["python3", "-m", "py_compile", str(file_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as compile_err:
            if backup_code is not None:
                file_path.write_text(backup_code, encoding="utf-8")
            else:
                file_path.unlink(missing_ok=True)
            return False, f"❌ Skill compilation failed:\n{compile_err.stderr}", False

        if require_test and not test_command:
            if backup_code is not None:
                file_path.write_text(backup_code, encoding="utf-8")
            else:
                file_path.unlink(missing_ok=True)
            return False, "❌ test_command required for staging forge but was not provided.", False

        if test_command:
            try:
                res = subprocess.run(
                    test_command,
                    shell=True,
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(get_workspace_root()),
                )
                test_output = res.stdout + "\n" + res.stderr
                test_passed = True
            except subprocess.CalledProcessError as test_err:
                if backup_code is not None:
                    file_path.write_text(backup_code, encoding="utf-8")
                else:
                    file_path.unlink(missing_ok=True)
                return (
                    False,
                    f"❌ Verification tests failed:\n{test_err.stdout}\n{test_err.stderr}",
                    False,
                )
        else:
            test_output = "No test command specified. Compilation check passed."

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
                        return (
                            True,
                            f"⚠️ Skill saved but no @tool instances found in {skill_name}.py.",
                            test_passed,
                        )

                    return (
                        True,
                        (
                            f"✓ Skill '{skill_name}' forged successfully!\n"
                            f"Test Output:\n{test_output}\n"
                            f"Loaded tools: {', '.join(tools_loaded)}"
                        ),
                        test_passed,
                    )
            except ModuleNotFoundError as e:
                missing_mod = e.name
                top_level_mod = missing_mod.split(".")[0] if missing_mod else None
                if top_level_mod and top_level_mod not in {"agent_framework", "jarvis"} and attempt < max_retries - 1:
                    if install_dependency(top_level_mod):
                        continue
                if backup_code is not None:
                    file_path.write_text(backup_code, encoding="utf-8")
                else:
                    file_path.unlink(missing_ok=True)
                return False, f"❌ Failed to load module after writing: {e}", False
            except Exception as load_err:
                if backup_code is not None:
                    file_path.write_text(backup_code, encoding="utf-8")
                else:
                    file_path.unlink(missing_ok=True)
                return False, f"❌ Failed to load module after writing: {load_err}", False

        return False, "❌ Failed to load module after writing.", False
    except Exception as e:
        if backup_code is not None:
            file_path.write_text(backup_code, encoding="utf-8")
        return False, f"❌ Unexpected error during forging: {e}", False


def forge_to_staging(
    skill_name: str,
    code: str,
    staging_dir: Path,
    test_command: Optional[str] = None,
) -> tuple[bool, str, bool]:
    """Forge a skill into a staging directory (pray/ or dream/). Requires test_command."""
    file_path = Path(staging_dir) / f"{skill_name}.py"
    return _forge_skill_to_path(
        skill_name,
        code,
        file_path,
        test_command,
        require_test=True,
    )


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
    skills_dir = get_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    file_path = skills_dir / f"{skill_name}.py"
    ok, report, _ = _forge_skill_to_path(skill_name, code, file_path, test_command)
    return report
