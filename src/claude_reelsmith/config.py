"""Configuration: defaults, YAML merge, validation.

``DEFAULTS`` is the single authoritative schema. A user's ``reelsmith.yaml`` is
deep-merged over it. Unlike the predecessor tool, unknown keys are an error
rather than a silent no-op — a typo in a config file should not look like a
feature that quietly does nothing.
"""

from __future__ import annotations

import copy
import os
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required. Install with: pip install claude-reelsmith"
    ) from exc

CONFIG_FILENAME = "reelsmith.yaml"

DEFAULTS: dict[str, Any] = {
    # Free-form context an agent may use when writing titles. Nothing here is
    # required, and nothing here is specific to any one kind of event.
    "project": {
        "title": None,
        "subtitle": None,
        "date": None,
        "location": None,
    },
    "io": {
        "input_dir": ".",
        "input_glob": "*",
        "output_dir": "./reelsmith-out",
        "work_dir": "./_work",
        "output_name_template": "{index:02d}_{slug}.mp4",
        "recursive": False,
    },
    # Which signals the agent is allowed to gather. The default set is
    # transcript + frames + metadata; `lite` mode turns the first two off.
    "analysis": {
        "transcribe": True,
        "frames": True,
        "metadata": True,
        "frame_count": 5,
        "transcribe_model": "small",
        "transcribe_language": None,
        "transcribe_seconds": 0,  # 0 means the whole clip
        "detect_chapters": True,
        "silence_threshold_db": -35.0,
        "silence_min_seconds": 2.0,
    },
    "look": {
        "preset": "news",
        "caption_enabled": True,
        "show_seconds": 15.0,
        "fade_seconds": 1.0,
        "font_primary": None,  # None means auto-discover
        "font_secondary": None,
        "font_color": "white",
        "box_color": "black@0.5",
        "accent_color": None,
    },
    "logo": {
        "source": None,
        "crop": None,  # "W:H:X:Y" applied after rasterisation
        "position": "top-right",
        "height_fraction": 0.1389,  # 150px at 1080p, preserving the old look
        "margin_fraction": 0.0509,  # 55px at 1080p
        "opacity": 1.0,
    },
    "slate": {
        "intro_enabled": False,
        "intro_seconds": 2.5,
        "outro_enabled": False,
        "outro_seconds": 2.0,
        "outro_text": None,
        "background": "black",
    },
    "audio": {
        "profile": "music",
        "chain": None,  # only used when profile == "custom"
        "two_pass": True,
        "target_lufs": None,  # overrides the profile's target when set
    },
    "video": {
        "stabilize": True,
        "shakiness": 6,
        "accuracy": 12,
        "smoothing": 24,
        "zoom": 0,
        "unsharp": "5:5:0.8",
        "target_height": None,  # None means "match the most common input"
        "target_fps": None,
    },
    "encode": {
        "encoder": "auto",  # auto | libx264 | h264_nvenc | h264_vaapi | ...
        "quality": 18,  # CRF-equivalent; mapped per encoder
        "preset": "medium",
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "192k",
        "faststart": True,
        "jobs": 0,  # 0 means cores/2
    },
    "subtitles": {
        "sidecar": True,  # write .srt next to the output
        "burn_in": False,
    },
    "marking": {
        "embed_metadata": True,
        "rename": True,
        "chapters_file": True,
    },
}

_VALID_POSITIONS = {"top-right", "top-left", "bottom-right", "bottom-left"}


class ConfigError(RuntimeError):
    """Raised for a malformed or invalid configuration."""


def _deep_merge(base: dict[str, Any], override: dict[str, Any], path: str = "") -> dict[str, Any]:
    """Merge ``override`` into a copy of ``base``, rejecting unknown keys."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        where = f"{path}.{key}" if path else key
        if key not in out:
            raise ConfigError(
                f"Unknown configuration key '{where}'. "
                f"Valid keys here: {', '.join(sorted(out))}"
            )
        if isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value, where)
        else:
            out[key] = value
    return out


def load(path: str | None) -> dict[str, Any]:
    """Load configuration, deep-merged over :data:`DEFAULTS`."""
    cfg = copy.deepcopy(DEFAULTS)
    if not path:
        return cfg
    if not os.path.isfile(path):
        raise ConfigError(f"Config file not found: {path}")
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Config file must contain a YAML mapping: {path}")
    return _deep_merge(cfg, raw)


def find_config(start: str = ".") -> str | None:
    """Look for ``reelsmith.yaml`` in ``start`` then its parents."""
    here = os.path.abspath(start)
    while True:
        candidate = os.path.join(here, CONFIG_FILENAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def validate(cfg: dict[str, Any]) -> None:
    """Check values that would otherwise fail deep inside ffmpeg."""
    from . import audio, presets  # local import avoids a cycle

    preset = cfg["look"]["preset"]
    if preset not in presets.PRESETS:
        raise ConfigError(
            f"Unknown look preset '{preset}'. Available: {', '.join(sorted(presets.PRESETS))}"
        )

    profile = cfg["audio"]["profile"]
    if profile not in audio.PROFILES and profile != "custom":
        raise ConfigError(
            f"Unknown audio profile '{profile}'. "
            f"Available: {', '.join(sorted(audio.PROFILES))}, custom"
        )
    if profile == "custom" and not cfg["audio"]["chain"]:
        raise ConfigError("audio.profile is 'custom' but audio.chain is empty.")

    position = cfg["logo"]["position"]
    if position not in _VALID_POSITIONS:
        raise ConfigError(
            f"Unknown logo position '{position}'. Available: {', '.join(sorted(_VALID_POSITIONS))}"
        )

    if not 0.0 < cfg["logo"]["opacity"] <= 1.0:
        raise ConfigError("logo.opacity must be greater than 0 and at most 1.")

    if cfg["look"]["fade_seconds"] * 2 > cfg["look"]["show_seconds"]:
        raise ConfigError(
            "look.fade_seconds is too long: two fades must fit inside look.show_seconds."
        )

    jobs = cfg["encode"]["jobs"]
    if not isinstance(jobs, int) or jobs < 0:
        raise ConfigError("encode.jobs must be a non-negative integer (0 selects automatically).")


def dump(cfg: dict[str, Any]) -> str:
    """Serialise a config back to YAML, for ``reelsmith init``."""
    return yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, default_flow_style=False)


def resolve_jobs(cfg: dict[str, Any]) -> int:
    """Worker count: explicit setting, else half the cores, at least one."""
    configured = cfg["encode"]["jobs"]
    if configured:
        return configured
    return max(1, (os.cpu_count() or 2) // 2)
