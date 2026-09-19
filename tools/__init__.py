"""
Importing tools.__init__ registers every built-in tool. Add new tool
modules (weather.py, github.py, ...) by writing a `register_x_tools()`
function there and calling it below - the orchestrator and LLM never
need to change.
"""

from tools.applications import register_application_tools
from tools.commands import register_command_tools
from tools.filesystem import register_filesystem_tools


def register_all_tools():
    register_filesystem_tools()
    register_command_tools()
    register_application_tools()
