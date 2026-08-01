"""Local speech-to-text.

Transcription runs entirely on this machine through ``faster-whisper``. No
audio ever leaves the user's computer, and no API key is involved. The
dependency is optional: without it the tool degrades to the metadata-only path
rather than failing.

The transcript serves two purposes — it gives an agent something to reason
about when naming a clip, and it becomes the ``.srt`` sidecar.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass

from . import ff
from .notify import Notify


class TranscribeUnavailable(RuntimeError):
    """Raised when faster-whisper is not installed."""


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    language: str
    text: str
    segments: list[Segment]

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "text": self.text,
            "segments": [asdict(segment) for segment in self.segments],
        }

    def head(self, characters: int = 600) -> str:
        """Opening of the transcript, which usually carries the announcement."""
        return self.text[:characters]


def is_available() -> bool:
    try:
        import faster_whisper  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def extract_audio(source: str, out_wav: str, *, seconds: float = 0) -> str:
    """Pull mono 16kHz audio, which is what Whisper wants anyway."""
    args = []
    if seconds and seconds > 0:
        # Placed before -i so ffmpeg limits decoding rather than filtering.
        args += ["-t", f"{seconds:g}"]
    args += ["-i", source, "-vn", "-ac", "1", "-ar", "16000", out_wav]
    ff.run_ffmpeg(args)
    return out_wav


def transcribe(
    source: str,
    *,
    model_name: str = "small",
    language: str | None = None,
    seconds: float = 0,
) -> Transcript:
    """Transcribe a media file.

    ``seconds`` of 0 means the whole clip. Limiting it is much faster when the
    goal is only to hear an announcement at the top of a recording.
    """
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415
    except ImportError as exc:
        raise TranscribeUnavailable(
            "faster-whisper is not installed. Install it with: "
            "pip install 'claude-reelsmith[transcribe]'"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="reelsmith-asr-") as tmp:
        wav = extract_audio(source, os.path.join(tmp, "audio.wav"), seconds=seconds)
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments_iter, info = model.transcribe(wav, beam_size=5, language=language)
        segments = [
            Segment(start=float(s.start), end=float(s.end), text=s.text.strip())
            for s in segments_iter
        ]

    return Transcript(
        language=getattr(info, "language", language or "") or "",
        text=" ".join(segment.text for segment in segments).strip(),
        segments=segments,
    )


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    milliseconds = int(round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def to_srt(transcript: Transcript) -> str:
    """Render a transcript as SubRip."""
    lines: list[str] = []
    for number, segment in enumerate(transcript.segments, start=1):
        if not segment.text:
            continue
        lines.append(str(number))
        lines.append(f"{_srt_timestamp(segment.start)} --> {_srt_timestamp(segment.end)}")
        lines.append(segment.text)
        lines.append("")
    return "\n".join(lines)


def write_srt(transcript: Transcript, path: str) -> str | None:
    """Write an ``.srt`` sidecar. Returns the path, or None when empty."""
    body = to_srt(transcript)
    if not body.strip():
        Notify.warn(f"No speech detected; skipping subtitle sidecar for {os.path.basename(path)}")
        return None
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    return path
