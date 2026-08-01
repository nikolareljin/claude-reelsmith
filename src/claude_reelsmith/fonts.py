"""Font discovery.

The predecessor tool hardcoded two Debian paths, so a missing font surfaced as
a raw ffmpeg ``drawtext`` error on any other distribution or OS. Here fonts are
searched across the usual locations for Linux, macOS and Windows, and a missing
font is reported as an actionable message before rendering starts.
"""

from __future__ import annotations

import functools
import glob
import os
import sys

# Ordered by preference. The first existing file wins.
_SERIF_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/liberation-serif/LiberationSerif-Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
)

_SANS_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)

_SANS_REGULAR = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
)

_SEARCH_ROOTS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    "/Library/Fonts",
    "/System/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
    "C:/Windows/Fonts",
)

FAMILIES = {
    "serif-bold": _SERIF_BOLD,
    "sans-bold": _SANS_BOLD,
    "sans": _SANS_REGULAR,
}


class FontNotFound(RuntimeError):
    """Raised when no usable font file can be located."""


def _first_existing(candidates: tuple[str, ...]) -> str | None:
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


@functools.lru_cache(maxsize=8)
def _scan_any(substrings: tuple[str, ...]) -> str | None:
    """Last resort: walk the font roots looking for a matching filename."""
    for root in _SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for path in glob.iglob(os.path.join(root, "**", "*.tt[fc]"), recursive=True):
            name = os.path.basename(path).lower()
            if any(sub in name for sub in substrings):
                return path
    return None


@functools.lru_cache(maxsize=8)
def resolve(family: str) -> str:
    """Return a font file path for a logical family name.

    ``family`` is one of :data:`FAMILIES`, or an explicit path, which is
    returned unchanged once verified.
    """
    if os.path.isabs(family) or os.path.sep in family:
        if not os.path.isfile(family):
            raise FontNotFound(f"Font file not found: {family}")
        return family

    candidates = FAMILIES.get(family)
    if candidates is None:
        raise FontNotFound(
            f"Unknown font family '{family}'. Known: {', '.join(sorted(FAMILIES))}, "
            f"or give an absolute path to a .ttf file."
        )

    found = _first_existing(candidates)
    if found:
        return found

    fallback_hints = {
        "serif-bold": ("serif-bold", "serifbd", "georgiab", "timesbd"),
        "sans-bold": ("sans-bold", "arialbd", "-bold"),
        "sans": ("dejavusans", "arial", "liberationsans", "sans"),
    }
    found = _scan_any(fallback_hints[family])
    if found:
        return found

    raise FontNotFound(
        f"No font found for '{family}'. Install a font package and retry "
        f"({_install_hint()}), or set look.font_primary / look.font_secondary "
        f"to an absolute .ttf path in reelsmith.yaml."
    )


def _install_hint() -> str:
    if sys.platform == "darwin":
        return "macOS ships suitable fonts; check /System/Library/Fonts"
    if sys.platform.startswith("win"):
        return "Windows ships suitable fonts; check C:/Windows/Fonts"
    return "Debian/Ubuntu: sudo apt install fonts-dejavu-core"


def available() -> dict[str, str | None]:
    """Report what is resolvable, for ``reelsmith doctor``."""
    out: dict[str, str | None] = {}
    for family in FAMILIES:
        try:
            out[family] = resolve(family)
        except FontNotFound:
            out[family] = None
    return out
