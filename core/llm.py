"""
LLM abstraction.

The orchestrator talks to `get_llm_provider()`, never to a vendor SDK
directly. Swapping providers (or adding a second one) means writing a
new LLMProvider subclass here and pointing OGGY_LLM_PROVIDER at it -
nothing in core/orchestrator.py or tools/ has to change.

Supported providers:
    - AnthropicProvider: Anthropic API.
    - GeminiProvider: Google Gemini Interactions API.
    - OpenAICompatibleProvider: Groq and Qwen compatible endpoints.
    - EchoProvider: no-network test mode.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from config import config


@dataclass
class LLMResponse:
    # "text" content the assistant said, if any
    text: Optional[str]
    # list of {"id", "name", "input"} tool calls the model wants to make
    tool_calls: List[Dict[str, Any]]
    # raw assistant content blocks, needed to append back into history
    # in the exact shape the provider expects for multi-turn tool use
    raw_content: Any
    stop_reason: Optional[str] = None


class LLMProvider(ABC):
    @abstractmethod
    def send(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
    ) -> LLMResponse:
        ...


class AnthropicProvider(LLMProvider):
    def __init__(self):
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env, or set "
                "OGGY_LLM_PROVIDER=echo to run OGGY without a real LLM."
            )
        import anthropic  # imported lazily so the package is only required
                           # if you actually use this provider
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def send(self, messages, tools, system_prompt) -> LLMResponse:
        response = self._client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=config.MAX_TOKENS,
            system=system_prompt,
            messages=messages,
            tools=tools if tools else None,
        )

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            raw_content=[b.model_dump() for b in response.content],
            stop_reason=response.stop_reason,
        )


class GeminiProvider(LLMProvider):
    """
    Uses Google's Interactions API (`google-genai` SDK) in STATEFUL mode:
    `store=True` plus `previous_interaction_id` chaining. This is Google's
    current recommended approach for multi-turn tool use, and it sidesteps
    the bug the old stateless implementation had.

    The old implementation normalized Gemini's response steps into the
    same generic block shape AnthropicProvider uses, stored *that* in
    core/context.py, and then, on the next turn, tried to translate those
    generic blocks back into Gemini "input" steps (a hand-rolled
    {"type": "text", ...} step, an invented {"type": "function_call", ...}
    replay, etc). Gemini's Interactions API doesn't recognize several of
    those reconstructed shapes - in particular a bare `{"type": "text"}`
    input step - which is what produced:

        "The value 'UNKNOWN' is not supported for 'type' at 'input[1]'"

    Stateful mode avoids the problem at the root: Gemini keeps its own
    authoritative record of every step it produced (including `thought`
    steps and, for Gemini 3 models, thought signatures) server-side under
    the interaction id. We never have to reconstruct any of that - we
    only ever send the *new* thing that happened since our last call
    (the user's message, or a tool's result), chained onto the previous
    interaction with `previous_interaction_id`.

    core/context.py is untouched and keeps its own generic (Anthropic-
    shaped) copy of the conversation for display/audit/other providers.
    This class tracks, in parallel and privately, which of those message
    dicts it has already turned into Gemini input, keyed by Python object
    identity (id()) rather than list position/length, so that
    core/context.py's history trimming (MAX_HISTORY_MESSAGES) can't
    desync the bookkeeping.
    """

    def __init__(self):
        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env, or set "
                "OGGY_LLM_PROVIDER=echo to run OGGY without a real LLM."
            )
        from google import genai  # imported lazily - only required for this provider
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model = config.GEMINI_MODEL

        # Stateful-interaction bookkeeping - see class docstring.
        self._previous_interaction_id: Optional[str] = None
        self._sent_ids: set = set()
        self._call_names: Dict[str, str] = {}

    def send(self, messages, tools, system_prompt) -> LLMResponse:
        gemini_tools = [
            {
                "type": "function",
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            }
            for t in tools
        ] if tools else None

        current_ids = {id(m) for m in messages}

        # If none of the messages we've previously forwarded to Gemini are
        # still present, the conversation was reset out from under us
        # (e.g. a future conversation.clear()) - start a fresh interaction
        # rather than trying to chain onto one Gemini no longer considers
        # relevant.
        if self._sent_ids and not (self._sent_ids & current_ids):
            self._previous_interaction_id = None
            self._sent_ids = set()
            self._call_names = {}

        new_messages = [m for m in messages if id(m) not in self._sent_ids]
        gemini_input = self._new_messages_to_gemini_input(new_messages)

        if not gemini_input:
            # Nothing new since last call (shouldn't normally happen) -
            # Gemini rejects an empty input list, so fall back to a no-op
            # continuation rather than sending nothing.
            gemini_input = [{"type": "user_input", "content": [{"type": "text", "text": ""}]}]

        response = self._client.interactions.create(
            model=self.model,
            system_instruction=system_prompt,
            input=gemini_input,
            tools=gemini_tools,
            store=True,
            previous_interaction_id=self._previous_interaction_id,
        )

        self._previous_interaction_id = response.id
        self._sent_ids |= current_ids

        tool_calls = []
        raw_content = []
        for step in response.steps:
            if getattr(step, "type", None) == "function_call":
                tool_calls.append({"id": step.id, "name": step.name, "input": step.arguments})
                raw_content.append({"type": "tool_use", "id": step.id, "name": step.name, "input": step.arguments})
                # Remember the name now, so that when the matching
                # function_result comes back in a later call we know what
                # tool it belongs to (OGGY's generic tool_result blocks,
                # see core/context.py, only carry the call id).
                self._call_names[step.id] = step.name

        text = response.output_text or None
        if text:
            raw_content.append({"type": "text", "text": text})

        return LLMResponse(text=text, tool_calls=tool_calls, raw_content=raw_content, stop_reason=None)

    def _new_messages_to_gemini_input(self, new_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert only the newly-appeared entries of OGGY's generic
        conversation history into Gemini Interactions API `input` steps.

        Assistant messages are deliberately NOT turned into input steps:
        in stateful mode Gemini already has its own record of what it
        said (that's the point of previous_interaction_id), and OGGY's
        stored copy is a generic block shape meant for other providers /
        display, not a faithful Gemini step - replaying it is exactly
        what produced the original "UNKNOWN" type error.
        """
        steps: List[Dict[str, Any]] = []

        for message in new_messages:
            role = message.get("role")
            content = message.get("content")

            if role == "user" and isinstance(content, str):
                steps.append({"type": "user_input", "content": [{"type": "text", "text": content}]})

            elif role == "user" and isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        call_id = block["tool_use_id"]
                        steps.append({
                            "type": "function_result",
                            "name": self._call_names.get(call_id, "unknown_tool"),
                            "call_id": call_id,
                            "result": [{"type": "text", "text": str(block.get("content", ""))}],
                        })

            elif role == "assistant" and isinstance(content, list):
                # Not sent to Gemini (see docstring) - just make sure we
                # know each tool call's name in case this dict wasn't
                # produced by this provider instance (e.g. after a
                # process restart with an otherwise-unchanged history).
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        self._call_names[block["id"]] = block["name"]

        return steps


