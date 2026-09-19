/**
 * OGGY state controller.
 */
const STATE_LABELS = {
  idle: "IDLE",
  listening: "LISTENING",
  thinking: "THINKING",
  responding: "RESPONDING",
  executing_tool: "EXECUTING",
  waiting_for_permission: "AWAITING APPROVAL",
  error: "ERROR",
};

function setOrbState(state, detail) {
  const orbWrap = document.getElementById("orbWrap");
  const label = document.getElementById("statusLabel");
  if (!orbWrap || !label) return;

  orbWrap.setAttribute("data-state", state);
  const text = STATE_LABELS[state] || String(state || "idle").toUpperCase();
  label.textContent = detail ? `${text} — ${detail}` : text;

  window.LightronOrb?.setState(state);
}
