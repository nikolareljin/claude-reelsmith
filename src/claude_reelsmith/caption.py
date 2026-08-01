"""Lower-third captions and logo placement.

Two things here are load-bearing.

**Geometry is resolution-relative.** The predecessor hardcoded pixel offsets
(``y=h-185``, ``fontsize=52``, logo height 150) which silently assumed 1080p and
broke on 4K or vertical footage. Every value is now derived from a scale
reference — the frame's *shorter* side — against a 1080 baseline. At 1920x1080
the arithmetic reproduces the original pixel values exactly; everywhere else it
scales correctly, and portrait footage gets text sized for its narrow width
rather than its tall height.

**Text never enters the filter string.** Captions are passed to ``drawtext`` via
``textfile=`` sidecars. A performer name containing an apostrophe, comma, colon
or accent would otherwise have to survive several layers of ffmpeg escaping.
Writing it to a file sidesteps the problem completely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# All coefficients are expressed against this baseline, so a 1080-pixel scale
# reference reproduces the original design pixel-for-pixel.
REFERENCE = 1080

_PRIMARY_SIZE = 52 / REFERENCE
_SECONDARY_SIZE = 38 / REFERENCE
_PRIMARY_BOTTOM = 185 / REFERENCE
_SECONDARY_BOTTOM = 105 / REFERENCE
_PRIMARY_BORDER = 20 / REFERENCE
_SECONDARY_BORDER = 14 / REFERENCE
_MARGIN_X = 60 / REFERENCE

# Average glyph advance as a fraction of nominal font size, for DejaVu-like
# faces. Used only to budget caption length, never for layout.
_AVG_GLYPH_RATIO = 0.52


@dataclass(frozen=True)
class Geometry:
    """Concrete pixel geometry for one frame size."""

    width: int
    height: int
    scale_ref: int
    primary_size: int
    secondary_size: int
    primary_y: int
    secondary_y: int
    margin_x: int
    primary_border: int
    secondary_border: int

    @property
    def primary_max_chars(self) -> int:
        return _max_chars(self.width, self.margin_x, self.primary_size)

    @property
    def secondary_max_chars(self) -> int:
        return _max_chars(self.width, self.margin_x, self.secondary_size)


def _max_chars(width: int, margin_x: int, font_size: int) -> int:
    usable = max(0, width - 2 * margin_x)
    return max(1, int(usable / (font_size * _AVG_GLYPH_RATIO)))


def scale_reference(width: int, height: int) -> int:
    """The dimension caption sizing is derived from.

    The shorter side is used so that portrait video gets text proportioned to
    the narrow axis, which is the one that actually constrains a caption.
    """
    return min(width, height)


def geometry(width: int, height: int, *, scale: float = 1.0) -> Geometry:
    """Compute caption geometry for a frame size.

    ``scale`` lets a look preset make its captions uniformly larger or smaller
    without restating every coefficient.
    """
    ref = scale_reference(width, height) * scale
    primary_size = max(8, round(ref * _PRIMARY_SIZE))
    secondary_size = max(8, round(ref * _SECONDARY_SIZE))
    return Geometry(
        width=width,
        height=height,
        scale_ref=round(ref),
        primary_size=primary_size,
        secondary_size=secondary_size,
        primary_y=height - round(ref * _PRIMARY_BOTTOM),
        secondary_y=height - round(ref * _SECONDARY_BOTTOM),
        margin_x=max(1, round(ref * _MARGIN_X)),
        primary_border=max(0, round(ref * _PRIMARY_BORDER)),
        secondary_border=max(0, round(ref * _SECONDARY_BORDER)),
    )


def alpha_expr(show_seconds: float, fade_seconds: float) -> str:
    """Fade in, hold, fade out, then stay hidden.

    Carried over unchanged: it reads awkwardly but it is correct, and ffmpeg's
    expression parser is unforgiving enough that rewriting it is not worth the
    risk.
    """
    s = show_seconds
    f = fade_seconds
    return (
        f"if(lt(t,{f}),t/{f},"
        f"if(lt(t,{s - f}),1,"
        f"if(lt(t,{s}),({s}-t)/{f},0)))"
    )


def logo_overlay_xy(position: str, margin: int) -> str:
    """Overlay coordinates for a corner logo."""
    corners = {
        "top-right": f"W-w-{margin}:{margin}",
        "top-left": f"{margin}:{margin}",
        "bottom-right": f"W-w-{margin}:H-h-{margin}",
        "bottom-left": f"{margin}:H-h-{margin}",
    }
    if position not in corners:
        raise ValueError(f"Unknown logo position: {position}")
    return corners[position]


def escape_filter_value(value: str) -> str:
    """Escape a value for use inside an ffmpeg filter argument.

    Needed for file paths, which may legitimately contain a colon (every path
    on Windows does) or a backslash.
    """
    return (
        value.replace("\\", "\\\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


def write_text_files(work_dir: str, basename: str, primary: str, secondary: str) -> tuple[str, str]:
    """Write caption text to sidecar files and return their paths."""
    os.makedirs(work_dir, exist_ok=True)
    primary_path = os.path.join(work_dir, f"{basename}.primary.txt")
    secondary_path = os.path.join(work_dir, f"{basename}.secondary.txt")
    # No trailing newline: drawtext would render it as an empty second line.
    with open(primary_path, "w", encoding="utf-8") as handle:
        handle.write(primary or "")
    with open(secondary_path, "w", encoding="utf-8") as handle:
        handle.write(secondary or "")
    return primary_path, secondary_path


def drawtext_chain(
    *,
    geo: Geometry,
    primary_font: str,
    secondary_font: str,
    primary_file: str,
    secondary_file: str,
    alpha: str,
    font_color: str,
    box_color: str,
    draw_box: bool = True,
    shadow: int = 0,
    has_secondary: bool = True,
) -> str:
    """Build the comma-joined ``drawtext`` pair for a lower third.

    ``shadow`` is a drop-shadow offset expressed at the 1080 baseline and scaled
    with the frame, giving legibility to box-less presets over bright footage.
    """
    box_primary = (
        f"box=1:boxcolor={box_color}:boxborderw={geo.primary_border}:" if draw_box else ""
    )
    box_secondary = (
        f"box=1:boxcolor={box_color}:boxborderw={geo.secondary_border}:" if draw_box else ""
    )

    shadow_args = ""
    if shadow > 0:
        offset = max(1, round(shadow * geo.scale_ref / REFERENCE))
        shadow_args = f"shadowcolor=black@0.8:shadowx={offset}:shadowy={offset}:"

    primary = (
        f"drawtext=fontfile={escape_filter_value(primary_font)}:"
        f"textfile={escape_filter_value(primary_file)}:"
        f"fontsize={geo.primary_size}:fontcolor={font_color}:"
        f"{box_primary}{shadow_args}"
        f"x={geo.margin_x}:y={geo.primary_y}:alpha='{alpha}'"
    )
    if not has_secondary:
        return primary

    secondary = (
        f"drawtext=fontfile={escape_filter_value(secondary_font)}:"
        f"textfile={escape_filter_value(secondary_file)}:"
        f"fontsize={geo.secondary_size}:fontcolor={font_color}:"
        f"{box_secondary}{shadow_args}"
        f"x={geo.margin_x}:y={geo.secondary_y}:alpha='{alpha}'"
    )
    return f"{primary},{secondary}"
