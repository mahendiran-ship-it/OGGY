"""
Application control tool.

Allows OGGY to open applications registered with Windows Start Apps.
The tool returns a ToolResult so OGGY's permission/execution system
can correctly process the result.
"""

import subprocess

from security.permissions import PermissionLevel
from tools.registry import Tool, ToolError, ToolResult, registry


def open_application(name: str) -> ToolResult:
    name = name.strip().lower()

    # Get applications registered with Windows
    result = subprocess.run(
        ["powershell", "-Command", "Get-StartApps"],
        capture_output=True,
        text=True,
        timeout=10
    )

    if result.returncode != 0:
        raise ToolError("Could not read Windows Start Apps.")

    # Search for the requested application
    for line in result.stdout.splitlines():

        line = line.strip()

        if not line:
            continue

        parts = line.split()

        # A valid Start App entry needs at least a name + AppID
        if len(parts) < 2:
            continue

        app_id = parts[-1]
        app_name = " ".join(parts[:-1])

        # Match user's requested application
        if name in app_name.lower():

            try:
                subprocess.Popen([
                    "explorer.exe",
                    f"shell:AppsFolder\\{app_id}"
                ])

            except OSError as e:
                raise ToolError(
                    f"Failed to launch '{app_name}': {e}"
                )

            # IMPORTANT:
            # OGGY expects a ToolResult.
            return ToolResult(
                success=True,
                data={
                    "application": app_name,
                    "launched": True
                }
            )

    # Nothing matched
    raise ToolError(
        f"Could not find an installed application matching '{name}'."
    )


def register_application_tools():
    registry.register(
        Tool(
            name="open_application",
            description="Open an installed Windows application. Requires confirmation.",
            parameters={
                "name": {
                    "type": "string",
                    "description": "Application name, e.g. 'WhatsApp' or 'Chrome'."
                }
            },
            risk_level=PermissionLevel.MODERATE,
            handler=open_application,
            required=["name"],
        )
    )