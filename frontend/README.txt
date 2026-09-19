OGGY + Lightron Orb frontend integration

Files:
- index.html: OGGY UI with the Lightron 7-ring orb and hidden camera input
- app.js: OGGY API/chat/permission logic preserved
- orb.js: OGGY backend-state -> Lightron visual-state adapter
- lightron-orb-controller.js: Lightron orb animation + gesture zoom
- gesture-controller.js: MediaPipe hand tracking and pinch control
- style.css: Lightron holographic orb + OGGY chat/permission panel

Important:
- Backend endpoints remain /api/state, /api/chat and /api/permission/response.
- Gesture camera is not displayed.
- MediaPipe is loaded from the same CDN/model URLs used by the supplied Lightron gesture implementation.
- The terminal HTTP-request suppression is a backend/server logging change and is not included here because the supplied frontend files do not control Flask/Werkzeug logging.
