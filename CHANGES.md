# OGGY — Change log

What changed in this drop, file by file, old vs new. Architecture is
unchanged: same layers (`api` → `core.orchestrator` → `core.llm` /
`security.permissions` / `tools.registry` / `memory`), same
responsibilities, same request flow. Everything below is additive or a
targeted fix inside that structure.

Three things were asked for:
1. Add [OmniRoute](https://omniroute.online) support so OGGY can run
   against any model behind its gateway, without crashing.
2. A knowledge base file for personal/work context.
3. Chat replies that render code the way ChatGPT does — a block with a
   copy button.

---

## 1. `config.py`

**Old:** `OGGY_LLM_PROVIDER` accepted `anthropic` / `gemini` / `echo`.
No knowledge-base setting existed.

**New:** added an `omniroute` provider option plus its settings, and a
knowledge-base section:

```python
OMNIROUTE_BASE_URL = os.getenv("OMNIROUTE_BASE_URL", "http://localhost:20128/v1")
OMNIROUTE_API_KEY = os.getenv("OMNIROUTE_API_KEY", "")
OMNIROUTE_MODEL = os.getenv("OMNIROUTE_MODEL", "auto")
OMNIROUTE_TIMEOUT_SECONDS = float(os.getenv("OMNIROUTE_TIMEOUT_SECONDS", "60"))
OMNIROUTE_MAX_RETRIES = int(os.getenv("OMNIROUTE_MAX_RETRIES", "2"))
OMNIROUTE_DISABLE_TOOLS = os.getenv("OMNIROUTE_DISABLE_TOOLS", "false").lower() == "true"

KNOWLEDGE_BASE_PATH = Path(os.getenv("OGGY_KNOWLEDGE_BASE_PATH", str(Path(__file__).parent / "knowledge_base.md"))).expanduser()
KNOWLEDGE_BASE_MAX_CHARS = int(os.getenv("OGGY_KNOWLEDGE_BASE_MAX_CHARS", "6000"))
```

Nothing existing was removed or renamed — old `.env` files still work.

---

## 2. `core/llm.py`

**Old:** two real providers, `AnthropicProvider` and `GeminiProvider`,
plus `EchoProvider`. `get_llm_provider()` raised `ValueError` for
anything else.

**New:** added `OmniRouteProvider`, a third real provider, using the
official `openai` SDK pointed at OmniRoute's local `/v1` endpoint
(OmniRoute is OpenAI-wire-compatible, so no vendor SDK was needed). It:

- Converts OGGY's existing generic (Anthropic-block-shaped) history —
  the same shape `core/context.py` already stored — into OpenAI
  chat-completions messages, and converts OpenAI's response back into
  that same generic shape. `core/context.py` itself is **untouched**,
  exactly like the existing `GeminiProvider` already does for Gemini's
  format.
- Never raises out of `send()`. Every external failure mode is caught
  and turned into either a graceful fallback or a clear text reply:

  | Failure | Old behavior (n/a — provider didn't exist) | New behavior |
  |---|---|---|
  | Model doesn't support tool calling | — | detected from the error, cached per-instance, retried once without `tools`; every later call for that model skips `tools` automatically |
  | Model returns malformed tool-call JSON | — | parsed defensively; on failure, turned into a normal tool-error result the model can see and retry from, instead of an unhandled exception |
  | Model returns an empty/refused message | — | replaced with a clear placeholder reply, never a blank bubble |
  | Network error / OmniRoute not running / bad model string | — | caught, returned as a short readable chat message naming the base URL and model, instead of propagating |

- `get_llm_provider()` gained an `omniroute` branch, and its error
  message for an unknown provider now lists the valid options instead
  of just echoing the bad value back.

---

## 3. `core/orchestrator.py`

**Old:** a single fixed `SYSTEM_PROMPT` string. `handle_message()` and
`resolve_confirmation()` both called `provider.send(...)` with no
error handling of their own — an exception there propagated all the
way up to `api/routes.py`'s generic except block.

**New:**

- `SYSTEM_PROMPT` (fixed base text) → `build_system_prompt()` (a
  function): same base text, renamed `BASE_SYSTEM_PROMPT`, plus:
  - a new **code-formatting** section instructing the model to always
    fence code with a language tag, only code inside the fence, and
    give complete copy-pasteable snippets — this is what
    `frontend/app.js`'s new renderer (§6) is built to display.
  - the user's `knowledge_base.md` content (§4), appended as a
    clearly-delimited "standing context" section, when present.
  - `SYSTEM_PROMPT` is still exported as an alias of the old fixed
    text, so nothing importing the old name breaks.
- Both call sites (`handle_message`'s loop and
  `resolve_confirmation`'s wrap-up call) now wrap `provider.send(...)`
  — and, in `handle_message`, `get_llm_provider()` itself — in
  `try/except`, setting state to `ERROR` and returning a clear
  `reply` string on failure instead of letting the exception escape
  the orchestrator. This is what actually makes "any OmniRoute model,
  never crash" true at the app level, not just inside
  `OmniRouteProvider`.

---

## 4. `core/knowledge.py` (new file)

Small, single-purpose module: `load_knowledge_base()` reads
`config.KNOWLEDGE_BASE_PATH`, returns `None` if it's missing/empty
(never raises), and truncates to `KNOWLEDGE_BASE_MAX_CHARS` otherwise.
Called by `build_system_prompt()` in `core/orchestrator.py` on every
turn — no caching, no restart needed to pick up edits.

## 5. `knowledge_base.md` (new file)

A plain-markdown template at the project root — About Me / Current
Work / Preferences / Standing Context headings — for you to fill in.
Nothing reads this as structured data; it's dropped into the system
prompt close to verbatim, so edit it like a text file.

---

## 6. `frontend/app.js` + `frontend/style.css`

**Old:** `appendLog()` inserted replies as a plain text node
(`document.createTextNode`), and CSS relied on `white-space: pre-wrap`
on `.log-entry` to preserve formatting. No markdown, no code
highlighting, no copy affordance — a multi-line code reply just wrapped
as plain paragraph text.

**New:**

- `renderMarkdown()` (new function) does one job well: turns
  <code>&#96;&#96;&#96;lang ... &#96;&#96;&#96;</code> fences into a
  real code block (`renderCodeBlock()`), plus small extras (`` `inline
  code` ``, `**bold**`, line breaks). Everything is HTML-escaped before
  insertion — `appendLog()` now sets `.innerHTML` from this renderer's
  output, never raw user/model text.
- Each code block gets a header with a **language label** and a
  **Copy** button (`.code-block`, `.code-block-header`, `.copy-btn` in
  `style.css`) — matching ChatGPT's copy-paste code UI. One delegated
  click listener on the log element handles every Copy button, past
  and future, via `navigator.clipboard.writeText()`, with a brief
  "Copied!" state.
- An unterminated fence (a reply cut off mid-code-block) still renders
  as a code block instead of leaking literal backticks into the chat.
- `.log-entry`'s CSS lost `white-space: pre-wrap` (no longer needed —
  line breaks are now explicit `<br>`s from the renderer); `.code-pre`
  carries its own `white-space: pre` so code whitespace is still exact.
- No new dependency, no CDN script, no build step — same vanilla-JS
  constraint as before, just more JS in the same file.

---

## 7. `api/routes.py`

**Old:** the `/api/chat` exception handler did
`state_manager.set(state_manager.get()["state"])` — a no-op read that
looked like a reset but wasn't one, so a mid-turn crash left the orb
stuck on `THINKING`/`EXECUTING_TOOL` until the next successful turn.

**New:** `state_manager.set(OggyState.ERROR)` — an actual reset, so the
orb visibly goes to its error state and the UI recovers. This bug
existed before OmniRoute was added, but it's fixed now because a
less-predictable "any model" provider makes hitting it far more likely.

---

## 8. `requirements.txt` / `.env.example`

- `requirements.txt`: added `openai>=1.40` (only imported if
  `OGGY_LLM_PROVIDER=omniroute`, same lazy-import pattern the
  `anthropic` and `google-genai` packages already used).
- `.env.example`: added the `OMNIROUTE_*` and `OGGY_KNOWLEDGE_BASE_*`
  variables from §1, with inline comments. Existing variables
  untouched.

---

## 9. `README.md`

Updated the directory-structure listing and provider table to include
`core/knowledge.py`, `knowledge_base.md`, and the `omniroute` provider;
added sections **G** (LLM providers / OmniRoute), **H** (knowledge
base), and **I** (copy-pasteable code) describing how to use each. No
existing section was restructured or removed.
