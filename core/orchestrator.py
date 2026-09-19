
"""
OGGY Orchestrator.

Coordinates:

    user message
        ↓
    conversation context
        ↓
    LLM
        ↓
    tool request
        ↓
    Tool Registry
        ↓
    Permission Layer
        ↓
    ┌───────────────┬────────────────┐
    │ SAFE          │ MODERATE       │
    │ execute       │ ask user       │
    │ automatically │ for approval   │
    └───────────────┴────────────────┘
        ↓
    tool result
        ↓
    LLM
        ↓
    final response

The orchestrator does NOT directly execute tool handlers.

All tool execution goes through tools.registry.

The registry is responsible for enforcing permissions.
"""

from typing import Any, Dict

from config import config

from core.context import conversation
from core.llm import get_llm_provider
from core.state import OggyState, state_manager

from memory.memory import memory_store

from oggy_logging.logger import audit_logger

from tools.registry import registry


# ======================================================================
# SYSTEM PROMPT
# ======================================================================

SYSTEM_PROMPT = """
You are OGGY, a personal AI computer assistant created by Mahendiran.

Always address the user as "sir".

Example:

    "Hello sir, how can I help you today?"

============================================================
IDENTITY
============================================================

You are an AI assistant that can:

- Talk normally with the user.
- Inspect the user's filesystem.
- Read files.
- Search files.
- Create files.
- Edit files.
- Create folders.
- Rename files.
- Move files.
- Delete files.
- Use approved development commands.

You may inspect OGGY's own source files when the filesystem tools
allow access to them.

============================================================
IMPORTANT TOOL RULES
============================================================

1. Only request tools that are actually necessary.

2. Never claim that you performed an action unless the tool result
   confirms that the action succeeded.

3. Reading and inspecting files is allowed when the corresponding
   tool permits it.

4. File modifications may require the user's confirmation.

5. Never attempt to bypass the permission system.

6. Never attempt to execute a blocked tool indirectly.

7. If a tool request is returned as "pending confirmation", clearly
   tell the user what OGGY wants to do and wait for approval.

8. Do not repeatedly request the same failed tool.

9. If a tool fails, explain the failure clearly.

10. Do not silently retry dangerous or destructive operations.

11. When editing code, inspect the relevant file first when possible.

12. When modifying OGGY itself, explain what file you intend to change
    if user confirmation is required.

============================================================
FILESYSTEM BEHAVIOR
============================================================

When asked to find something:

    list_files
    search_files

When asked to read something:

    read_file

When asked to create something:

    create_file
    create_folder

When asked to modify something:

    edit_file

When asked to rename something:

    rename_file

When asked to move something:

    move_file

When asked to delete something:

    delete_file

Use the smallest number of tools necessary.

============================================================
RESPONSE STYLE
============================================================

Be concise.

You are embedded inside a desktop assistant UI.

Do not generate unnecessary reports.

Speak naturally and clearly.
"""


# ======================================================================
# EXCEPTIONS
# ======================================================================

class AgentStepLimitReached(Exception):
    """
    Raised when OGGY exceeds MAX_AGENT_STEPS.
    """

    pass


# ======================================================================
# MAIN MESSAGE HANDLER
# ======================================================================

def handle_message(user_text: str) -> Dict[str, Any]:
    """
    Run one complete OGGY turn.

    Returns:

        {
            "reply": "...",
            "pending_confirmation": {...} | None
        }

    SAFE tools execute automatically.

    MODERATE/DANGEROUS tools return a pending confirmation.
    """

    # --------------------------------------------------------------
    # Add user message
    # --------------------------------------------------------------

    conversation.add_user_message(
        user_text
    )

    state_manager.set(
        OggyState.THINKING
    )

    provider = get_llm_provider()

    tool_schemas = registry.llm_schemas()


    # --------------------------------------------------------------
    # Agent loop
    # --------------------------------------------------------------

    for step in range(
        config.MAX_AGENT_STEPS
    ):

        try:

            response = provider.send(

                messages=conversation.as_list(),

                tools=tool_schemas,

                system_prompt=SYSTEM_PROMPT,
            )

        except Exception as e:

            state_manager.set(
                OggyState.ERROR
            )

            return {
                "reply": (
                    f"Sorry sir, I couldn't contact "
                    f"the AI provider: {e}"
                ),

                "pending_confirmation": None,
            }


        # ----------------------------------------------------------
        # Save assistant response
        # ----------------------------------------------------------

        conversation.add_assistant_message(
            response.raw_content
        )


        # ----------------------------------------------------------
        # No tool call
        # ----------------------------------------------------------

        if not response.tool_calls:

            state_manager.set(
                OggyState.RESPONDING
            )

            reply = response.text or ""

            state_manager.set(
                OggyState.IDLE
            )

            return {
                "reply": reply,
                "pending_confirmation": None,
            }


        # ----------------------------------------------------------
        # Process tool calls
        # ----------------------------------------------------------

        for call in response.tool_calls:

            outcome = _handle_tool_call(
                user_text,
                call,
            )


            # ------------------------------------------------------
            # Permission required
            # ------------------------------------------------------

            if outcome.get(
                "pending_confirmation"
            ):

                state_manager.set(
                    OggyState.WAITING_FOR_PERMISSION
                )

                return {
                    "reply": outcome["reply"],

                    "pending_confirmation":
                        outcome["pending_confirmation"],
                }


            # ------------------------------------------------------
            # Feed result back to LLM
            # ------------------------------------------------------

            conversation.add_tool_result(

                tool_use_id=call["id"],

                content=outcome["reply"],

                is_error=outcome.get(
                    "is_error",
                    False,
                ),
            )


        # ----------------------------------------------------------
        # Continue thinking
        # ----------------------------------------------------------

        state_manager.set(
            OggyState.THINKING
        )


    # ==================================================================
    # Step limit reached
    # ==================================================================

    state_manager.set(
        OggyState.ERROR
    )

    return {

        "reply": (
            f"I stopped after "
            f"{config.MAX_AGENT_STEPS} steps "
            f"without finishing the task, sir."
        ),

        "pending_confirmation": None,
    }


