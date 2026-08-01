"""Title cards and closing cards.

A slate is rendered as its own short clip using exactly the encode settings of
the main render, then joined with the concat demuxer in copy mode. Doing it
this way keeps the main filtergraph simple — adding a slate does not perturb
stabilisation, captioning or overlay logic at all.
"""

from __future__ import annotations

import os
from typing import Any

from . import caption, ff
from .encode import Encoder
from .normalize import Target


def _drawtext(
    text: str,
    *,
    font: str,
    size: int,
    y_expr: str,
    color: str,
    text_file: str,
) -> str:
    with open(text_file, "w", encoding="utf-8") as handle:
        handle.write(text)
    return (
        f"drawtext=fontfile={caption.escape_filter_value(font)}:"
        f"textfile={caption.escape_filter_value(text_file)}:"
        f"fontsize={size}:fontcolor={color}:"
        f"x=(w-text_w)/2:y={y_expr}"
    )


def render_slate(
    *,
    out_path: str,
    work_dir: str,
    target: Target,
    encoder: Encoder,
    encode_cfg: dict[str, Any],
    seconds: float,
    primary_text: str,
    secondary_text: str = "",
    logo_png: str = "",
    background: str = "black",
    font_primary: str,
    font_secondary: str,
    font_color: str = "white",
) -> str:
    """Render one slate clip and return its path."""
    if os.path.isfile(out_path):
        return out_path

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    geo = caption.geometry(target.width, target.height)
    tag = os.path.splitext(os.path.basename(out_path))[0]

    inputs = [
        "-f", "lavfi", "-t", f"{seconds:g}",
        "-i", f"color=c={background}:s={target.width}x{target.height}:r={target.fps}",
        "-f", "lavfi", "-t", f"{seconds:g}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
    ]

    parts: list[str] = []
    label = "0:v"

    if logo_png:
        inputs += ["-i", logo_png]
        logo_height = max(2, round(target.height * 0.22))
        parts.append(f"[2:v]scale=-1:{logo_height}[lg]")
        # Logo sits above centre; the text block sits below it.
        parts.append(f"[{label}][lg]overlay=(W-w)/2:H*0.28-h/2[vlogo]")
        label = "vlogo"

    title_size = max(12, round(geo.primary_size * 1.6))
    subtitle_size = max(10, round(geo.secondary_size * 1.2))

    text_chain = _drawtext(
        primary_text,
        font=font_primary,
        size=title_size,
        y_expr="h*0.55-text_h/2",
        color=font_color,
        text_file=os.path.join(work_dir, f"{tag}.primary.txt"),
    )
    if secondary_text:
        text_chain += "," + _drawtext(
            secondary_text,
            font=font_secondary,
            size=subtitle_size,
            y_expr="h*0.66-text_h/2",
            color=font_color,
            text_file=os.path.join(work_dir, f"{tag}.secondary.txt"),
        )

    suffix = f",{encoder.filter_suffix}" if encoder.filter_suffix else ""
    parts.append(f"[{label}]{text_chain}{suffix}[vout]")
    filter_complex = ";".join(parts)

    args = [
        *encoder.init_args,
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "1:a",
        "-c:v", encoder.name,
        *encoder.output_args(encode_cfg["quality"], encode_cfg["preset"]),
        "-pix_fmt", encode_cfg["pix_fmt"],
        "-r", str(target.fps),
        "-c:a", encode_cfg["acodec"], "-b:a", encode_cfg["abitrate"], "-ar", "48000",
        "-shortest",
        out_path,
    ]
    ff.run_ffmpeg(args, timeout=600)
    return out_path


def concat_copy(parts: list[str], out_path: str, work_dir: str, tag: str) -> str:
    """Join pre-encoded parts without re-encoding.

    Every part is produced by this package with identical encoder settings, so
    stream copy is safe and effectively instant.
    """
    list_path = os.path.join(work_dir, f"{tag}.concat.txt")
    with open(list_path, "w", encoding="utf-8") as handle:
        for part in parts:
            escaped = part.replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")

    ff.run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", list_path,
        "-c", "copy", "-movflags", "+faststart", out_path,
    ], timeout=1800)
    return out_path
