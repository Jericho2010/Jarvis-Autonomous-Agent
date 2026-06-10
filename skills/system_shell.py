import subprocess
import os
from agent_framework import tool

@tool(approval_mode="never_require")
def execute_bash(command: str) -> str:
    """
    Executes a bash command on the host OS. Use this to run builds, tests, or navigate the system.
    Args:
        command: The bash command to run (e.g. 'ls -la', 'uv pip list').
    Returns:
        The standard output and standard error of the command.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd="/home/shaun/jarvis"
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        return output if output else "Command executed successfully (no output)."
    except Exception as e:
        return f"Execution failed: {str(e)}"
