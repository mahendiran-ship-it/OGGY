"""
Flask API routes.

Deliberately thin: every route just validates the HTTP-level input and
delegates to core.orchestrator / core.state. No orchestration logic
lives here, so the API can evolve (e.g. add auth, switch to websockets)
without touching the agent loop.
"""

from flask import Blueprint, jsonify, request

from core import orchestrator
from core.state import state_manager

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Missing 'message'."}), 400

    try:
        result = orchestrator.handle_message(message)
    except Exception as e:  # noqa: BLE001 - never let the API crash on a bad turn
        return jsonify({"error": f"OGGY hit an unexpected error: {e}"}), 500

    return jsonify(result)


@api_bp.route("/state", methods=["GET"])
def get_state():
    return jsonify(state_manager.get())


@api_bp.route("/permission/response", methods=["POST"])
def permission_response():
    payload = request.get_json(silent=True) or {}
    confirmation_id = payload.get("id")
    approved = bool(payload.get("approved"))

    if not confirmation_id:
        return jsonify({"error": "Missing 'id'."}), 400

    try:
        result = orchestrator.resolve_confirmation(confirmation_id, approved)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"OGGY hit an unexpected error: {e}"}), 500

    return jsonify(result)


@api_bp.route("/tools", methods=["GET"])
def list_tools():
    from tools.registry import registry
    return jsonify([
        {"name": t.name, "description": t.description, "risk_level": t.risk_level.value}
        for t in registry.list_tools()
    ])