# ======================================================================
# HANDLE TOOL CALL
# ======================================================================

def _handle_tool_call(
    user_text: str,
    call: Dict[str, Any],
) -> Dict[str, Any]:

    tool_name = call.get(
        "name"
    )

    arguments = call.get(
        "input",
        {},
    )

    tool_use_id = call.get(
        "id"
    )


    # --------------------------------------------------------------
    # Validate tool name
    # --------------------------------------------------------------

    tool = registry.get(
        tool_name
    )

    if tool is None:

        return {

            "reply": (
                f"Unknown tool requested: "
                f"{tool_name}"
            ),

            "is_error": True,
        }


    # --------------------------------------------------------------
    # Execute through registry
    #
    # IMPORTANT:
    #
    # We DO NOT call permission_manager.evaluate() here.
    #
    # registry.execute() is now the central permission gate.
    # --------------------------------------------------------------

    state_manager.set(
        OggyState.EXECUTING_TOOL,
        detail=tool_name,
    )


    result = registry.execute(

        name=tool_name,

        arguments=arguments,

        tool_use_id=tool_use_id,
    )


    # --------------------------------------------------------------
    # Confirmation required
    # --------------------------------------------------------------

    if result.requires_confirmation:

        pending = (
            permission_manager_pending(
                result.confirmation_id
            )
        )


        audit_logger.log_tool_call(

            user_text,

            tool_name,

            arguments,

            tool.risk_level.value,

            "pending",
        )


        if pending is None:

            return {

                "reply": (
                    "Sir, OGGY requested confirmation, "
                    "but the confirmation request could "
                    "not be found."
                ),

                "is_error": True,
            }


        return {

            "reply": (
                f"Sir, OGGY wants to run "
                f"'{tool_name}'. "
                f"Your confirmation is required."
            ),

            "pending_confirmation": {

                "id": pending.id,

                "tool": pending.tool_name,

                "arguments": pending.arguments,

                "risk_level":
                    pending.risk_level.value,

                "reason": pending.reason,
            },
        }


    # --------------------------------------------------------------
    # Blocked
    # --------------------------------------------------------------

    if not result.success:

        audit_logger.log_tool_call(

            user_text,

            tool_name,

            arguments,

            tool.risk_level.value,

            "blocked"
            if tool.risk_level.value == "blocked"
            else "error",

            result=result.data,

            error=result.error,
        )


        return {

            "reply": (
                result.error
                or "The tool failed."
            ),

            "is_error": True,
        }


    # --------------------------------------------------------------
    # Successful execution
    # --------------------------------------------------------------

    memory_store.record_tool_use(

        tool_name,

        arguments,

        result.success,

        summary=str(
            result.data
        )[:200],
    )


    audit_logger.log_tool_call(

        user_text,

        tool_name,

        arguments,

        tool.risk_level.value,

        "auto",

        result=result.data,

        error=result.error,
    )


    return {

        "reply": result.data,

        "is_error": False,
    }


# ======================================================================
# GET PENDING CONFIRMATION
# ======================================================================

def permission_manager_pending(
    confirmation_id: str,
):
    """
    Retrieve a pending permission request.

    Kept as a small helper so the orchestrator doesn't manipulate
    the permission manager's internal dictionary.
    """

    if not confirmation_id:

        return None


    from security.permissions import permission_manager

    return permission_manager.get_pending(
        confirmation_id
    )


# ======================================================================
# RESOLVE CONFIRMATION
# ======================================================================

