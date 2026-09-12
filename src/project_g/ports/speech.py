from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SpeechSynthesisRequest:
    text: str
    model: str
    voice: str
    audio_format: str
    instructions: str | None = None


class SpeechSynthesizer(Protocol):
    def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> bytes:
        """Generate encoded speech audio."""
        ...
