/**
 * OGGY frontend app logic.
 * Backend/API behavior intentionally preserved.
 */
const STATE_POLL_MS = 800;

const logEl = document.getElementById("log");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const confirmBox = document.getElementById("confirmBox");
const confirmText = document.getElementById("confirmText");
const confirmApprove = document.getElementById("confirmApprove");
const confirmDeny = document.getElementById("confirmDeny");

let pendingConfirmationId = null;

function updateClock() {
  const clockEl = document.getElementById("clockDisplay");
  if (!clockEl) return;
  const now = new Date();
  clockEl.textContent = now.toLocaleTimeString();
}
setInterval(updateClock, 1000);
updateClock();

function appendLog(who, text, isError = false) {
  const entry = document.createElement("div");
  entry.className = `log-entry ${who}${isError ? " error" : ""}`;
  const whoLabel = document.createElement("span");
  whoLabel.className = "who";
  whoLabel.textContent = who === "user" ? "YOU" : "OGGY";
  entry.appendChild(whoLabel);
  entry.appendChild(document.createTextNode(formatText(text)));
  logEl.appendChild(entry);
  logEl.scrollTop = logEl.scrollHeight;
}

function formatText(text) {
  if (typeof text === "string") return text;
  try { return JSON.stringify(text, null, 2); }
  catch (e) { return String(text); }
}

async function pollState() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) return;
    const data = await res.json();
    setOrbState(data.state, data.detail);
  } catch (e) {}
}
setInterval(pollState, STATE_POLL_MS);
pollState();

function showConfirmation(pending) {
  pendingConfirmationId = pending.id;
  confirmText.textContent =
    `OGGY wants to run "${pending.tool}" ` +
    `(${pending.risk_level}) with: ${formatText(pending.arguments)}`;
  confirmBox.hidden = false;
}

function hideConfirmation() {
  pendingConfirmationId = null;
  confirmBox.hidden = true;
}

async function sendMessage(message) {
  appendLog("user", message);
  chatInput.value = "";
  chatInput.disabled = true;
  setThinking(true);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();

    if (!res.ok) {
      appendLog("oggy", data.error || "Something went wrong.", true);
      return;
    }

    if (data.pending_confirmation) {
      appendLog("oggy", data.reply);
      showConfirmation(data.pending_confirmation);
    } else {
      appendLog("oggy", data.reply);
    }
  } catch (e) {
    appendLog("oggy", "Could not reach OGGY\'s backend.", true);
  } finally {
    setThinking(false);
    chatInput.disabled = false;
    chatInput.focus();
  }
}

function setThinking(isThinking) {
  window.LightronOrb?.setThinking(isThinking);
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  sendMessage(message);
});

async function respondToConfirmation(approved) {
  if (!pendingConfirmationId) return;
  const id = pendingConfirmationId;
  hideConfirmation();

  try {
    const res = await fetch("/api/permission/response", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, approved }),
    });
    const data = await res.json();
    if (!res.ok) {
      appendLog("oggy", data.error || "Something went wrong.", true);
      return;
    }
    appendLog("oggy", data.reply);
  } catch (e) {
    appendLog("oggy", "Could not reach OGGY\'s backend.", true);
  }
}

confirmApprove.addEventListener("click", () => respondToConfirmation(true));
confirmDeny.addEventListener("click", () => respondToConfirmation(false));

appendLog("oggy", "OGGY is online. Ask me to look at your files, or just say hello.");