class OpenAICompatibleProvider(LLMProvider):
    """Small standard-library client for Groq/Qwen-compatible endpoints."""

    def __init__(self, name: str, api_key: str, model: str, endpoint: str):
        if not api_key:
            raise RuntimeError(f"{name.upper()}_API_KEY is not set.")
        self.name = name
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    def send(self, messages, tools, system_prompt) -> LLMResponse:
        payload_messages = [{"role": "system", "content": system_prompt}]
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                content = "\n".join(str(block.get("content", "")) for block in content)
            payload_messages.append({"role": message.get("role", "user"), "content": str(content or "")})
        payload = {"model": self.model, "messages": payload_messages}
        if tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": tool["name"], "description": tool["description"],
                "parameters": tool["input_schema"],
            }} for tool in tools]
        body = json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(
            self.endpoint,
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=config.PROVIDER_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            raise RuntimeError(f"{self.name} provider returned HTTP {exc.code}.") from exc
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{self.name} provider request failed.") from exc

        message = (data.get("choices") or [{}])[0].get("message") or {}
        calls = []
        raw_content = []
        if message.get("content"):
            raw_content.append({"type": "text", "text": message["content"]})
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function", {})
            try:
                arguments = json.loads(function.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}
            calls.append({"id": tool_call.get("id", ""), "name": function.get("name", ""), "input": arguments})
            raw_content.append({"type": "tool_use", "id": tool_call.get("id", ""), "name": function.get("name", ""), "input": arguments})
        text = message.get("content") or None
        return LLMResponse(text, calls, raw_content, data.get("choices", [{}])[0].get("finish_reason"))


class FallbackProvider(LLMProvider):
    """Try each configured provider once, then remember failures."""

    def __init__(self, factories: Dict[str, Any]):
        self._factories = factories
        self._instances: Dict[str, LLMProvider] = {}
        self._failed = set()

    def send(self, messages, tools, system_prompt) -> LLMResponse:
        failures = []
        for name, factory in self._factories.items():
            if name in self._failed:
                continue
            try:
                provider = self._instances.get(name)
                if provider is None:
                    provider = factory()
                    self._instances[name] = provider
                return provider.send(messages, tools, system_prompt)
            except Exception as exc:
                self._failed.add(name)
                reason = str(exc).strip() or exc.__class__.__name__
                failures.append(f"{name} ({reason})")
        raise RuntimeError("All configured OGGY providers failed: " + ", ".join(failures))


class EchoProvider(LLMProvider):
    """
    No-network fallback. Doesn't call tools - just echoes back what it
    was told, so you can verify the Flask app, the orb states, memory,
    and logging all work before an API key is configured.
    """

    def send(self, messages, tools, system_prompt) -> LLMResponse:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                last_user = m["content"]
                break
        text = (
            f"(echo mode - no LLM configured) You said: \"{last_user}\". "
            f"Set ANTHROPIC_API_KEY and OGGY_LLM_PROVIDER=anthropic in .env "
            f"to talk to a real model."
        )
        return LLMResponse(text=text, tool_calls=[], raw_content=[{"type": "text", "text": text}], stop_reason="end_turn")


_provider_instance: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    if config.LLM_PROVIDER == "anthropic":
        _provider_instance = AnthropicProvider()
    elif config.LLM_PROVIDER == "echo":
        _provider_instance = EchoProvider()
    elif config.LLM_PROVIDER in {"gemini", "groq", "qwen"}:
        factories = {
            "gemini": GeminiProvider,
            "groq": lambda: OpenAICompatibleProvider(
                "groq", config.GROQ_API_KEY, config.GROQ_MODEL,
                "https://api.groq.com/openai/v1/chat/completions",
            ),
            "qwen": lambda: OpenAICompatibleProvider(
                "qwen", config.QWEN_API_KEY, config.QWEN_MODEL,
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            ),
        }
        credentials = {
            "gemini": config.GEMINI_API_KEY,
            "groq": config.GROQ_API_KEY,
            "qwen": config.QWEN_API_KEY,
        }
        ordered = config.PROVIDER_ORDER or [config.LLM_PROVIDER, "groq", "qwen"]
        names = list(dict.fromkeys(ordered))
        configured = {
            name: factories[name]
            for name in names
            if name in factories and credentials[name]
        }
        if not configured:
            raise RuntimeError(
                "No configured OGGY provider has an API key. Set one of "
                "GEMINI_API_KEY, GROQ_API_KEY, or QWEN_API_KEY."
            )
        _provider_instance = FallbackProvider(configured)
    else:
        raise ValueError(f"Unknown OGGY_LLM_PROVIDER: {config.LLM_PROVIDER}. Use gemini, groq, qwen, anthropic, or echo.")

    return _provider_instance
