/**
 * Gesture Controller -> LightronOrb -> DOM.
 */
const orbEl = document.getElementById("orb");

const state = {
  thinking: false,
  backendState: "idle",
  targetZoom: 0,
  zoom: 0,
  targetEnergy: 0,
  energy: 0,
};

const MIN_ZOOM_SCALE = 0.25;
const MAX_ZOOM_SCALE = 2.6;
const THINKING_SCALE = 1.18;
const SMOOTHING = 0.18;

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function layerOpacity(zoom, start, end) {
  if (zoom <= start) return 0;
  if (zoom >= end) return 1;
  return (zoom - start) / (end - start);
}

function setThinking(isThinking) {
  state.thinking = !!isThinking;
}

function setState(nextState) {
  state.backendState = nextState || "idle";
  state.thinking = state.backendState === "thinking";
  orbEl.dataset.backendState = state.backendState;
}

function setGesture({ zoom = 0, interactionStrength = 0 } = {}) {
  state.targetZoom = clamp(zoom, 0, 1);
  state.targetEnergy = clamp(interactionStrength, 0, 1);
}

function reset() {
  state.targetZoom = 0;
  state.targetEnergy = 0;
}

window.LightronOrb = { setThinking, setState, setGesture, reset };

function tick() {
  state.zoom = lerp(state.zoom, state.targetZoom, SMOOTHING);
  state.energy = lerp(state.energy, state.targetEnergy, SMOOTHING);

  const thinkingMultiplier = state.thinking ? THINKING_SCALE : 1;
  const zoomMultiplier =
    MIN_ZOOM_SCALE + state.zoom * (MAX_ZOOM_SCALE - MIN_ZOOM_SCALE);

  orbEl.style.setProperty(
    "--orb-scale",
    (thinkingMultiplier * zoomMultiplier).toFixed(3)
  );

  orbEl.style.setProperty("--layer-outer", layerOpacity(state.zoom, 0.0, 0.3).toFixed(3));
  orbEl.style.setProperty("--layer-energy", layerOpacity(state.zoom, 0.15, 0.45).toFixed(3));
  orbEl.style.setProperty("--layer-particles", layerOpacity(state.zoom, 0.35, 0.6).toFixed(3));
  orbEl.style.setProperty("--layer-inner", layerOpacity(state.zoom, 0.5, 0.75).toFixed(3));
  orbEl.style.setProperty("--layer-orbit", layerOpacity(state.zoom, 0.65, 0.85).toFixed(3));
  orbEl.style.setProperty("--layer-nucleus", layerOpacity(state.zoom, 0.8, 1.0).toFixed(3));
  orbEl.style.setProperty("--nucleus-scale", (0.4 + state.zoom * 0.8).toFixed(3));

  orbEl.classList.toggle("gesture-active", state.energy > 0.15);
  requestAnimationFrame(tick);
}

requestAnimationFrame(tick);
