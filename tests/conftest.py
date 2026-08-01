"""Shared fixtures.

Media fixtures are generated with ffmpeg rather than committed. Two seconds of
``testsrc`` is a few kilobytes to produce and lets the suite exercise the real
filtergraph — mocking ffmpeg would test the mock, not the pipeline.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")


def make_clip(
    path,
    *,
    width: int = 320,
    height: int = 240,
    fps: int = 15,
    duration: float = 2.0,
    audio: bool = True,
    volume_db: float | None = None,
) -> str:
    """Generate a tiny synthetic clip."""
    args = [
        "ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}:duration={duration}",
    ]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
        if volume_db is not None:
            args += ["-af", f"volume={volume_db}dB"]
        args += ["-c:a", "aac"]
    args += [
        "-c:v", "libx264", "-crf", "35", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(args, check=True, capture_output=True)
    return str(path)


@pytest.fixture
def clip_factory(tmp_path):
    """Make clips on demand inside a per-test directory."""
    made: list[str] = []

    def factory(name: str = "clip.mp4", **kwargs) -> str:
        path = make_clip(tmp_path / name, **kwargs)
        made.append(path)
        return path

    return factory


@pytest.fixture
def input_dir(tmp_path):
    directory = tmp_path / "in"
    directory.mkdir()
    return directory
