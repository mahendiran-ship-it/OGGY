"""
Command execution tool.

This is deliberately the most locked-down tool in OGGY:

  1. Only executables named in config.ALLOWED_COMMANDS may ever run.
  2. Arguments are passed as a list (never shell=True / a raw string),
     so there is no shell-injection surface.
  3. The tool's risk level is DANGEROUS, so the permission layer always
     requires explicit user confirmation before execution - regardless
     of what the LLM decided to request.
  4. Execution has a hard timeout and captured, size-limited output.

The LLM can never expand ALLOWED_COMMANDS - that only changes via
config/environment, which the LLM has no access to.
"""

import shlex
import subprocess

from config import config
from security.path_guard import PathViolation, resolve_safe_path
from security.permissions import PermissionLevel
from tools.registry import Tool, ToolError, ToolResult, registry

MAX_OUTPUT_CHARS = 20_000


def run_command(command: str, working_directory: str = ".") -> ToolResult:
    try:
        parts = shlex.split(command)
    except ValueError as e:
        raise ToolError(f"Could not parse command: {e}")

    if not parts:
        raise ToolError("Empty command.")

    executable = parts[0]
    if executable not in config.ALLOWED_COMMANDS:
        raise ToolError(
            f"'{executable}' is not on the allowed command list. "
            f"Allowed: {', '.join(sorted(config.ALLOWED_COMMANDS))}"
        )

    try:
        cwd = resolve_safe_path(working_directory)
    except PathViolation as e:
        raise ToolError(str(e))

    try:
        proc = subprocess.run(
            parts,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=config.COMMAND_TIMEOUT_SECONDS,
            shell=False,  # never True - `parts` is an argv list, not a shell string
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"Command timed out after {config.COMMAND_TIMEOUT_SECONDS}s.")
    except FileNotFoundError:
        raise ToolError(f"Executable not found: {executable}")

    stdout = proc.stdout[:MAX_OUTPUT_CHARS]
    stderr = proc.stderr[:MAX_OUTPUT_CHARS]

    return ToolResult(
        success=proc.returncode == 0,
        data={
            "command": command,
            "cwd": str(cwd),
            "return_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        },
        error=None if proc.returncode == 0 else f"Command exited with code {proc.returncode}",
    )


def register_command_tools():
    registry.register(Tool(
        name="run_command",
        description=(
            "Run an allow-listed development command (e.g. python, pip, git, npm, pytest) "
            "inside the OGGY workspace. Always requires user confirmation before running."
        ),
        parameters={
            "command": {"type": "string", "description": "The full command to run, e.g. 'pytest -q'."},
            "working_directory": {"type": "string", "description": "Directory to run it in, relative to the workspace root."},
        },
        risk_level=PermissionLevel.DANGEROUS,
        handler=run_command,
        required=["command"],
    ))
