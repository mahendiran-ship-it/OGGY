import pytest

from core.llm import FallbackProvider, LLMResponse


def response(text):
    return LLMResponse(text, [], [{"type": "text", "text": text}])


def test_fallback_moves_from_gemini_to_groq_once():
    calls = []

    def gemini():
        calls.append("gemini-init")
        raise RuntimeError("429")

    def groq():
        calls.append("groq-init")
        return type("Provider", (), {"send": lambda self, *_args, **_kwargs: response("groq")})()

    manager = FallbackProvider({"gemini": gemini, "groq": groq})
    assert manager.send(messages=[], tools=[], system_prompt="").text == "groq"
    assert manager.send(messages=[], tools=[], system_prompt="").text == "groq"
    assert calls == ["gemini-init", "groq-init"]


def test_fallback_moves_from_gemini_to_groq_after_rate_limit():
    calls = []

    class Gemini:
        def send(self, *_args, **_kwargs):
            calls.append("gemini-send")
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    class Groq:
        def send(self, *_args, **_kwargs):
            calls.append("groq-send")
            return response("groq")

    manager = FallbackProvider({
        "gemini": lambda: Gemini(),
        "groq": lambda: Groq(),
    })

    assert manager.send(messages=[], tools=[], system_prompt="").text == "groq"
    assert calls == ["gemini-send", "groq-send"]


def test_fallback_reports_all_provider_failures():
    manager = FallbackProvider({
        "gemini": lambda: (_ for _ in ()).throw(TimeoutError()),
        "groq": lambda: (_ for _ in ()).throw(RuntimeError("down")),
    })
    with pytest.raises(RuntimeError, match=r"All configured OGGY providers failed: gemini \(.*\), groq \(down\)"):
        manager.send(messages=[], tools=[], system_prompt="")