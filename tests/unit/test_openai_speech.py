from typing import cast

import pytest
from openai import OpenAI

from project_g.infrastructure.audio.openai_speech import (
    OpenAISpeechResponseError,
    OpenAISpeechSynthesizer,
)
from project_g.ports.speech import (
    SpeechSynthesisRequest,
)


class FakeBinaryResponse:
    def __init__(
        self,
        data: bytes,
    ) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeSpeechResource:
    def __init__(
        self,
        data: bytes = b"fake-mp3",
    ) -> None:
        self.data = data
        self.calls: list[dict[str, object]] = []

    def create(
        self,
        **kwargs: object,
    ) -> FakeBinaryResponse:
        self.calls.append(kwargs)
        return FakeBinaryResponse(self.data)


class FakeAudioResource:
    def __init__(
        self,
        speech: FakeSpeechResource,
    ) -> None:
        self.speech = speech


class FakeOpenAIClient:
    def __init__(
        self,
        speech: FakeSpeechResource,
    ) -> None:
        self.audio = FakeAudioResource(speech)


def _service(
    speech: FakeSpeechResource,
) -> OpenAISpeechSynthesizer:
    return OpenAISpeechSynthesizer(
        api_key="test-key",
        timeout_seconds=12.5,
        client=cast(
            OpenAI,
            FakeOpenAIClient(speech),
        ),
    )


def test_synthesize_returns_binary_audio() -> None:
    speech = FakeSpeechResource(b"project-g-audio")

    result = _service(speech).synthesize(
        SpeechSynthesisRequest(
            text=" 巨人のニュースです。 ",
            model="gpt-4o-mini-tts",
            voice="marin",
            audio_format="mp3",
            instructions=(" Natural Japanese narration. "),
        )
    )

    assert result == b"project-g-audio"

    assert speech.calls == [
        {
            "input": "巨人のニュースです。",
            "model": "gpt-4o-mini-tts",
            "voice": "marin",
            "instructions": ("Natural Japanese narration."),
            "response_format": "mp3",
            "timeout": 12.5,
        }
    ]


def test_synthesize_omits_blank_instructions() -> None:
    speech = FakeSpeechResource()

    _service(speech).synthesize(
        SpeechSynthesisRequest(
            text="音声テスト",
            model="gpt-4o-mini-tts",
            voice="marin",
            audio_format="mp3",
            instructions="   ",
        )
    )

    assert "instructions" not in speech.calls[0]


@pytest.mark.parametrize(
    "text",
    (
        "",
        "   ",
        "あ" * 4097,
    ),
)
def test_synthesize_rejects_invalid_text(
    text: str,
) -> None:
    speech = FakeSpeechResource()

    with pytest.raises(ValueError):
        _service(speech).synthesize(
            SpeechSynthesisRequest(
                text=text,
                model="gpt-4o-mini-tts",
                voice="marin",
                audio_format="mp3",
            )
        )

    assert speech.calls == []


def test_synthesize_rejects_unsupported_format() -> None:
    speech = FakeSpeechResource()

    with pytest.raises(
        ValueError,
        match="Unsupported",
    ):
        _service(speech).synthesize(
            SpeechSynthesisRequest(
                text="音声テスト",
                model="gpt-4o-mini-tts",
                voice="marin",
                audio_format="exe",
            )
        )

    assert speech.calls == []


def test_synthesize_rejects_empty_response() -> None:
    speech = FakeSpeechResource(b"")

    with pytest.raises(
        OpenAISpeechResponseError,
        match="empty",
    ):
        _service(speech).synthesize(
            SpeechSynthesisRequest(
                text="音声テスト",
                model="gpt-4o-mini-tts",
                voice="marin",
                audio_format="mp3",
            )
        )
