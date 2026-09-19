
"""
OGGY Tool Registry.

Every capability OGGY has is registered here as a Tool.

Each Tool contains:

    - name
    - description
    - parameter schema
    - risk level
    - handler

The registry is also the final execution gate.

Permission flow:

    SAFE
        -> execute immediately

    MODERATE
        -> create confirmation request
        -> DO NOT execute

    DANGEROUS
        -> create confirmation request
        -> DO NOT execute

    BLOCKED
        -> never execute

The LLM never receives a direct Python reference to a handler.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from security.permissions import (
    PermissionLevel,
    PermissionDecision,
    PendingConfirmation,
    permission_manager,
)


# ======================================================================
# Errors
# ======================================================================

class ToolError(Exception):
    """
    Expected tool failure.

    Examples:

        file not found
        invalid path
        command not allowed
        invalid arguments
    """

    pass


class ToolValidationError(ToolError):
    """
    Tool arguments do not match the required schema.
    """

    pass


# ======================================================================
# Tool Result
# ======================================================================

@dataclass
class ToolResult:

    success: bool

    data: Any = None

    error: Optional[str] = None

    # Used when a tool is waiting for user confirmation.
    requires_confirmation: bool = False

    confirmation_id: Optional[str] = None

    @classmethod
    def confirmation_required(
        cls,
        pending: PendingConfirmation,
    ):

        return cls(

            success=False,

            data={
                "tool_name": pending.tool_name,
                "arguments": pending.arguments,
                "risk_level": pending.risk_level.value,
                "reason": pending.reason,
            },

            error=pending.reason,

            requires_confirmation=True,

            confirmation_id=pending.id,
        )


    def to_dict(self) -> Dict[str, Any]:

        return {
            "success": self.success,

            "data": self.data,

            "error": self.error,

            "requires_confirmation": self.requires_confirmation,

            "confirmation_id": self.confirmation_id,
        }


# ======================================================================
# Tool Definition
# ======================================================================

@dataclass
class Tool:

    name: str

    description: str

    parameters: Dict[str, Any]

    risk_level: PermissionLevel

    handler: Callable[..., ToolResult]

    required: List[str] = None


    # ------------------------------------------------------------------
    # LLM schema
    # ------------------------------------------------------------------

    def to_llm_schema(self) -> Dict[str, Any]:

        return {
            "name": self.name,

            "description": self.description,

            "input_schema": {
                "type": "object",

                "properties": self.parameters,

                "required": self.required or [],
            },
        }


    # ------------------------------------------------------------------
    # Argument validation
    # ------------------------------------------------------------------

    def validate(
        self,
        arguments: Dict[str, Any],
    ) -> None:

        if not isinstance(arguments, dict):

            raise ToolValidationError(
                f"Arguments for '{self.name}' must be an object."
            )

        missing = [
            required_name
            for required_name in (self.required or [])
            if required_name not in arguments
        ]

        if missing:

            raise ToolValidationError(
                f"Missing required argument(s) for "
                f"'{self.name}': {', '.join(missing)}"
            )


# ======================================================================
# Tool Registry
# ======================================================================

class ToolRegistry:

    def __init__(self):

        self._tools: Dict[str, Tool] = {}


    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    def register(
        self,
        tool: Tool,
    ):

        if tool.name in self._tools:

            raise ValueError(
                f"Tool '{tool.name}' is already registered."
            )

        self._tools[tool.name] = tool


    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> Optional[Tool]:

        return self._tools.get(name)


    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Tool]:

        return list(
            self._tools.values()
        )


    # ------------------------------------------------------------------
    # LLM Schemas
    # ------------------------------------------------------------------

    def llm_schemas(
        self,
    ) -> List[Dict[str, Any]]:

        return [
            tool.to_llm_schema()
            for tool in self._tools.values()
        ]


    # ------------------------------------------------------------------
    # Permission evaluation
    # ------------------------------------------------------------------

    def check_permission(
        self,
        name: str,
        arguments: Dict[str, Any],
        tool_use_id: Optional[str] = None,
    ) -> PermissionDecision:

        tool = self.get(name)

        if tool is None:

            return PermissionDecision(

                allowed=False,

                requires_confirmation=False,

                pending=None,

                reason=f"Unknown tool: '{name}'",
            )

        return permission_manager.evaluate(

            tool_name=name,

            risk_level=tool.risk_level,

            arguments=arguments,

            tool_use_id=tool_use_id,
        )


    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        tool_use_id: Optional[str] = None,
    ) -> ToolResult:
        """
        Execute a tool only when permission allows it.

        SAFE:
            Executes immediately.

        MODERATE/DANGEROUS:
            Creates a pending confirmation.
            The handler is NOT executed.

        BLOCKED:
            Never executes.
        """

        tool = self.get(name)

        if tool is None:

            return ToolResult(
                success=False,
                error=f"Unknown tool: '{name}'",
            )


        # --------------------------------------------------------------
        # Validate arguments BEFORE asking for permission.
        # --------------------------------------------------------------

        try:

            tool.validate(arguments)

        except ToolError as e:

            return ToolResult(
                success=False,
                error=str(e),
            )


        # --------------------------------------------------------------
        # Permission check
        # --------------------------------------------------------------

        decision = permission_manager.evaluate(

            tool_name=name,

            risk_level=tool.risk_level,

            arguments=arguments,

            tool_use_id=tool_use_id,
        )


        # --------------------------------------------------------------
        # BLOCKED
        # --------------------------------------------------------------

        if not decision.allowed and not decision.requires_confirmation:

            return ToolResult(
                success=False,
                error=decision.reason,
            )


        # --------------------------------------------------------------
        # MODERATE / DANGEROUS
        # --------------------------------------------------------------

        if decision.requires_confirmation:

            return ToolResult.confirmation_required(
                decision.pending
            )


        # --------------------------------------------------------------
        # SAFE
        # --------------------------------------------------------------

        try:

            return tool.handler(
                **arguments
            )

        except ToolError as e:

            return ToolResult(
                success=False,
                error=str(e),
            )

        except Exception as e:

            return ToolResult(
                success=False,
                error=(
                    f"Unexpected error in "
                    f"'{name}': {e}"
                ),
            )


    # ------------------------------------------------------------------
    # Execute approved confirmation
    # ------------------------------------------------------------------

    def execute_confirmation(
        self,
        confirmation_id: str,
    ) -> ToolResult:
        """
        Execute a previously approved confirmation.

        The UI/orchestrator should call:

            permission_manager.approve(...)

        and then pass the returned request here.

        This method executes ONLY an already-approved request.
        """

        pending = permission_manager.get_pending(
            confirmation_id
        )

        if pending is None:

            return ToolResult(
                success=False,
                error=(
                    "Confirmation does not exist "
                    "or has already been resolved."
                ),
            )


        # Consume/approve the confirmation.
        approved = permission_manager.approve(
            confirmation_id
        )

        if approved is None:

            return ToolResult(
                success=False,
                error="Unable to approve confirmation.",
            )


        tool = self.get(
            approved.tool_name
        )

        if tool is None:

            return ToolResult(
                success=False,
                error=(
                    f"Tool '{approved.tool_name}' "
                    f"no longer exists."
                ),
            )


        # --------------------------------------------------------------
        # Execute approved tool
        # --------------------------------------------------------------

        try:

            tool.validate(
                approved.arguments
            )

            return tool.handler(
                **approved.arguments
            )

        except ToolError as e:

            return ToolResult(
                success=False,
                error=str(e),
            )

        except Exception as e:

            return ToolResult(
                success=False,
                error=(
                    f"Unexpected error in "
                    f"'{approved.tool_name}': {e}"
                ),
            )


    # ------------------------------------------------------------------
    # Deny confirmation
    # ------------------------------------------------------------------

    def deny_confirmation(
        self,
        confirmation_id: str,
    ) -> ToolResult:
        """
        Deny a pending tool request.
        """

        pending = permission_manager.deny(
            confirmation_id
        )

        if pending is None:

            return ToolResult(
                success=False,
                error=(
                    "Confirmation does not exist "
                    "or has already been resolved."
                ),
            )

        return ToolResult(
            success=False,

            error=(
                f"User denied execution of "
                f"'{pending.tool_name}'."
            ),

            data={
                "tool_name": pending.tool_name,
                "denied": True,
            },
        )


    # ------------------------------------------------------------------
    # Pending confirmations
    # ------------------------------------------------------------------

    def pending_confirmations(
        self,
    ):

        return permission_manager.list_pending()


# ======================================================================
# Global Registry
# ======================================================================

registry = ToolRegistry()
