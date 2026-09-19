"""
Voice foundation (V1: interfaces only, no orchestrator coupling).

The point of this module in V1 is the *shape*, not a working
implementation: voice must never get its own AI brain or its own copy
of the agent loop. When wired up, the flow is:

    microphone -> SpeechToText.transcribe() -> str
                                                  |
                                                  v
                                   core.orchestrator.handle_message()
                                        (exact same path as typed text)
                                                  |
                                                  v
                              TextToSpeech.synthesize() -> audio bytes

Concrete providers (e.g. a local Whisper model, or a cloud STT/TTS API)
should subclass these and be selected via config, the same pattern as
core/llm.py's provider selection - so swapping providers later doesn't
touch the orchestrator.
"""

from abc import ABC, abstractmethod


class SpeechToText(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> str:
        """Return the transcribed text for the given audio."""


class TextToSpeech(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Return audio bytes (e.g. WAV/MP3) for the given text."""


class NotConfiguredSTT(SpeechToText):
    def transcribe(self, audio_bytes: bytes) -> str:
        raise NotImplementedError(
            "No speech-to-text provider is configured yet. This is a V1 "
            "foundation - wire up a real provider (e.g. local Whisper) here."
        )


class NotConfiguredTTS(TextToSpeech):
    def synthesize(self, text: str) -> bytes:
        raise NotImplementedError(
            "No text-to-speech provider is configured yet. This is a V1 "
            "foundation - wire up a real provider here."
        )


def get_stt() -> SpeechToText:
    return NotConfiguredSTT()


def get_tts() -> TextToSpeech:
    return NotConfiguredTTS()
