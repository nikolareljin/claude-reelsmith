"""Audio enhancement profiles and loudness normalisation.

The three original profiles are carried over unchanged from the tool this
package replaces — they encode real tuning against real phone-recorded concert
audio and are not worth re-deriving.

What is new is two-pass ``loudnorm``. Run single-pass, ``loudnorm`` works in a
dynamic mode that only approaches the target; run it twice, feeding the first
pass's measurements back in, and it hits the target and stays linear. Because
``reelsmith analyze`` already reads every file, the measurement pass is close to
free, so two-pass is the default.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Profile:
    """A named audio treatment.

    ``pre`` runs before ``loudnorm`` and does the tone shaping and levelling;
    ``loudnorm`` then lands the result on a defined loudness; ``post`` is a
    safety limiter that catches inter-sample peaks.
    """

    description: str
    pre: str
    target_i: float
    target_tp: float
    target_lra: float
    post: str


PROFILES: dict[str, Profile] = {
    "gentle": Profile(
        description="Light touch. Preserves dynamics; use when the recording is already good.",
        pre="highpass=f=60,dynaudnorm=f=500:g=31:p=0.9:m=10:s=0",
        target_i=-16.0,
        target_tp=-1.5,
        target_lra=11.0,
        post="alimiter=limit=0.95",
    ),
    "standard": Profile(
        description="Balanced default for mixed material.",
        pre="highpass=f=50,dynaudnorm=f=400:g=31:p=0.92:m=15:s=0",
        target_i=-14.0,
        target_tp=-1.5,
        target_lra=11.0,
        post="alimiter=limit=0.96",
    ),
    "music": Profile(
        description=(
            "Loud and forward, tuned on live acoustic piano recorded at a distance. "
            "Lifts quiet passages hard without pumping."
        ),
        pre=(
            "highpass=f=50,"
            "acompressor=threshold=-20dB:ratio=2.5:attack=20:release=300:makeup=2,"
            "dynaudnorm=f=350:g=31:p=0.95:m=30:s=6"
        ),
        target_i=-13.0,
        target_tp=-1.5,
        target_lra=9.0,
        post="alimiter=limit=0.97",
    ),
    "speech": Profile(
        description="Interviews and talking heads. Cuts rumble, tightens dynamics for clarity.",
        pre=(
            "highpass=f=80,"
            "acompressor=threshold=-18dB:ratio=3:attack=10:release=200:makeup=3,"
            "dynaudnorm=f=300:g=15:p=0.9:m=20:s=0"
        ),
        target_i=-16.0,
        target_tp=-1.5,
        target_lra=7.0,
        post="alimiter=limit=0.96",
    ),
    "broadcast": Profile(
        description="EBU R128 delivery target (-23 LUFS). Use when a broadcaster requires it.",
        pre="highpass=f=50,dynaudnorm=f=500:g=31:p=0.9:m=10:s=0",
        target_i=-23.0,
        target_tp=-1.0,
        target_lra=7.0,
        post="alimiter=limit=0.93",
    ),
    "web": Profile(
        description="Streaming-platform target (-14 LUFS). Safe for YouTube and similar.",
        pre="highpass=f=50,dynaudnorm=f=400:g=31:p=0.92:m=15:s=0",
        target_i=-14.0,
        target_tp=-1.0,
        target_lra=11.0,
        post="alimiter=limit=0.96",
    ),
}

# The predecessor's profile name, kept so an old config keeps working.
ALIASES = {"loud-piano": "music"}


def resolve_profile(name: str) -> Profile:
    name = ALIASES.get(name, name)
    if name not in PROFILES:
        raise KeyError(name)
    return PROFILES[name]


def _loudnorm_args(profile: Profile, target_i: float | None) -> tuple[float, float, float]:
    return (target_i if target_i is not None else profile.target_i,
            profile.target_tp,
            profile.target_lra)


def measure_chain(audio_cfg: dict[str, Any]) -> str:
    """Filter chain for the measurement pass.

    ``loudnorm`` must see exactly the signal it will see during the render, so
    the pre-chain is applied here too.
    """
    profile_name = audio_cfg["profile"]
    if profile_name == "custom":
        # A custom chain is opaque; there is nothing meaningful to measure.
        return ""
    profile = resolve_profile(profile_name)
    i, tp, lra = _loudnorm_args(profile, audio_cfg.get("target_lufs"))
    return f"{profile.pre},loudnorm=I={i}:TP={tp}:LRA={lra}:print_format=json"


def measure(path: str, audio_cfg: dict[str, Any], *, timeout: float | None = None) -> dict | None:
    """Run the measurement pass and return ffmpeg's loudness statistics.

    Returns ``None`` when measurement is not applicable (custom chain) or when
    ffmpeg produced no parsable JSON, in which case the caller falls back to
    single-pass normalisation.
    """
    chain = measure_chain(audio_cfg)
    if not chain:
        return None

    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-i", path,
        "-vn", "-af", chain, "-f", "null", "-",
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)  # noqa: S603
    if proc.returncode != 0:
        return None
    return _parse_loudnorm_json(proc.stderr)


def _parse_loudnorm_json(stderr: str) -> dict | None:
    """Extract the trailing JSON object ffmpeg prints after the log lines."""
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def render_chain(audio_cfg: dict[str, Any], measured: dict | None = None) -> str:
    """Build the filter chain used during the actual render.

    When ``measured`` is supplied the ``loudnorm`` stage runs in linear mode and
    lands precisely on the target. Without it the stage falls back to the
    dynamic single-pass behaviour, which still improves the audio but is less
    accurate.
    """
    profile_name = audio_cfg["profile"]
    if profile_name == "custom":
        chain = audio_cfg.get("chain")
        if not chain:
            raise ValueError("audio.profile is 'custom' but audio.chain is empty.")
        return chain

    profile = resolve_profile(profile_name)
    i, tp, lra = _loudnorm_args(profile, audio_cfg.get("target_lufs"))

    loudnorm = f"loudnorm=I={i}:TP={tp}:LRA={lra}"
    if audio_cfg.get("two_pass", True) and measured and _measurements_usable(measured):
        loudnorm += (
            f":measured_I={measured['input_i']}"
            f":measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}"
            f":measured_thresh={measured['input_thresh']}"
            f":offset={measured.get('target_offset', 0.0)}"
            f":linear=true:print_format=summary"
        )

    return f"{profile.pre},{loudnorm},{profile.post}"


def _measurements_usable(measured: dict) -> bool:
    """Reject the sentinel values ffmpeg emits for silent or degenerate input.

    A fully silent track measures as ``-inf`` / ``-70``; feeding those back in
    makes loudnorm apply enormous gain to noise.
    """
    required = ("input_i", "input_tp", "input_lra", "input_thresh")
    if not all(key in measured for key in required):
        return False
    try:
        values = [float(measured[key]) for key in required]
    except (TypeError, ValueError):
        return False
    if any(value != value or value in (float("-inf"), float("inf")) for value in values):
        return False
    # -70 LUFS is ffmpeg's floor; anything at or below it is effectively silence.
    return float(measured["input_i"]) > -70.0


def describe() -> list[tuple[str, str, float]]:
    """Profile table for ``reelsmith doctor`` and the wizard."""
    return [(name, p.description, p.target_i) for name, p in sorted(PROFILES.items())]
