# OGGY

```text
  @@@   @@@@  @@@@  @   @
 @   @  @     @      @ @
 @   @  @ @@  @ @@    @
 @   @  @  @  @  @    @
  @@@   @@@@  @@@@    @
```

OGGY is a small personal AI assistant. You can type a request such as
"make a folder" or "read this file", and OGGY can plan the next step.
It is built with Python, Flask, HTML, CSS, and JavaScript. It does not
need React, Node, or a frontend build step.

The most important idea is simple:

> The AI can suggest an action, but the safety code decides whether that
> action is allowed to happen.

## What happens when you send a message?

1. You type a message in the browser.
2. The browser sends it to Flask at `/api/chat`.
3. The OGGY orchestrator gives the message and the available tools to an
   AI provider.
4. The AI either writes an answer or asks for a tool, such as
   `read_file` or `create_folder`.
5. OGGY checks the tool request before running it.
6. Safe work runs automatically. Risky work waits for you to click
   Approve or Deny.
7. OGGY sends the result back to the AI and then shows the final answer.

The AI never receives direct permission to run commands or change files.
It can only ask for one of OGGY's registered tools.

## Safety rules

OGGY uses four safety levels:

- **SAFE**: reading, searching, and creating normal files can run
  automatically.
- **MODERATE**: opening an application needs your approval first.
- **DANGEROUS**: deleting, moving, renaming, or running a command needs
  your approval first.
- **BLOCKED**: the action is refused and cannot be approved.

File paths are checked by `security/path_guard.py`. This blocks paths
that try to escape the allowed folders, including `../../` paths and
unsafe symbolic links. Commands are checked against the list in
`OGGY_ALLOWED_COMMANDS` and run without a shell.

API keys are kept in `.env`. Do not commit `.env` to GitHub. The example
file `.env.example` contains names and empty values, not your secrets.
Audit logs hide values that look like API keys, tokens, passwords, or
authorization headers.

## AI providers and fallback

OGGY can use these providers:

- Anthropic
- Google Gemini
- Groq
- Qwen through the DashScope compatible API
- Echo mode, which needs no internet or API key

When Gemini, Groq, or Qwen are configured, OGGY tries them in the order
written in `OGGY_PROVIDER_ORDER`. If one provider is unavailable, OGGY
marks it as failed and tries the next provider. Providers with empty API
keys are skipped.

Example fallback settings:

```env
OGGY_LLM_PROVIDER=gemini
OGGY_PROVIDER_ORDER=gemini,groq,qwen
OGGY_PROVIDER_TIMEOUT_SECONDS=20
```

Use Echo mode when you only want to test the website and tools without
calling an AI service:

```env
OGGY_LLM_PROVIDER=echo
```

After changing `.env`, restart OGGY because settings are loaded when the
Python process starts.

## Procedures: install and start OGGY

### 1. Open the project folder

```powershell
cd C:\path\to\OGGY
```

### 2. Create a virtual environment

A virtual environment keeps OGGY's Python packages separate from other
projects on your computer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux, activate it with:

```bash
source .venv/bin/activate
```

### 3. Install the packages

```powershell
pip install -r requirements.txt
```

### 4. Create your settings file

```powershell
Copy-Item .env.example .env
```

Open `.env` and add one real API key, or select Echo mode. Never paste
your real keys into `README.md`, `.env.example`, or a public issue.

### 5. Start the server

```powershell
python app.py
```

Open this address in your browser:

`http://127.0.0.1:5050`

Try asking:

> Create a folder called experiments and a file called test.py inside it.

### 6. Run the tests

Keep the virtual environment active and run:

```powershell
pytest tests/
```

The tests check the security rules and the provider fallback behavior.

## Project map

These are the important folders and what they do:

```text
app.py                    Starts the Flask web server.
config.py                 Reads settings from .env.
api/routes.py             Receives browser requests.
core/orchestrator.py      Runs one complete AI task.
core/llm.py               Talks to AI providers and handles fallback.
core/context.py           Stores the conversation history.
core/state.py             Stores states such as thinking and waiting.
tools/                    Performs approved file, command, and app tasks.
security/                 Checks paths and permission levels.
memory/                   Stores facts and session information in SQLite.
oggy_logging/             Writes redacted audit logs.
frontend/                 Contains the browser page and animated Orb.
voice/                    Future speech input and output code.
tests/                    Automated safety and fallback tests.
```

The Orb shows what OGGY is doing. For example, it can show idle,
listening, thinking, responding, executing a tool, waiting for your
permission, or an error.

## Current limitation

If one message asks for several risky tool actions, the current V1
interface shows the first approval request before the others. This is a
known limitation planned for a future version.

## Future plans

- Better project detection and project memory.
- Safer code editing and controlled test execution.
- More terminal and application workflows.
- Voice input and spoken answers.
- Browser control and email drafting.
- Git tools with confirmation for push, reset, and force-push actions.
- Better planning and recovery for long tasks.

Created by Mahzendx.
