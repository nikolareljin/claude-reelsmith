"""Logo preparation.

SVG input is rasterised once per run. Three rasterisers are tried in order —
Inkscape, rsvg-convert, then CairoSVG — because no single one is reliably
present, and the pure-pip fallback keeps the tool working on a machine where
the user cannot install system packages.

The source file is copied into the work directory before rasterising, and
``realpath`` is applied first: a snap-confined Inkscape cannot follow a symlink
that leaves the user's home directory, which is a genuinely confusing failure
to debug from the outside.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from . import ff
from .notify import Notify

RASTER_WIDTH = 1600  # generous: the overlay is downscaled to fit the frame


class LogoError(RuntimeError):
    """Raised when a logo cannot be prepared."""


def _try_inkscape(src: str, out: str) -> bool:
    if not shutil.which("inkscape"):
        return False
    try:
        subprocess.run(  # noqa: S603
            ["inkscape", os.path.realpath(src), "--export-type=png",
             "--export-area-drawing", "-w", str(RASTER_WIDTH), "-o", out],
            capture_output=True, text=True, timeout=120, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return os.path.isfile(out)


def _try_rsvg(src: str, out: str) -> bool:
    if not shutil.which("rsvg-convert"):
        return False
    try:
        subprocess.run(  # noqa: S603
            ["rsvg-convert", "-w", str(RASTER_WIDTH), "-o", out, os.path.realpath(src)],
            capture_output=True, text=True, timeout=120, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return os.path.isfile(out)


def _try_cairosvg(src: str, out: str) -> bool:
    try:
        import cairosvg  # noqa: PLC0415 - optional dependency, imported lazily
    except ImportError:
        return False
    try:
        cairosvg.svg2png(url=os.path.realpath(src), write_to=out, output_width=RASTER_WIDTH)
    except Exception:  # noqa: BLE001 - any rasteriser failure falls through
        return False
    return os.path.isfile(out)


def rasterize_svg(src_svg: str, out_png: str) -> str:
    """Convert an SVG to PNG using whichever rasteriser is available."""
    for attempt in (_try_inkscape, _try_rsvg, _try_cairosvg):
        if attempt(src_svg, out_png):
            return out_png
    raise LogoError(
        f"Could not rasterise {src_svg}. Install one of: inkscape, rsvg-convert, "
        f"or the Python package cairosvg (pip install 'claude-reelsmith[svg]'). "
        f"Alternatively supply a PNG logo instead of an SVG."
    )


def prepare(source: str | None, work_dir: str, crop: str | None = None) -> str:
    """Return a PNG path suitable for overlay, or an empty string when unset.

    A missing logo is a warning, not an error: branding is optional and a batch
    should not fail hours in because a path was mistyped.
    """
    if not source:
        return ""

    source = os.path.expanduser(source)
    if not os.path.isfile(source):
        Notify.warn(f"Logo not found, continuing without it: {source}")
        return ""

    os.makedirs(work_dir, exist_ok=True)
    extension = os.path.splitext(source)[1].lower()

    if extension == ".svg":
        # Copy first so the user's original is never touched by a rasteriser.
        staged = os.path.join(work_dir, "logo_src.svg")
        shutil.copyfile(source, staged)
        png = rasterize_svg(staged, os.path.join(work_dir, "logo.png"))
    elif extension in (".png", ".webp", ".tif", ".tiff"):
        png = os.path.join(work_dir, "logo.png")
        shutil.copyfile(source, png)
    elif extension in (".jpg", ".jpeg"):
        # JPEG has no alpha; convert so the overlay does not paint a hard box.
        png = os.path.join(work_dir, "logo.png")
        ff.run_ffmpeg(["-i", source, "-vf", "format=rgba", png])
    else:
        raise LogoError(
            f"Unsupported logo format '{extension}'. Use SVG, PNG, WebP, TIFF or JPEG."
        )

    if crop:
        cropped = os.path.join(work_dir, "logo_cropped.png")
        ff.run_ffmpeg(["-i", png, "-vf", f"crop={crop}", cropped])
        png = cropped

    return png
