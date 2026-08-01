"""The render pipeline.

Filter order matters and is not arbitrary:

1. **Stabilise first.** ``vidstabtransform`` must see the same geometry that
   ``vidstabdetect`` measured, so it runs before any scaling.
2. **Then normalise** onto the common canvas.
3. **Then brand and caption**, so overlay and text geometry are computed
   against the final frame size.
4. **Encoder-specific upload last**, because a hardware surface cannot be drawn
   on by software filters.

Output is written to a ``.part.mp4`` and moved into place with ``os.replace``,
so an interrupted run never leaves a half-written file that a later run would
mistake for finished work.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Any

from . import audio as audio_mod
from . import caption, ff, fonts, normalize, probe, transcribe
from .encode import Encoder
from .manifest import ClipEntry, output_name
from .normalize import Target
from .notify import Notify


class RenderError(RuntimeError):
    """Raised when a clip cannot be rendered."""


@dataclass
class RenderResult:
    clip: ClipEntry
    output: str
    skipped: bool = False
    subtitle: str | None = None
    warnings: list[str] = field(default_factory=list)


def _confine(path: str, root: str) -> str:
    """Refuse to write outside the configured output directory."""
    resolved = os.path.realpath(path)
    root_resolved = os.path.realpath(root)
    if not (resolved == root_resolved or resolved.startswith(root_resolved + os.sep)):
        raise RenderError(
            f"Refusing to write outside the output directory.\n"
            f"  output_dir: {root_resolved}\n"
            f"  attempted:  {resolved}"
        )
    return resolved


class Pipeline:
    """Renders manifest entries into finished files."""

    def __init__(
        self,
        *,
        cfg: dict[str, Any],
        target: Target,
        encoder: Encoder,
        look: dict[str, Any],
        logo_png: str,
        work_dir: str,
        output_dir: str,
    ) -> None:
        self.cfg = cfg
        self.target = target
        self.encoder = encoder
        self.look = look
        self.logo_png = logo_png
        self.work_dir = os.path.abspath(work_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.geo = caption.geometry(target.width, target.height, scale=look["caption_scale"])

        os.makedirs(self.work_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        self.font_primary = fonts.resolve(look["primary_font"]) if look["captions"] else ""
        self.font_secondary = fonts.resolve(look["secondary_font"]) if look["captions"] else ""

        caps = ff.capabilities()
        self.can_stabilize = caps.can_stabilize
        if cfg["video"]["stabilize"] and not self.can_stabilize:
            Notify.warn(
                "This ffmpeg build has no libvidstab; stabilization is disabled for this run."
            )
        if look["captions"] and not caps.can_caption:
            raise RenderError(
                "This ffmpeg build has no drawtext filter, so captions cannot be rendered. "
                "Install an ffmpeg built with freetype, or set look.preset to 'minimal'."
            )

    # ------------------------------------------------------------------ paths

    def output_path(self, clip: ClipEntry) -> str:
        name = output_name(clip, self.cfg["io"]["output_name_template"])
        return _confine(os.path.join(self.output_dir, name), self.output_dir)

    def _tag(self, clip: ClipEntry) -> str:
        stem = os.path.splitext(os.path.basename(clip.source))[0]
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
        return f"{clip.index:03d}_{safe}"

    # ------------------------------------------------------------- sub-stages

    def _concat_sources(self, clip: ClipEntry, tag: str) -> str:
        """Join a multi-source clip into one intermediate.

        Unlike the predecessor, this honours the configured encode settings
        rather than hardcoding its own, so the intermediate cannot become the
        quality bottleneck.
        """
        merged = os.path.join(self.work_dir, f"{tag}_merged.mp4")
        if os.path.isfile(merged):
            return merged

        sources = clip.sources()
        inputs: list[str] = []
        graph = ""
        for position, source in enumerate(sources):
            inputs += ["-i", source]
            graph += f"[{position}:v][{position}:a]"
        graph += f"concat=n={len(sources)}:v=1:a=1[v][a]"

        encode_cfg = self.cfg["encode"]
        partial = merged + ".part.mp4"
        ff.run_ffmpeg([
            *inputs,
            "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", str(max(1, encode_cfg["quality"] - 2)),
            "-preset", "veryfast", "-pix_fmt", encode_cfg["pix_fmt"],
            "-c:a", encode_cfg["acodec"], "-b:a", encode_cfg["abitrate"],
            partial,
        ], timeout=7200)
        os.replace(partial, merged)
        return merged

    def _detect_stabilization(self, source: str, tag: str) -> str:
        """First stabilisation pass. The transform file is reused if present."""
        trf_dir = os.path.join(self.work_dir, "trf")
        os.makedirs(trf_dir, exist_ok=True)
        trf = os.path.join(trf_dir, f"{tag}.trf")
        if os.path.isfile(trf) and os.path.getsize(trf) > 0:
            return trf

        video_cfg = self.cfg["video"]
        ff.run_ffmpeg([
            "-i", source,
            "-vf", (
                f"vidstabdetect=shakiness={video_cfg['shakiness']}"
                f":accuracy={video_cfg['accuracy']}"
                f":result={caption.escape_filter_value(trf)}"
            ),
            "-f", "null", "-",
        ], timeout=7200)
        return trf

    # ------------------------------------------------------------ filtergraph

    def _video_chain(self, info: probe.MediaInfo, clip: ClipEntry, tag: str, trf: str | None,
                     logo_index: int | None, subtitle_path: str | None) -> tuple[str, str]:
        """Build the video half of the filtergraph.

        Returns the graph fragment and the label carrying the finished video.
        """
        parts: list[str] = []
        label = "0:v"

        stage: list[str] = []
        if trf:
            video_cfg = self.cfg["video"]
            stage.append(
                f"vidstabtransform=input={caption.escape_filter_value(trf)}"
                f":smoothing={video_cfg['smoothing']}:zoom={video_cfg['zoom']}"
            )
            stage.append(f"unsharp={video_cfg['unsharp']}")

        scaling = normalize.video_filter(info, self.target)
        if scaling:
            stage.append(scaling)

        if subtitle_path and self.cfg["subtitles"]["burn_in"]:
            stage.append(f"subtitles={caption.escape_filter_value(subtitle_path)}")

        if stage:
            parts.append(f"[{label}]{','.join(stage)}[vbase]")
            label = "vbase"

        if logo_index is not None:
            logo_height = max(2, round(self.target.height * self.cfg["logo"]["height_fraction"]))
            margin = max(0, round(self.target.height * self.cfg["logo"]["margin_fraction"]))
            opacity = self.cfg["logo"]["opacity"]
            logo_stage = f"scale=-1:{logo_height}"
            if opacity < 1.0:
                logo_stage += f",format=rgba,colorchannelmixer=aa={opacity}"
            parts.append(f"[{logo_index}:v]{logo_stage}[lg]")
            xy = caption.logo_overlay_xy(self.cfg["logo"]["position"], margin)
            parts.append(f"[{label}][lg]overlay={xy}[vlogo]")
            label = "vlogo"

        if self.look["captions"] and (clip.primary or clip.secondary):
            primary_file, secondary_file = caption.write_text_files(
                self.work_dir, tag, clip.primary, clip.secondary
            )
            alpha = caption.alpha_expr(self.look["show_seconds"], self.look["fade_seconds"])
            chain = caption.drawtext_chain(
                geo=self.geo,
                primary_font=self.font_primary,
                secondary_font=self.font_secondary,
                primary_file=primary_file,
                secondary_file=secondary_file,
                alpha=alpha,
                font_color=self.look["font_color"],
                box_color=self.look["box_color"],
                draw_box=self.look["draw_box"],
                shadow=self.look["shadow"],
                has_secondary=bool(clip.secondary),
            )
            parts.append(f"[{label}]{chain}[vcap]")
            label = "vcap"

        if self.encoder.filter_suffix:
            parts.append(f"[{label}]{self.encoder.filter_suffix}[vhw]")
            label = "vhw"

        return ";".join(parts), label

    # ---------------------------------------------------------------- metadata

    def _metadata_args(self, clip: ClipEntry) -> list[str]:
        if not self.cfg["marking"]["embed_metadata"]:
            return []
        project = self.cfg["project"]
        args: list[str] = []
        if clip.title:
            args += ["-metadata", f"title={clip.title}"]
        if clip.primary:
            args += ["-metadata", f"artist={clip.primary}"]
        if clip.description:
            args += ["-metadata", f"comment={clip.description}"]
        if project.get("date"):
            args += ["-metadata", f"date={project['date']}"]
        if project.get("title"):
            args += ["-metadata", f"album={project['title']}"]
        if clip.tags:
            args += ["-metadata", f"genre={', '.join(clip.tags)}"]
        return args

    # ------------------------------------------------------------------ render

    def render(
        self,
        clip: ClipEntry,
        analysis_entry: dict[str, Any] | None = None,
        *,
        preview_seconds: float = 0.0,
        preview_start: float = 0.0,
        output_override: str | None = None,
    ) -> RenderResult:
        """Render one manifest entry."""
        tag = self._tag(clip)
        out = output_override or self.output_path(clip)
        result = RenderResult(clip=clip, output=out)

        sources = clip.sources()
        for source in sources:
            if not os.path.isfile(source):
                raise RenderError(f"Input file not found: {source}")

        source = self._concat_sources(clip, tag) if len(sources) > 1 else sources[0]
        info = probe.probe(source)

        trf = None
        if self.cfg["video"]["stabilize"] and self.can_stabilize and not preview_seconds:
            trf = self._detect_stabilization(source, tag)

        subtitle_path = self._write_subtitles(clip, analysis_entry, out)
        result.subtitle = subtitle_path

        # Input ordering: video, then a silent track when the source has none,
        # then the logo. Indices are tracked as inputs are appended.
        inputs: list[str] = []
        if preview_seconds:
            inputs += ["-ss", f"{preview_start:g}", "-t", f"{preview_seconds:g}"]
        inputs += ["-i", source]
        next_index = 1

        if info.has_audio:
            audio_label = "0:a"
        else:
            duration = preview_seconds or max(info.duration, 0.1)
            inputs += ["-f", "lavfi", "-t", f"{duration:.3f}",
                       "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
            audio_label = f"{next_index}:a"
            next_index += 1

        logo_index = None
        if self.logo_png:
            inputs += ["-i", self.logo_png]
            logo_index = next_index
            next_index += 1

        video_graph, video_label = self._video_chain(
            info, clip, tag, trf, logo_index, subtitle_path
        )

        measured = (analysis_entry or {}).get("audio", {}).get("measured")
        audio_chain = audio_mod.render_chain(self.cfg["audio"], measured)
        audio_graph = f"[{audio_label}]{audio_chain}[aout]"

        filter_complex = f"{video_graph};{audio_graph}" if video_graph else audio_graph
        video_map = f"[{video_label}]" if video_graph else "0:v"

        encode_cfg = self.cfg["encode"]
        args = [
            *self.encoder.init_args,
            *inputs,
            "-filter_complex", filter_complex,
            "-map", video_map, "-map", "[aout]",
            "-c:v", self.encoder.name,
            *self.encoder.output_args(encode_cfg["quality"], encode_cfg["preset"]),
            "-pix_fmt", encode_cfg["pix_fmt"],
            "-c:a", encode_cfg["acodec"], "-b:a", encode_cfg["abitrate"],
            *self._metadata_args(clip),
        ]
        if encode_cfg["faststart"]:
            args += ["-movflags", "+faststart"]

        partial = out + ".part.mp4"
        args.append(partial)

        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        try:
            ff.run_ffmpeg(args, timeout=None)
        except ff.FFmpegError:
            if os.path.isfile(partial):
                os.unlink(partial)
            raise

        os.replace(partial, out)
        return result

    def _write_subtitles(
        self,
        clip: ClipEntry,
        analysis_entry: dict[str, Any] | None,
        out: str,
    ) -> str | None:
        """Write the ``.srt`` sidecar from the analysis transcript."""
        if not analysis_entry:
            return None
        wants_sidecar = self.cfg["subtitles"]["sidecar"]
        wants_burn = self.cfg["subtitles"]["burn_in"]
        if not (wants_sidecar or wants_burn):
            return None

        raw = analysis_entry.get("transcript")
        if not raw or not raw.get("segments"):
            return None

        script = transcribe.Transcript(
            language=raw.get("language", ""),
            text=raw.get("text", ""),
            segments=[
                transcribe.Segment(
                    start=float(s["start"]), end=float(s["end"]), text=s["text"]
                )
                for s in raw["segments"]
            ],
        )

        # The sidecar lives beside the output; burn-in reads the same file.
        sidecar = os.path.splitext(out)[0] + ".srt"
        _confine(sidecar, self.output_dir)
        written = transcribe.write_srt(script, sidecar)
        if written and not wants_sidecar:
            # Only needed transiently for burn-in; move it out of the output dir.
            staged = os.path.join(self.work_dir, os.path.basename(sidecar))
            shutil.move(written, staged)
            return staged
        return written