def resolve_confirmation(
    confirmation_id: str,
    approved: bool,
) -> Dict[str, Any]:
    """
    Called by the permission API/UI.

    approved=True:
        Execute the previously requested tool.

    approved=False:
        Reject it.

    IMPORTANT:

        Approved tools are executed through
        registry.execute_confirmation().

        We DO NOT call registry.execute() here because that would
        create a NEW permission request for the same operation.
    """

    from security.permissions import permission_manager


    # --------------------------------------------------------------
    # Get pending request before resolving it
    # --------------------------------------------------------------

    pending = permission_manager.get_pending(
        confirmation_id
    )

    if pending is None:

        return {

            "reply": (
                "That confirmation has expired "
                "or was already handled, sir."
            ),

            "pending_confirmation": None,
        }


    # ==================================================================
    # DENIED
    # ==================================================================

    if not approved:

        denied = permission_manager.deny(
            confirmation_id
        )

        if denied is None:

            return {

                "reply": (
                    "That confirmation was already handled, sir."
                ),

                "pending_confirmation": None,
            }


        audit_logger.log_tool_call(

            "(user denied)",

            denied.tool_name,

            denied.arguments,

            denied.risk_level.value,

            "denied",
        )


        # ----------------------------------------------------------
        # Complete the pending LLM tool call.
        #
        # This is important for providers such as Anthropic that
        # expect a matching tool_result.
        # ----------------------------------------------------------

        if denied.tool_use_id:

            conversation.add_tool_result(

                denied.tool_use_id,

                "The user denied this action.",

                is_error=True,
            )


        state_manager.set(
            OggyState.IDLE
        )


        return {

            "reply": (
                f"Okay sir — I won't run "
                f"'{denied.tool_name}'."
            ),

            "pending_confirmation": None,
        }


    # ==================================================================
    # APPROVED
    # ==================================================================

    state_manager.set(

        OggyState.EXECUTING_TOOL,

        detail=pending.tool_name,
    )


    # --------------------------------------------------------------
    # Execute the already-approved request.
    #
    # DO NOT use registry.execute() here.
    # --------------------------------------------------------------

    result = registry.execute_confirmation(
        confirmation_id
    )


    # --------------------------------------------------------------
    # Audit
    # --------------------------------------------------------------

    audit_logger.log_tool_call(

        "(user approved)",

        pending.tool_name,

        pending.arguments,

        pending.risk_level.value,

        "approved",

        result=result.data,

        error=result.error,
    )


    # --------------------------------------------------------------
    # Store memory
    # --------------------------------------------------------------

    memory_store.record_tool_use(

        pending.tool_name,

        pending.arguments,

        result.success,

        summary=str(
            result.data
        )[:200],
    )


    # --------------------------------------------------------------
    # Feed result into conversation
    # --------------------------------------------------------------

    if pending.tool_use_id:

        conversation.add_tool_result(

            pending.tool_use_id,

            (
                result.error
                if not result.success
                else result.data
            ),

            is_error=not result.success,
        )


    # ==================================================================
    # TOOL FAILED
    # ==================================================================

    if not result.success:

        state_manager.set(
            OggyState.ERROR
        )


        return {

            "reply": (
                f"Sorry sir, "
                f"'{pending.tool_name}' failed: "
                f"{result.error}"
            ),

            "pending_confirmation": None,
        }


    # ==================================================================
    # TOOL SUCCESS
    # ==================================================================

    # Give the LLM the opportunity to naturally explain the result.

    state_manager.set(
        OggyState.THINKING
    )


    try:

        provider = get_llm_provider()

        response = provider.send(

            messages=conversation.as_list(),

            tools=registry.llm_schemas(),

            system_prompt=SYSTEM_PROMPT,
        )


    except Exception as e:

        state_manager.set(
            OggyState.ERROR
        )

        return {

            "reply": (
                f"The action completed successfully, sir, "
                f"but I couldn't generate the final response: {e}"
            ),

            "pending_confirmation": None,
        }


    conversation.add_assistant_message(
        response.raw_content
    )


    # --------------------------------------------------------------
    # If the follow-up itself requests another tool
    # --------------------------------------------------------------

    if response.tool_calls:

        # Process the next tool request.

        for call in response.tool_calls:

            outcome = _handle_tool_call(
                "(continuation)",
                call,
            )


            if outcome.get(
                "pending_confirmation"
            ):

                state_manager.set(
                    OggyState.WAITING_FOR_PERMISSION
                )

                return {

                    "reply": outcome["reply"],

                    "pending_confirmation":
                        outcome[
                            "pending_confirmation"
                        ],
                }


            conversation.add_tool_result(

                tool_use_id=call["id"],

                content=outcome["reply"],

                is_error=outcome.get(
                    "is_error",
                    False,
                ),
            )


    # --------------------------------------------------------------
    # Final response
    # --------------------------------------------------------------

    state_manager.set(
        OggyState.RESPONDING
    )

    reply = response.text or "Done, sir."

    state_manager.set(
        OggyState.IDLE
    )


    return {

        "reply": reply,

        "pending_confirmation": None,
    }

