"""Preflight checks.

Every failure mode this catches was, in the predecessor tool, a raw ffmpeg
error thrown hours into a batch or on the first file. A missing font is a
one-line install command, not a filtergraph traceback — but only if something
looks for it before rendering starts.

Each failed check carries the exact command that fixes it, because the person
running this may not be the person who chose the dependencies.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass

from . import encode, ff, fonts, transcribe


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    remedy: str = ""
    required: bool = True


def _install_hint(package: str) -> str:
    if sys.platform == "darwin":
        return f"brew install {package}"
    if sys.platform.startswith("win"):
        return f"winget install {package}"
    return f"sudo apt install {package}"


def run_checks() -> list[Check]:
    """Every preflight check, in the order a user should read them."""
    checks: list[Check] = []

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    checks.append(Check(
        name="ffmpeg",
        ok=bool(ffmpeg_path),
        detail=ffmpeg_path or "not found on PATH",
        remedy=_install_hint("ffmpeg"),
    ))
    checks.append(Check(
        name="ffprobe",
        ok=bool(ffprobe_path),
        detail=ffprobe_path or "not found on PATH",
        remedy=_install_hint("ffmpeg"),
    ))

    if not ffmpeg_path:
        # Nothing further can be determined without ffmpeg.
        return checks

    caps = ff.capabilities()
    checks[0] = Check(name="ffmpeg", ok=True, detail=f"version {caps.version}")

    checks.append(Check(
        name="stabilization",
        ok=caps.can_stabilize,
        detail="libvidstab present" if caps.can_stabilize else "libvidstab missing",
        remedy="Install an ffmpeg build with libvidstab, or set video.stabilize: false",
        required=False,
    ))
    checks.append(Check(
        name="captions",
        ok=caps.can_caption,
        detail="drawtext present" if caps.can_caption else "drawtext missing",
        remedy="Install an ffmpeg built with freetype, or use look.preset: minimal",
    ))
    checks.append(Check(
        name="loudness",
        ok=caps.has_filter("loudnorm") and caps.has_filter("ebur128"),
        detail="loudnorm and ebur128 present",
        remedy="Install a full ffmpeg build",
    ))

    found_fonts = fonts.available()
    usable = {name: path for name, path in found_fonts.items() if path}
    checks.append(Check(
        name="fonts",
        ok=bool(usable),
        detail=(
            ", ".join(f"{name} → {path.split('/')[-1]}" for name, path in usable.items())
            if usable else "no usable font found"
        ),
        remedy=(
            "sudo apt install fonts-dejavu-core"
            if sys.platform.startswith("linux")
            else "install a TrueType font, or set look.font_primary to a .ttf path"
        ),
    ))

    try:
        working = encode.available()
        best = working[0].name if working else ""
        checks.append(Check(
            name="encoders",
            ok=bool(working),
            detail=(
                f"{', '.join(e.name for e in working)} (will use {best})"
                if working else "none usable"
            ),
            remedy=_install_hint("ffmpeg"),
        ))
    except Exception as exc:  # noqa: BLE001 - detection must never crash doctor
        checks.append(Check(
            name="encoders", ok=False, detail=f"detection failed: {exc}",
            remedy=_install_hint("ffmpeg"),
        ))

    checks.append(Check(
        name="transcription",
        ok=transcribe.is_available(),
        detail="faster-whisper installed" if transcribe.is_available() else "not installed",
        remedy="pip install 'claude-reelsmith[transcribe]'",
        required=False,
    ))

    svg_tool = next(
        (tool for tool in ("inkscape", "rsvg-convert") if shutil.which(tool)),
        None,
    )
    if not svg_tool:
        try:
            import cairosvg  # noqa: F401, PLC0415
            svg_tool = "cairosvg"
        except ImportError:
            svg_tool = None
    checks.append(Check(
        name="svg logos",
        ok=bool(svg_tool),
        detail=f"{svg_tool} available" if svg_tool else "no SVG rasterizer",
        remedy="pip install 'claude-reelsmith[svg]' (only needed for SVG logos)",
        required=False,
    ))

    return checks


def render_table(checks: list[Check]) -> str:
    """Format checks as an aligned table."""
    width = max((len(check.name) for check in checks), default=10)
    lines: list[str] = []
    for check in checks:
        mark = "✓" if check.ok else ("✗" if check.required else "·")
        line = f"  {mark} {check.name.ljust(width)}  {check.detail}"
        if not check.ok and check.remedy:
            line += f"\n      → {check.remedy}"
        lines.append(line)
    return "\n".join(lines)


def blocking_failures(checks: list[Check]) -> list[Check]:
    return [check for check in checks if check.required and not check.ok]
