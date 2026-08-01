"""Look presets.

A preset is a bundle of typographic and timing choices. It never touches
geometry maths — that lives in :mod:`caption` and stays resolution-relative —
so a preset scales correctly by construction.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    """One visual treatment for the caption layer."""

    description: str
    captions: bool
    primary_font: str
    secondary_font: str
    draw_box: bool
    shadow: int  # shadow offset in pixels at the 1080 baseline; 0 disables
    caption_scale: float
    font_color: str
    box_color: str
    show_seconds: float
    fade_seconds: float


PRESETS: dict[str, Preset] = {
    "news": Preset(
        description=(
            "Broadcast lower third: bold name over a lighter subtitle, both on a "
            "translucent bar. The most legible option over unpredictable footage."
        ),
        captions=True,
        primary_font="sans-bold",
        secondary_font="sans",
        draw_box=True,
        shadow=0,
        caption_scale=1.0,
        font_color="white",
        box_color="black@0.5",
        show_seconds=15.0,
        fade_seconds=1.0,
    ),
    "concert": Preset(
        description=(
            "Restrained programme styling: serif name, no bar, soft shadow for "
            "legibility, and a longer hold so an audience can read it."
        ),
        captions=True,
        primary_font="serif-bold",
        secondary_font="sans",
        draw_box=False,
        shadow=3,
        caption_scale=1.0,
        font_color="white",
        box_color="black@0.0",
        show_seconds=18.0,
        fade_seconds=1.5,
    ),
    "minimal": Preset(
        description=(
            "Logo bug only, no text. For footage that already carries its own "
            "titles, or when only enhancement and branding are wanted."
        ),
        captions=False,
        primary_font="sans-bold",
        secondary_font="sans",
        draw_box=False,
        shadow=0,
        caption_scale=1.0,
        font_color="white",
        box_color="black@0.0",
        show_seconds=0.0,
        fade_seconds=0.0,
    ),
}


def resolve(name: str) -> Preset:
    if name not in PRESETS:
        raise KeyError(name)
    return PRESETS[name]


def describe() -> list[tuple[str, str]]:
    """Preset table for the wizard and ``reelsmith doctor``."""
    return [(name, preset.description) for name, preset in sorted(PRESETS.items())]


def effective_look(cfg: dict) -> dict:
    """Merge a preset with any explicit ``look.*`` overrides from config.

    Config wins where the user set something; the preset fills the rest. The
    defaults for ``show_seconds`` and ``fade_seconds`` match the ``news`` preset,
    so a user who never touches them still gets each preset's own timing.
    """
    from .config import DEFAULTS

    preset = resolve(cfg["look"]["preset"])
    look = dict(cfg["look"])
    defaults = DEFAULTS["look"]

    def pick(key: str, preset_value):
        configured = look.get(key)
        if configured is None or configured == defaults.get(key):
            return preset_value
        return configured

    return {
        "captions": look["caption_enabled"] and preset.captions,
        "primary_font": look["font_primary"] or preset.primary_font,
        "secondary_font": look["font_secondary"] or preset.secondary_font,
        "draw_box": preset.draw_box,
        "shadow": preset.shadow,
        "caption_scale": preset.caption_scale,
        "font_color": pick("font_color", preset.font_color),
        "box_color": pick("box_color", preset.box_color),
        "show_seconds": pick("show_seconds", preset.show_seconds),
        "fade_seconds": pick("fade_seconds", preset.fade_seconds),
    }
