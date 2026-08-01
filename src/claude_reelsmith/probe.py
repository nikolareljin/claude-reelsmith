"""Media inspection via ffprobe.

Everything downstream — caption geometry, normalisation targets, encoder
choice — depends on knowing the real shape of each input, including the
rotation metadata that phones write instead of rotating pixels.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from fractions import Fraction

from . import ff


@dataclass(frozen=True)
class MediaInfo:
    """What ffprobe knows about one file."""

    path: str
    duration: float
    width: int
    height: int
    fps: float
    rotation: int
    has_audio: bool
    audio_channels: int
    audio_sample_rate: int
    video_codec: str
    audio_codec: str
    pix_fmt: str
    size_bytes: int
    mtime: float

    @property
    def display_width(self) -> int:
        """Width after rotation metadata is applied."""
        return self.height if abs(self.rotation) in (90, 270) else self.width

    @property
    def display_height(self) -> int:
        return self.width if abs(self.rotation) in (90, 270) else self.height

    @property
    def is_portrait(self) -> bool:
        return self.display_height > self.display_width

    def to_dict(self) -> dict:
        data = asdict(self)
        data["display_width"] = self.display_width
        data["display_height"] = self.display_height
        return data


class ProbeError(RuntimeError):
    """Raised when a file cannot be probed or has no video stream."""


def _parse_fps(rate: str | None) -> float:
    if not rate or rate in ("0/0", "N/A"):
        return 0.0
    try:
        return float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _parse_rotation(stream: dict) -> int:
    """Rotation may live in side data or in a legacy tag, depending on ffmpeg."""
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            try:
                return int(round(float(side["rotation"])))
            except (TypeError, ValueError):
                continue
    tag = (stream.get("tags") or {}).get("rotate")
    if tag is not None:
        try:
            return int(round(float(tag)))
        except (TypeError, ValueError):
            return 0
    return 0


def probe(path: str) -> MediaInfo:
    """Inspect one media file."""
    if not os.path.isfile(path):
        raise ProbeError(f"File not found: {path}")

    proc = ff.run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe returned unparsable output for {path}") from exc

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video is None:
        raise ProbeError(
            f"No video stream in {path}. reelsmith processes video files; "
            f"check io.input_glob if this file was matched by mistake."
        )

    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or video.get("duration") or 0.0)
    stat = os.stat(path)

    return MediaInfo(
        path=os.path.abspath(path),
        duration=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        rotation=_parse_rotation(video),
        has_audio=audio is not None,
        audio_channels=int((audio or {}).get("channels") or 0),
        audio_sample_rate=int((audio or {}).get("sample_rate") or 0),
        video_codec=str(video.get("codec_name") or "unknown"),
        audio_codec=str((audio or {}).get("codec_name") or ""),
        pix_fmt=str(video.get("pix_fmt") or ""),
        size_bytes=stat.st_size,
        mtime=stat.st_mtime,
    )


def probe_all(paths: list[str]) -> tuple[list[MediaInfo], list[tuple[str, str]]]:
    """Probe many files, collecting failures instead of aborting the batch."""
    infos: list[MediaInfo] = []
    failures: list[tuple[str, str]] = []
    for path in paths:
        try:
            infos.append(probe(path))
        except (ProbeError, ff.FFmpegError) as exc:
            failures.append((path, str(exc).splitlines()[0]))
    return infos, failures
