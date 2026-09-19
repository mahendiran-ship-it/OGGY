# OGGY

A personal AI assistant with a strict boundary between "what the LLM
decides" and "what actually touches your computer." Built from scratch
in Python/Flask + HTML/CSS/vanilla JS — no React, no Node, no build step.

## A. Architecture

```
 User (text / voice)
        |
        v
   Flask API  (api/routes.py)
        |
        v
 OGGY Orchestrator (core/orchestrator.py)
        |
        +--> LLM abstraction (core/llm.py)  -- decides WHAT should happen
        |
        +--> Permission layer (security/permissions.py) -- decides
        |    whether that's allowed to happen automatically, needs your
        |    confirmation, or is blocked outright
        |
        +--> Tool registry (tools/registry.py) -- deterministic
        |    handlers that decide HOW it happens (filesystem.py,
        |    commands.py, applications.py)
        |
        +--> Memory (memory/memory.py) -- SQLite: permanent facts,
        |    session state, tool-use history
        |
        +--> Audit log (oggy_logging/logger.py) -- every tool call,
             with secrets redacted before they ever hit disk
        |
        v
   Frontend Orb (frontend/) -- polls /api/state, renders OGGY's
   current state as a living reactor-core animation
```

The LLM **never** executes a shell command or touches the filesystem
directly. It can only request a named tool with typed arguments. The
orchestrator hands that request to the permission layer, which is the
only thing that decides if it runs automatically, waits for you to
approve it, or gets refused.

## B. Directory structure

```
OGGY/
├── app.py                  Flask entrypoint
├── config.py                All settings, read from env / .env
├── core/
│   ├── orchestrator.py      The agent loop
│   ├── llm.py                LLM providers and ordered fallback chain
│   ├── context.py            Conversation history
│   └── state.py              IDLE/THINKING/... state machine
├── tools/
│   ├── registry.py           Tool definitions + validated execution
│   ├── filesystem.py         list/read/search/create/delete/rename/move
│   ├── commands.py           Allow-listed command execution
│   └── applications.py       Allow-listed application launching
├── security/
│   ├── permissions.py        SAFE / MODERATE / DANGEROUS / BLOCKED
│   ├── path_guard.py          Filesystem sandbox enforcement
│   └── audit_log.py           Re-exports oggy_logging's logger
├── memory/memory.py          SQLite: permanent + session + history
├── voice/voice.py             STT/TTS interfaces (not wired up yet)
├── oggy_logging/logger.py     Structured, secret-redacting audit log
├── api/routes.py              /api/chat, /api/state, /api/permission/response
├── frontend/                  index.html, style.css, orb.js, app.js
└── tests/test_security.py     Path guard + permission manager tests
```

(Named `oggy_logging`, not `logging`, so it never shadows Python's
standard library logging module, which several files also use.)

## C. Data flow (one chat turn)

1. You type a message. `app.js` POSTs it to `/api/chat`.
2. `orchestrator.handle_message()` adds it to conversation history and
   asks the LLM what to do, passing the current tool schemas.
3. If the LLM just replies with text, that's returned straight away.
4. If it requests a tool call, the orchestrator asks
   `permission_manager.evaluate()`:
   - **SAFE** → runs immediately, result fed back to the LLM, loop
     continues (bounded by `OGGY_MAX_AGENT_STEPS`).
   - **MODERATE/DANGEROUS** → execution pauses; the frontend shows an
     approve/deny prompt; nothing runs until you respond.
   - **BLOCKED** → refused, no confirmation possible.
5. Once there's a final text reply, it's returned and the orb goes
   back to idle.

## D. Security model

- **Filesystem**: every path goes through `security/path_guard.py`,
  which resolves it and verifies it's inside `OGGY_ALLOWED_DIRS`.
  `../../` traversal and symlink escapes are both blocked (verified in
  `tests/test_security.py`).
- **Commands**: `tools/commands.py` only ever runs executables on
  `OGGY_ALLOWED_COMMANDS`, as an argv list (never `shell=True`), with a
  timeout and output size cap. Risk level is `DANGEROUS`, so it always
  needs your confirmation regardless of what the LLM asked for.
- **Applications**: same allow-list pattern, `MODERATE` risk.
- **Permissions**: the LLM has no path to the permission rules
  themselves — they live in `config.py` and `security/permissions.py`,
  which the LLM never sees or can call into.
- **Secrets**: `oggy_logging/logger.py` redacts anything with a key
  matching `api_key|token|password|secret|authorization` before it's
  written to the audit log. `.env` (not `.env.example`) is where real
  credentials live and is never read by the LLM.

## E. Orb state system

`core/state.py` holds one canonical state
(`idle/listening/thinking/responding/executing_tool/waiting_for_permission/error`).
The orchestrator updates it as it works; `frontend/app.js` polls
`GET /api/state` every 800ms and calls `setOrbState()`
(`frontend/orb.js`), which just sets a `data-state` attribute — all the
actual animation (ring speed, color, glow) is CSS driven from
`style.css`. Adding a new state is: one enum value + one CSS block.

## F. Setup

```bash
cd OGGY
python -m venv .venv && source .venv/bin/activate   # or your preferred env tool
pip install -r requirements.txt
cp .env.example .env
# edit .env and set a provider key. For fallback, use:
# OGGY_LLM_PROVIDER=gemini and OGGY_PROVIDER_ORDER=gemini,groq,qwen
# Providers whose API keys are empty are skipped.
# Use OGGY_LLM_PROVIDER=echo to run without a real LLM.
python app.py
```

Then open `http://127.0.0.1:5050`. Try:

> "Create a folder called experiments and a file called test.py inside it."

`list_files` / `read_file` / `search_files` / `create_file` /
`create_folder` run automatically (SAFE). `delete_file` / `rename_file`
/ `move_file` / `run_command` / `open_application` will show an
approve/deny prompt in the UI first.

Run the security tests:
```bash
pytest tests/
```

## Known V1 limitation

If the LLM requests several tool calls in a single turn and more than
one of them needs confirmation, only the first pending one is
surfaced — see the note in `core/orchestrator.py:resolve_confirmation`.
In practice V1's tool set rarely triggers this; it's flagged as a V2
fix (track *all* outstanding tool_use ids per turn, not just one).

## Roadmap (from the original brief)

- **V1 (this drop)**: orchestrator, tool registry, permission layer,
  filesystem controller, logging, LLM tool calling, the Orb.
- **V2**: project memory & detection, `open_project`, diff-based code
  editing, controlled test execution.
- **V3**: richer application/terminal control, more workflows.
- **V4**: wire up `voice/voice.py` to a real STT/TTS provider.
- **V5**: browser control (Playwright), email drafting/sending.
- **V6**: full git controller (`status`/`diff`/`add`/`commit`, with
  `push`/`force_push`/`reset` always confirmation-gated).
- **V7**: screen understanding (vision) — used to *identify* the real
  file/error, then handed off to the filesystem/code tools rather than
  becoming the primary editing mechanism.
- **V8**: better planning, recovery, long-running workflow memory.
