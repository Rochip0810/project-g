import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from project_g.ports.video import (
    RenderedVideo,
    VideoRenderer,
    VideoRenderRequest,
)

_MAX_FORMAT_LENGTH = 16


class FFmpegVideoRenderError(RuntimeError):
    """Raised when FFmpeg cannot render or inspect a video."""


class FFmpegVideoRenderer(VideoRenderer):
    def __init__(
        self,
        *,
        ffmpeg_binary: str = "ffmpeg",
        ffprobe_binary: str = "ffprobe",
        timeout_seconds: float = 120.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._ffmpeg_binary = ffmpeg_binary
        self._ffprobe_binary = ffprobe_binary
        self._timeout_seconds = timeout_seconds

    def render(
        self,
        request: VideoRenderRequest,
    ) -> RenderedVideo:
        if not request.audio_data:
            raise ValueError("audio_data must not be empty")

        audio_format = self._normalize_format(
            request.audio_format,
            field_name="audio_format",
        )
        video_format = self._normalize_format(
            request.video_format,
            field_name="video_format",
        )

        if video_format != "mp4":
            raise ValueError(f"Unsupported video format: {video_format}")

        if request.width < 1:
            raise ValueError("width must be at least 1")

        if request.height < 1:
            raise ValueError("height must be at least 1")

        if request.fps < 1:
            raise ValueError("fps must be at least 1")

        with TemporaryDirectory(
            prefix="project-g-video-",
        ) as temporary_directory:
            temporary_root = Path(temporary_directory)

            input_path = temporary_root / f"narration.{audio_format}"
            output_path = temporary_root / f"rendered.{video_format}"

            input_path.write_bytes(request.audio_data)

            self._render_video(
                input_path=input_path,
                output_path=output_path,
                width=request.width,
                height=request.height,
                fps=request.fps,
            )

            if not output_path.is_file():
                raise FFmpegVideoRenderError("FFmpeg completed without producing a video")

            video_data = output_path.read_bytes()

            if not video_data:
                raise FFmpegVideoRenderError("FFmpeg produced an empty video")

            duration_ms = self._probe_duration_ms(
                output_path=output_path,
            )

        return RenderedVideo(
            data=video_data,
            duration_ms=duration_ms,
        )

    def _render_video(
        self,
        *,
        input_path: Path,
        output_path: Path,
        width: int,
        height: int,
        fps: int,
    ) -> None:
        command = [
            self._ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:r={fps}",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        self._run(command)

    def _probe_duration_ms(
        self,
        *,
        output_path: Path,
    ) -> int:
        command = [
            self._ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ]

        result = self._run(command)

        try:
            duration_seconds = float(result.stdout.strip())
        except ValueError as error:
            raise FFmpegVideoRenderError("FFprobe returned an invalid duration") from error

        duration_ms = round(duration_seconds * 1000)

        if duration_ms < 1:
            raise FFmpegVideoRenderError("FFprobe returned a non-positive duration")

        return duration_ms

    def _run(
        self,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError as error:
            raise FFmpegVideoRenderError(f"Video executable was not found: {command[0]}") from error
        except subprocess.TimeoutExpired as error:
            raise FFmpegVideoRenderError(f"Video command timed out: {command[0]}") from error

        if result.returncode != 0:
            detail = result.stderr.strip()

            if detail:
                detail = detail[-1000:]
                raise FFmpegVideoRenderError(f"Video command failed: {command[0]}: {detail}")

            raise FFmpegVideoRenderError(f"Video command failed: {command[0]}")

        return result

    @staticmethod
    def _normalize_format(
        value: str,
        *,
        field_name: str,
    ) -> str:
        normalized = value.strip().lower()

        if not normalized or len(normalized) > _MAX_FORMAT_LENGTH or not normalized.isalnum():
            raise ValueError(f"{field_name} must be a simple media format")

        return normalized
