"""Reconciling heterogeneous input.

Real folders hold mixed footage: two phones at different resolutions, one clip
shot portrait, a camera at 25fps beside one at 30. The predecessor assumed
1080p landscape throughout and failed the whole batch when that was untrue.

The rule here is **scale and pad, never crop**. Cropping to fit silently
discards picture the user shot, and a batch that quietly loses the edge of the
frame is worse than one that adds a letterbox.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .probe import MediaInfo


@dataclass(frozen=True)
class Target:
    """The common canvas every clip is rendered onto."""

    width: int
    height: int
    fps: float

    @property
    def is_portrait(self) -> bool:
        return self.height > self.width

    def __str__(self) -> str:
        return f"{self.width}x{self.height} @ {self.fps:g}fps"


def _even(value: int) -> int:
    """H.264 requires even dimensions in 4:2:0."""
    return value if value % 2 == 0 else value + 1


def choose_target(
    infos: list[MediaInfo],
    *,
    target_height: int | None = None,
    target_fps: float | None = None,
) -> Target:
    """Pick the canvas from the inputs, honouring explicit overrides.

    The most common frame shape wins rather than the largest: if twenty clips
    are 1080p and one stray clip is 4K, upscaling everything to 4K would cost
    hours of encoding for no gain.
    """
    if not infos:
        raise ValueError("Cannot choose a target from an empty input set.")

    shapes = Counter((info.display_width, info.display_height) for info in infos)
    # Ties break toward the larger frame, which loses the least detail.
    width, height = max(shapes.items(), key=lambda kv: (kv[1], kv[0][0] * kv[0][1]))[0]

    if target_height:
        aspect = width / height if height else 16 / 9
        height = target_height
        width = _even(round(target_height * aspect))

    rates = Counter(round(info.fps, 3) for info in infos if info.fps > 0)
    fps = target_fps or (max(rates.items(), key=lambda kv: (kv[1], kv[0]))[0] if rates else 30.0)

    return Target(width=_even(width), height=_even(height), fps=float(fps))


def needs_scaling(info: MediaInfo, target: Target) -> bool:
    return (info.display_width, info.display_height) != (target.width, target.height)


def video_filter(info: MediaInfo, target: Target, *, pad_color: str = "black") -> str:
    """Filter fragment bringing one clip onto the target canvas.

    Returns an empty string when the clip already matches, so the filtergraph
    stays as short as possible.
    """
    parts: list[str] = []

    if needs_scaling(info, target):
        parts.append(
            f"scale={target.width}:{target.height}:force_original_aspect_ratio=decrease"
        )
        parts.append(
            f"pad={target.width}:{target.height}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
        )
        parts.append("setsar=1")

    if info.fps and abs(info.fps - target.fps) > 0.01:
        parts.append(f"fps={target.fps}")

    return ",".join(parts)


def audio_input_args(info: MediaInfo) -> list[str]:
    """Extra ffmpeg inputs needed to give a silent clip an audio track.

    Mapping ``[0:a]`` on a clip with no audio stream is a hard failure. Adding a
    silent source keeps the clip in the batch, correctly branded and titled,
    instead of dropping it.
    """
    if info.has_audio:
        return []
    return ["-f", "lavfi", "-t", f"{max(info.duration, 0.1):.3f}", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000"]


def summarize(infos: list[MediaInfo], target: Target) -> str:
    """One-line description of how mixed the input set is."""
    shapes = Counter((i.display_width, i.display_height) for i in infos)
    rates = Counter(round(i.fps) for i in infos if i.fps > 0)
    silent = sum(1 for i in infos if not i.has_audio)

    bits = [f"{len(infos)} clips", f"target {target}"]
    if len(shapes) > 1:
        bits.append(f"{len(shapes)} different frame sizes")
    if len(rates) > 1:
        bits.append(f"{len(rates)} different frame rates")
    if silent:
        bits.append(f"{silent} with no audio track")
    return ", ".join(bits)
