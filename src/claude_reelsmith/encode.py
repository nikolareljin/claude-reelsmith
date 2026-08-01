"""Encoder selection.

``ffmpeg -encoders`` lists what was *compiled in*, not what actually works: a
build with NVENC support on a machine with no NVIDIA card still advertises
``h264_nvenc`` and then fails at render time. So candidates are verified by
encoding a handful of frames of synthetic video and checking the exit code.
The probe costs well under a second and is cached for the process.

Quality is expressed once, on a CRF-like scale, and mapped per encoder. Users
should not have to know that NVENC calls it ``-cq`` and VideoToolbox uses an
inverted 1-100 scale.
"""

from __future__ import annotations

import functools
import os
import subprocess
from dataclasses import dataclass, field

from . import ff


@dataclass(frozen=True)
class Encoder:
    """How to drive one video encoder."""

    name: str
    description: str
    hardware: bool
    init_args: list[str] = field(default_factory=list)
    filter_suffix: str = ""

    def output_args(self, quality: int, preset: str) -> list[str]:
        return _QUALITY_MAP[self.name](quality, preset)


def _x26x(quality: int, preset: str) -> list[str]:
    return ["-crf", str(quality), "-preset", preset]


def _nvenc(quality: int, preset: str) -> list[str]:
    # NVENC presets are p1 (fastest) to p7 (slowest). Map the libx264 vocabulary
    # onto that scale so the same config works on either encoder.
    mapping = {
        "ultrafast": "p1", "superfast": "p1", "veryfast": "p2", "faster": "p3",
        "fast": "p4", "medium": "p4", "slow": "p5", "slower": "p6", "veryslow": "p7",
    }
    return ["-rc", "vbr", "-cq", str(quality), "-preset", mapping.get(preset, "p4"), "-b:v", "0"]


def _qsv(quality: int, _preset: str) -> list[str]:
    return ["-global_quality", str(quality), "-look_ahead", "1"]


def _vaapi(quality: int, _preset: str) -> list[str]:
    return ["-rc_mode", "CQP", "-qp", str(quality)]


def _videotoolbox(quality: int, _preset: str) -> list[str]:
    # VideoToolbox quality runs 1-100 with higher meaning better, the opposite
    # of CRF. CRF 18 lands around 70, CRF 28 around 45.
    mapped = max(1, min(100, round(100 - quality * 1.9)))
    return ["-q:v", str(mapped)]


_QUALITY_MAP = {
    "libx264": _x26x,
    "libx265": _x26x,
    "h264_nvenc": _nvenc,
    "hevc_nvenc": _nvenc,
    "h264_qsv": _qsv,
    "h264_vaapi": _vaapi,
    "h264_videotoolbox": _videotoolbox,
    "h264_amf": _x26x,
}

_VAAPI_DEVICE = os.environ.get("REELSMITH_VAAPI_DEVICE", "/dev/dri/renderD128")

# Ordered best-first. Hardware encoders are preferred for throughput; libx264
# is the guaranteed fallback and the quality reference.
CANDIDATES: list[Encoder] = [
    Encoder("h264_nvenc", "NVIDIA NVENC", hardware=True),
    Encoder("h264_qsv", "Intel Quick Sync", hardware=True),
    Encoder(
        "h264_vaapi",
        "VAAPI (Intel/AMD on Linux)",
        hardware=True,
        init_args=["-vaapi_device", _VAAPI_DEVICE],
        filter_suffix="format=nv12,hwupload",
    ),
    Encoder("h264_videotoolbox", "Apple VideoToolbox", hardware=True),
    Encoder("h264_amf", "AMD AMF", hardware=True),
    Encoder("libx264", "libx264 (software)", hardware=False),
]

BY_NAME = {enc.name: enc for enc in CANDIDATES}


def _smoke_test(encoder: Encoder) -> bool:
    """Encode a few synthetic frames to confirm the encoder really runs."""
    vf = "format=nv12,hwupload" if encoder.filter_suffix else "format=yuv420p"
    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        *encoder.init_args,
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=0.3",
        "-vf", vf,
        "-c:v", encoder.name,
        "-frames:v", "3",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30)  # noqa: S603
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


@functools.lru_cache(maxsize=1)
def available() -> tuple[Encoder, ...]:
    """Encoders that are both compiled in and verified working, best first."""
    caps = ff.capabilities()
    working = []
    for encoder in CANDIDATES:
        if not caps.has_encoder(encoder.name):
            continue
        if encoder.hardware and not _smoke_test(encoder):
            continue
        working.append(encoder)
    return tuple(working)


def select(name: str = "auto") -> Encoder:
    """Choose an encoder by name, or the best working one when ``auto``."""
    working = available()
    if name != "auto":
        if name not in BY_NAME:
            raise ValueError(
                f"Unknown encoder '{name}'. Known: {', '.join(sorted(BY_NAME))}, or 'auto'."
            )
        chosen = BY_NAME[name]
        if chosen not in working:
            raise ValueError(
                f"Encoder '{name}' is not usable on this machine. "
                f"Working encoders: {', '.join(e.name for e in working) or 'none'}."
            )
        return chosen

    if not working:
        raise RuntimeError(
            "No usable video encoder found. Install an ffmpeg build with libx264 "
            "(Debian/Ubuntu: sudo apt install ffmpeg)."
        )
    return working[0]


def describe() -> list[tuple[str, str, bool, bool]]:
    """Encoder table for ``reelsmith doctor``: name, description, hw, working."""
    caps = ff.capabilities()
    working = {enc.name for enc in available()}
    return [
        (enc.name, enc.description, enc.hardware, enc.name in working)
        for enc in CANDIDATES
        if caps.has_encoder(enc.name)
    ]
