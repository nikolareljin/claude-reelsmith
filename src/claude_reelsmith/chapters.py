"""Segmenting a long continuous recording.

One unbroken take of a concert or a conference session contains several items
separated by applause and silence. ``silencedetect`` finds the gaps; the
midpoint of each sufficiently long gap becomes a boundary.

The output is an ffmetadata chapter file, which ffmpeg and most players
understand, plus optional real cut points.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Silence:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def midpoint(self) -> float:
        return self.start + self.duration / 2


@dataclass(frozen=True)
class Chapter:
    index: int
    start: float
    end: float
    title: str

    @property
    def duration(self) -> float:
        return self.end - self.start


_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silences(
    path: str,
    *,
    threshold_db: float = -35.0,
    min_seconds: float = 2.0,
    timeout: float | None = None,
) -> list[Silence]:
    """Find silent stretches using ffmpeg's ``silencedetect``."""
    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-i", path,
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_seconds}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)  # noqa: S603
    if proc.returncode != 0:
        return []

    starts = [float(m) for m in _START_RE.findall(proc.stderr)]
    ends = [float(m) for m in _END_RE.findall(proc.stderr)]

    silences: list[Silence] = []
    for index, start in enumerate(starts):
        # A silence running to the end of the file has no matching end marker.
        end = ends[index] if index < len(ends) else start + min_seconds
        if end > start:
            silences.append(Silence(start=max(0.0, start), end=end))
    return silences


def derive_chapters(
    duration: float,
    silences: list[Silence],
    *,
    min_chapter_seconds: float = 20.0,
    title_template: str = "Item {index}",
) -> list[Chapter]:
    """Turn silences into chapters.

    Gaps that would produce an implausibly short chapter are ignored — a
    two-second pause mid-performance is not a new item.
    """
    if duration <= 0:
        return []

    boundaries = [0.0]
    for silence in silences:
        candidate = silence.midpoint
        if candidate - boundaries[-1] >= min_chapter_seconds:
            boundaries.append(candidate)
    boundaries.append(duration)

    # Fold a too-short trailing chapter back into its predecessor.
    if len(boundaries) > 2 and boundaries[-1] - boundaries[-2] < min_chapter_seconds:
        boundaries.pop(-2)

    chapters: list[Chapter] = []
    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        chapters.append(
            Chapter(
                index=index + 1,
                start=start,
                end=end,
                title=title_template.format(index=index + 1),
            )
        )
    return chapters


def to_ffmetadata(chapters: list[Chapter]) -> str:
    """Serialise chapters in ffmpeg's metadata format."""
    lines = [";FFMETADATA1"]
    for chapter in chapters:
        lines.append("")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={int(round(chapter.start * 1000))}")
        lines.append(f"END={int(round(chapter.end * 1000))}")
        lines.append(f"title={chapter.title}")
    return "\n".join(lines) + "\n"


def to_plain_text(chapters: list[Chapter]) -> str:
    """Human-readable chapter list, the kind pasted into a video description."""
    lines = []
    for chapter in chapters:
        total = int(chapter.start)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        stamp = f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:d}:{seconds:02d}"
        lines.append(f"{stamp}  {chapter.title}")
    return "\n".join(lines) + "\n" if lines else ""
