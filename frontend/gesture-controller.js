/**
 * Lightron gesture control for OGGY.
 * Camera -> MediaPipe -> pinch distance -> smoothing -> LightronOrb.
 * No camera preview and no video is uploaded.
 */
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
const WASM_URL =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";

const EMA_ALPHA = 0.35;
const THUMB_TIP = 4;
const INDEX_TIP = 8;
const WRIST = 0;
const INDEX_MCP = 5;
const HAND_LOST_TIMEOUT_MS = 400;

let smoothedPinch = null;
let lastSeenAt = 0;

async function main() {
  let vision, HandLandmarker;

  try {
    ({ HandLandmarker, FilesetResolver: vision } = await import(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs"
    ));
  } catch (err) {
    console.warn("OGGY gesture control: MediaPipe could not load.", err);
    return;
  }

  const video = document.getElementById("gesture-camera");
  if (!video || !navigator.mediaDevices?.getUserMedia) return;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 480, height: 360, facingMode: "user" },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
  } catch (err) {
    console.warn("OGGY gesture control: camera unavailable/permission denied.", err);
    return;
  }

  let handLandmarker;
  try {
    const filesetResolver = await vision.forVisionTasks(WASM_URL);
    handLandmarker = await HandLandmarker.createFromOptions(filesetResolver, {
      baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
      runningMode: "VIDEO",
      numHands: 1,
    });
  } catch (err) {
    console.warn("OGGY gesture control: hand model initialization failed.", err);
    return;
  }

  const loop = (now) => {
    processFrame(handLandmarker, video, now);
    if (typeof video.requestVideoFrameCallback === "function") {
      video.requestVideoFrameCallback(loop);
    } else {
      requestAnimationFrame(() => loop(performance.now()));
    }
  };

  if (typeof video.requestVideoFrameCallback === "function") {
    video.requestVideoFrameCallback(loop);
  } else {
    requestAnimationFrame(() => loop(performance.now()));
  }
}

function processFrame(handLandmarker, video, now) {
  if (video.readyState < 2) return;

  const result = handLandmarker.detectForVideo(video, now);
  const hand = result?.landmarks?.[0];

  if (!hand) {
    if (now - lastSeenAt > HAND_LOST_TIMEOUT_MS) {
      window.LightronOrb?.setGesture({
        zoom: smoothedPinch ?? 0,
        interactionStrength: 0,
      });
    }
    return;
  }

  lastSeenAt = now;

  const thumbTip = hand[THUMB_TIP];
  const indexTip = hand[INDEX_TIP];
  const wrist = hand[WRIST];
  const indexMcp = hand[INDEX_MCP];

  const handScale = distance(wrist, indexMcp) || 0.0001;
  const rawPinch = distance(thumbTip, indexTip) / handScale;

  const normalized = clamp((rawPinch - 0.2) / 1.1, 0, 1);
  smoothedPinch =
    smoothedPinch === null
      ? normalized
      : lerp(smoothedPinch, normalized, EMA_ALPHA);

  window.LightronOrb?.setGesture({
    zoom: smoothedPinch,
    interactionStrength: 1,
  });
}

function distance(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  const dz = (a.z ?? 0) - (b.z ?? 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

main();
