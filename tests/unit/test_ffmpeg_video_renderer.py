import subprocess
from pathlib import Path

import pytest

from project_g.infrastructure.video.ffmpeg import (
    FFmpegVideoRenderer,
    FFmpegVideoRenderError,
)
from project_g.ports.video import VideoRenderRequest

_AUDIO_BYTES = b"fake-mp3-audio"
_VIDEO_BYTES = b"fake-mp4-video"


def _request() -> VideoRenderRequest:
    return VideoRenderRequest(
        audio_data=_AUDIO_BYTES,
        audio_format="mp3",
        video_format="mp4",
        width=1080,
        height=1920,
        fps=30,
    )


def test_renderer_creates_vertical_video_and_reads_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 12.5

        calls.append(command)

        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(_VIDEO_BYTES)

            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="",
            )

        assert command[0] == "ffprobe"

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="1.234\n",
            stderr="",
        )

    monkeypatch.setattr(
        "project_g.infrastructure.video.ffmpeg.subprocess.run",
        fake_run,
    )

    renderer = FFmpegVideoRenderer(
        timeout_seconds=12.5,
    )

    result = renderer.render(_request())

    assert result.data == _VIDEO_BYTES
    assert result.duration_ms == 1234

    assert len(calls) == 2

    render_command = calls[0]

    assert render_command[0] == "ffmpeg"
    assert "color=c=black:s=1080x1920:r=30" in render_command
    assert "libx264" in render_command
    assert "yuv420p" in render_command
    assert "aac" in render_command
    assert "-shortest" in render_command

    probe_command = calls[1]

    assert probe_command[0] == "ffprobe"
    assert "format=duration" in probe_command


def test_renderer_rejects_empty_audio() -> None:
    renderer = FFmpegVideoRenderer()

    request = VideoRenderRequest(
        audio_data=b"",
        audio_format="mp3",
        video_format="mp4",
        width=1080,
        height=1920,
        fps=30,
    )

    with pytest.raises(
        ValueError,
        match="audio_data must not be empty",
    ):
        renderer.render(request)


def test_renderer_rejects_unsupported_video_format() -> None:
    renderer = FFmpegVideoRenderer()

    request = VideoRenderRequest(
        audio_data=_AUDIO_BYTES,
        audio_format="mp3",
        video_format="webm",
        width=1080,
        height=1920,
        fps=30,
    )

    with pytest.raises(
        ValueError,
        match="Unsupported video format",
    ):
        renderer.render(request)


@pytest.mark.parametrize(
    "audio_format",
    [
        "",
        "../mp3",
        "mp3.exe",
    ],
)
def test_renderer_rejects_unsafe_audio_format(
    audio_format: str,
) -> None:
    renderer = FFmpegVideoRenderer()

    request = VideoRenderRequest(
        audio_data=_AUDIO_BYTES,
        audio_format=audio_format,
        video_format="mp4",
        width=1080,
        height=1920,
        fps=30,
    )

    with pytest.raises(
        ValueError,
        match="audio_format must be a simple media format",
    ):
        renderer.render(request)


def test_renderer_reports_ffmpeg_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del check
        del capture_output
        del text
        del timeout

        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="simulated render failure",
        )

    monkeypatch.setattr(
        "project_g.infrastructure.video.ffmpeg.subprocess.run",
        fake_run,
    )

    renderer = FFmpegVideoRenderer()

    with pytest.raises(
        FFmpegVideoRenderError,
        match="simulated render failure",
    ):
        renderer.render(_request())


def test_renderer_reports_missing_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del check
        del capture_output
        del text
        del timeout

        raise FileNotFoundError(command[0])

    monkeypatch.setattr(
        "project_g.infrastructure.video.ffmpeg.subprocess.run",
        fake_run,
    )

    renderer = FFmpegVideoRenderer()

    with pytest.raises(
        FFmpegVideoRenderError,
        match="Video executable was not found",
    ):
        renderer.render(_request())


def test_timeout_must_be_positive() -> None:
    with pytest.raises(
        ValueError,
        match="timeout_seconds must be positive",
    ):
        FFmpegVideoRenderer(
            timeout_seconds=0,
        )
