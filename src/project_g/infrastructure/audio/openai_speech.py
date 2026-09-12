from typing import Literal, cast

from openai import OpenAI

from project_g.ports.speech import (
    SpeechSynthesisRequest,
    SpeechSynthesizer,
)

_MAX_INPUT_CHARACTERS = 4096

_ResponseFormat = Literal[
    "mp3",
    "opus",
    "aac",
    "flac",
    "wav",
    "pcm",
]

_SUPPORTED_FORMATS: frozenset[str] = frozenset(
    {
        "mp3",
        "opus",
        "aac",
        "flac",
        "wav",
        "pcm",
    }
)


class OpenAISpeechResponseError(RuntimeError):
    """Raised when OpenAI returns unusable speech content."""


class OpenAISpeechSynthesizer(SpeechSynthesizer):
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        client: OpenAI | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key must not be empty")

        if timeout_seconds <= 0:
            raise ValueError("OpenAI timeout_seconds must be greater than zero")

        self._client = client if client is not None else OpenAI(api_key=api_key)
        self._timeout_seconds = timeout_seconds

    def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> bytes:
        text = request.text.strip()
        model = request.model.strip()
        voice = request.voice.strip()
        audio_format = request.audio_format.strip().lower()

        if not text:
            raise ValueError("Speech input text must not be empty")

        if len(text) > _MAX_INPUT_CHARACTERS:
            raise ValueError(
                f"Speech input text must not exceed {_MAX_INPUT_CHARACTERS} characters"
            )

        if not model:
            raise ValueError("Speech model must not be empty")

        if not voice:
            raise ValueError("Speech voice must not be empty")

        if audio_format not in _SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported speech audio format: {audio_format}")

        response_format = cast(
            _ResponseFormat,
            audio_format,
        )

        instructions = request.instructions.strip() if request.instructions is not None else None

        if instructions:
            response = self._client.audio.speech.create(
                input=text,
                model=model,
                voice=voice,
                instructions=instructions,
                response_format=response_format,
                timeout=self._timeout_seconds,
            )
        else:
            response = self._client.audio.speech.create(
                input=text,
                model=model,
                voice=voice,
                response_format=response_format,
                timeout=self._timeout_seconds,
            )

        data = response.read()

        if not data:
            raise OpenAISpeechResponseError("OpenAI returned empty speech audio")

        return data
