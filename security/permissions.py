
"""
OGGY Permission Layer.

This module is the central authority for deciding whether a tool call:

    SAFE
        -> executes automatically

    MODERATE
        -> requires explicit user confirmation

    DANGEROUS
        -> requires explicit user confirmation and should be logged

    BLOCKED
        -> can never execute

The LLM cannot bypass this layer.

The LLM only requests:

    tool_name + arguments

The permission manager decides whether the tool is allowed to execute.
"""

import time
import uuid

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


# ======================================================================
# Permission Levels
# ======================================================================

class PermissionLevel(str, Enum):

    SAFE = "safe"

    MODERATE = "moderate"

    DANGEROUS = "dangerous"

    BLOCKED = "blocked"


# ======================================================================
# Pending Confirmation
# ======================================================================

@dataclass
class PendingConfirmation:

    id: str

    tool_name: str

    arguments: Dict[str, Any]

    risk_level: PermissionLevel

    reason: str

    tool_use_id: Optional[str] = None

    created_at: float = field(
        default_factory=time.time
    )


# ======================================================================
# Permission Denied
# ======================================================================

class PermissionDenied(Exception):
    """
    Raised when an operation is blocked or explicitly denied.
    """

    pass


# ======================================================================
# Permission Decision
# ======================================================================

@dataclass
class PermissionDecision:

    allowed: bool

    requires_confirmation: bool

    pending: Optional[PendingConfirmation]

    reason: str


# ======================================================================
# Permission Manager
# ======================================================================

class PermissionManager:
    """
    Central permission controller for OGGY.

    Important:

        This class DOES NOT execute tools.

        It only decides whether execution should happen.
    """

    def __init__(self):

        self._pending: Dict[
            str,
            PendingConfirmation
        ] = {}


    # ------------------------------------------------------------------
    # Evaluate Tool Request
    # ------------------------------------------------------------------

    def evaluate(
        self,
        tool_name: str,
        risk_level: PermissionLevel,
        arguments: Dict[str, Any],
        tool_use_id: Optional[str] = None,
    ) -> PermissionDecision:

        # --------------------------------------------------------------
        # BLOCKED
        # --------------------------------------------------------------

        if risk_level == PermissionLevel.BLOCKED:

            return PermissionDecision(
                allowed=False,
                requires_confirmation=False,
                pending=None,
                reason=(
                    f"'{tool_name}' is a blocked action "
                    f"and cannot be executed."
                ),
            )


        # --------------------------------------------------------------
        # SAFE
        # --------------------------------------------------------------

        if risk_level == PermissionLevel.SAFE:

            return PermissionDecision(
                allowed=True,
                requires_confirmation=False,
                pending=None,
                reason="",
            )


        # --------------------------------------------------------------
        # MODERATE / DANGEROUS
        # --------------------------------------------------------------

        pending = PendingConfirmation(

            id=str(
                uuid.uuid4()
            ),

            tool_name=tool_name,

            arguments=dict(arguments),

            risk_level=risk_level,

            reason=(
                f"OGGY wants to run '{tool_name}'. "
                f"Your confirmation is required."
            ),

            tool_use_id=tool_use_id,
        )


        self._pending[pending.id] = pending


        return PermissionDecision(

            allowed=False,

            requires_confirmation=True,

            pending=pending,

            reason=pending.reason,
        )


    # ------------------------------------------------------------------
    # Approve Confirmation
    # ------------------------------------------------------------------

    def approve(
        self,
        confirmation_id: str,
    ) -> Optional[PendingConfirmation]:
        """
        Approve and consume a pending confirmation.

        The caller receives the original tool request and can then
        execute it through the normal tool registry.
        """

        pending = self._pending.pop(
            confirmation_id,
            None
        )

        if pending is None:
            return None

        return pending


    # ------------------------------------------------------------------
    # Deny Confirmation
    # ------------------------------------------------------------------

    def deny(
        self,
        confirmation_id: str,
    ) -> Optional[PendingConfirmation]:
        """
        Deny and consume a pending confirmation.

        Returns the original request so the caller can notify OGGY
        that the operation was denied.
        """

        pending = self._pending.pop(
            confirmation_id,
            None
        )

        return pending


    # ------------------------------------------------------------------
    # Backwards-compatible resolve()
    # ------------------------------------------------------------------

    def resolve(
        self,
        confirmation_id: str,
        approved: bool,
    ) -> Optional[PendingConfirmation]:
        """
        Resolve a pending confirmation.

        approved=True:
            Approves the operation.

        approved=False:
            Denies the operation.

        The actual tool execution MUST happen outside this class.
        """

        if approved:

            return self.approve(
                confirmation_id
            )

        return self.deny(
            confirmation_id
        )


    # ------------------------------------------------------------------
    # Get Pending Confirmation
    # ------------------------------------------------------------------

    def get_pending(
        self,
        confirmation_id: str,
    ) -> Optional[PendingConfirmation]:

        return self._pending.get(
            confirmation_id
        )


    # ------------------------------------------------------------------
    # List Pending Confirmations
    # ------------------------------------------------------------------

    def list_pending(self):

        return list(
            self._pending.values()
        )


    # ------------------------------------------------------------------
    # Clear All Pending Requests
    # ------------------------------------------------------------------

    def clear_pending(self):

        self._pending.clear()


# ======================================================================
# Global Permission Manager
# ======================================================================

permission_manager = PermissionManager()
