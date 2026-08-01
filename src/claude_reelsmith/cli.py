"""Command-line interface.

The subcommands map onto the stages of the workflow, and each one is usable on
its own. That matters: an agent drives them in sequence, but a person debugging
a bad render needs to re-run just the failing stage.

    doctor    is my machine able to do this at all?
    init      write a config file
    analyze   gather facts about every clip            → analysis.json
    draft     turn those facts into a starting manifest → manifest.json
    plan      show what a render would produce
    preview   render one short sample so the look can be checked
    render    do the work
    clean     discard intermediates
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import __version__, encode, ff, jobs, logo, manifest, normalize, presets, probe, state
from . import analyze as analyze_mod
from . import audio as audio_mod
from . import config as config_mod
from . import doctor as doctor_mod
from .notify import Notify
from .pipeline import Pipeline, RenderError

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PREFLIGHT = 3
EXIT_RENDER = 4


# --------------------------------------------------------------------- helpers


def _load_config(args: argparse.Namespace) -> dict[str, Any]:
    path = getattr(args, "config", None) or config_mod.find_config()
    cfg = config_mod.load(path)
    if path:
        Notify.info(f"Config: {path}")

    for attribute, (section, key) in {
        "input": ("io", "input_dir"),
        "output": ("io", "output_dir"),
        "logo": ("logo", "source"),
        "preset": ("look", "preset"),
        "audio_profile": ("audio", "profile"),
        "jobs": ("encode", "jobs"),
        "encoder": ("encode", "encoder"),
    }.items():
        value = getattr(args, attribute, None)
        if value is not None:
            cfg[section][key] = value

    if getattr(args, "no_stabilize", False):
        cfg["video"]["stabilize"] = False
    if getattr(args, "lite", False):
        cfg["analysis"]["transcribe"] = False
        cfg["analysis"]["frames"] = False

    config_mod.validate(cfg)
    return cfg


def _work_dir(cfg: dict[str, Any]) -> str:
    return os.path.abspath(os.path.expanduser(cfg["io"]["work_dir"]))


def _analysis_path(cfg: dict[str, Any]) -> str:
    return os.path.join(_work_dir(cfg), analyze_mod.ANALYSIS_FILENAME)


def _load_analysis(cfg: dict[str, Any], explicit: str | None) -> dict[str, Any] | None:
    path = explicit or _analysis_path(cfg)
    if not os.path.isfile(path):
        return None
    return analyze_mod.load(path)


def _resolve_target(cfg: dict[str, Any], man: manifest.Manifest,
                    analysis: dict[str, Any] | None) -> normalize.Target:
    """Reuse the analysed target when available, else probe the manifest."""
    if analysis and analysis.get("target"):
        raw = analysis["target"]
        return normalize.Target(
            width=int(raw["width"]), height=int(raw["height"]), fps=float(raw["fps"])
        )
    sources = [source for clip in man.included() for source in clip.sources()]
    infos, _ = probe.probe_all(sources)
    if not infos:
        raise RenderError("Could not probe any manifest source to determine a render target.")
    return normalize.choose_target(
        infos,
        target_height=cfg["video"]["target_height"],
        target_fps=cfg["video"]["target_fps"],
    )


def _analysis_index(analysis: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not analysis:
        return {}
    return {entry["path"]: entry for entry in analysis.get("clips", [])}


def _build_pipeline(cfg: dict[str, Any], target: normalize.Target,
                    output_dir: str | None = None) -> Pipeline:
    encoder = encode.select(cfg["encode"]["encoder"])
    work = _work_dir(cfg)
    look = presets.effective_look(cfg)
    logo_png = logo.prepare(cfg["logo"]["source"], work, cfg["logo"]["crop"])
    Notify.info(f"Encoder: {encoder.name} ({encoder.description})")
    return Pipeline(
        cfg=cfg,
        target=target,
        encoder=encoder,
        look=look,
        logo_png=logo_png,
        work_dir=work,
        output_dir=output_dir or os.path.abspath(os.path.expanduser(cfg["io"]["output_dir"])),
    )


def _manifest_path(cfg: dict[str, Any], explicit: str | None) -> str:
    return explicit or os.path.join(_work_dir(cfg), manifest.MANIFEST_FILENAME)


# -------------------------------------------------------------------- commands


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = doctor_mod.run_checks()
    if args.json:
        print(json.dumps(
            [{"name": c.name, "ok": c.ok, "detail": c.detail,
              "remedy": c.remedy, "required": c.required} for c in checks],
            indent=2,
        ))
    else:
        Notify.step("Environment")
        Notify.plain(doctor_mod.render_table(checks))
        Notify.plain("")

    blocking = doctor_mod.blocking_failures(checks)
    if blocking:
        Notify.error(f"{len(blocking)} required check(s) failed.")
        return EXIT_PREFLIGHT
    Notify.ok("Ready to render.")
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    target_path = args.config or config_mod.CONFIG_FILENAME
    if os.path.exists(target_path) and not args.force:
        Notify.error(f"{target_path} already exists. Pass --force to overwrite it.")
        return EXIT_USAGE

    cfg = config_mod.load(None)
    for attribute, (section, key) in {
        "input": ("io", "input_dir"),
        "output": ("io", "output_dir"),
        "logo": ("logo", "source"),
        "preset": ("look", "preset"),
        "audio_profile": ("audio", "profile"),
        "title": ("project", "title"),
        "date": ("project", "date"),
    }.items():
        value = getattr(args, attribute, None)
        if value is not None:
            cfg[section][key] = value
    config_mod.validate(cfg)

    with open(target_path, "w", encoding="utf-8") as handle:
        handle.write("# reelsmith configuration\n")
        handle.write("# Every value below is a default you can change or delete.\n")
        handle.write("# Docs: https://github.com/nikolareljin/claude-reelsmith/tree/main/docs\n\n")
        handle.write(config_mod.dump(cfg))

    Notify.ok(f"Wrote {target_path}")
    return EXIT_OK


def cmd_analyze(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    result = analyze_mod.analyze(cfg)
    out = args.output_file or _analysis_path(cfg)
    analyze_mod.save(result, out)
    Notify.ok(f"Analysis written to {out}")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return EXIT_OK


def cmd_draft(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    analysis = _load_analysis(cfg, args.analysis)
    if analysis is None:
        Notify.error("No analysis found. Run 'reelsmith analyze' first.")
        return EXIT_USAGE

    draft = manifest.draft_from_analysis(analysis)
    out = _manifest_path(cfg, args.manifest)
    if os.path.exists(out) and not args.force:
        Notify.error(f"{out} already exists. Pass --force to overwrite it.")
        return EXIT_USAGE
    manifest.save(draft, out)
    Notify.ok(f"Draft manifest written to {out}")
    Notify.info("Edit the titles and captions, then run 'reelsmith plan'.")
    return EXIT_OK


def _plan_rows(cfg: dict[str, Any], man: manifest.Manifest,
               analysis: dict[str, Any] | None, pipeline: Pipeline,
               tracker: state.State, target: normalize.Target) -> list[dict[str, Any]]:
    index = _analysis_index(analysis)
    rows: list[dict[str, Any]] = []
    for clip in man.included():
        entry = index.get(clip.source, {})
        audio_info = entry.get("audio", {})
        media = entry.get("media", {})
        out = pipeline.output_path(clip)
        digest = state.fingerprint(cfg, clip, target)

        fixes = []
        gain = audio_info.get("needs_gain_db")
        if gain is not None and abs(gain) >= 1:
            fixes.append(f"{gain:+.1f} dB")
        if cfg["video"]["stabilize"] and pipeline.can_stabilize:
            fixes.append("stabilize")
        if media and (media.get("display_width"), media.get("display_height")) != (
            target.width, target.height
        ):
            fixes.append("rescale")
        if media and not media.get("has_audio", True):
            fixes.append("silent track")

        rows.append({
            "index": clip.index,
            "source": os.path.basename(clip.source),
            "title": clip.title,
            "primary": clip.primary,
            "secondary": clip.secondary,
            "output": os.path.basename(out),
            "duration": media.get("duration"),
            "fixes": fixes,
            "current": tracker.is_current(out, digest),
        })
    return rows


def _format_duration(seconds: float) -> str:
    """Human duration that stays honest about short batches."""
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _print_plan(rows: list[dict[str, Any]], target: normalize.Target) -> None:
    Notify.step(f"Render plan — {len(rows)} clip(s) onto {target}")
    if not rows:
        Notify.warn("Nothing to render: every manifest entry has include=false.")
        return

    width_source = max(len(str(row["source"])) for row in rows)
    width_title = max(len(str(row["title"])) for row in rows)
    total = 0.0
    for row in rows:
        duration = row["duration"] or 0.0
        total += duration
        stamp = f"{int(duration // 60):d}:{int(duration % 60):02d}" if duration else "  ?  "
        marker = "·" if row["current"] else " "
        fixes = ", ".join(row["fixes"]) or "—"
        Notify.plain(
            f"  {marker} {row['index']:>3}  {str(row['source']).ljust(width_source)}  "
            f"{str(row['title']).ljust(width_title)}  {stamp:>6}  {fixes}"
        )
    Notify.plain("")
    Notify.info(f"Total source runtime: {_format_duration(total)}")
    if any(row["current"] for row in rows):
        Notify.info("Rows marked · are already up to date and will be skipped.")


def cmd_plan(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    man = manifest.load(_manifest_path(cfg, args.manifest))
    analysis = _load_analysis(cfg, args.analysis)
    target = _resolve_target(cfg, man, analysis)
    pipeline = _build_pipeline(cfg, target)
    tracker = state.State(os.path.join(_work_dir(cfg), state.STATE_FILENAME))

    rows = _plan_rows(cfg, man, analysis, pipeline, tracker, target)
    if args.json:
        print(json.dumps({"target": str(target), "clips": rows}, indent=2, ensure_ascii=False))
    else:
        _print_plan(rows, target)
    return EXIT_OK


def cmd_preview(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    man = manifest.load(_manifest_path(cfg, args.manifest))
    analysis = _load_analysis(cfg, args.analysis)
    target = _resolve_target(cfg, man, analysis)

    included = man.included()
    if not included:
        Notify.error("Nothing to preview: every manifest entry has include=false.")
        return EXIT_USAGE

    clip = next((c for c in included if c.index == args.clip), included[0]) if args.clip \
        else included[0]

    preview_dir = os.path.join(
        os.path.abspath(os.path.expanduser(cfg["io"]["output_dir"])), "_preview"
    )
    os.makedirs(preview_dir, exist_ok=True)
    pipeline = _build_pipeline(cfg, target, output_dir=preview_dir)

    out = os.path.join(preview_dir, f"sample_{clip.index:02d}.mp4")
    Notify.step(f"Rendering a {args.seconds:g}s sample of {os.path.basename(clip.source)}")
    try:
        pipeline.render(
            clip,
            _analysis_index(analysis).get(clip.source),
            preview_seconds=args.seconds,
            preview_start=args.start,
            output_override=out,
        )
    except (RenderError, ff.FFmpegError) as exc:
        Notify.error(str(exc))
        return EXIT_RENDER

    Notify.ok(f"Sample written to {out}")
    Notify.info(
        "Check the logo position, caption text and audio level, "
        "then run 'reelsmith render'."
    )
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    man = manifest.load(_manifest_path(cfg, args.manifest))
    analysis = _load_analysis(cfg, args.analysis)
    target = _resolve_target(cfg, man, analysis)
    pipeline = _build_pipeline(cfg, target)
    index = _analysis_index(analysis)

    tracker = state.State(os.path.join(_work_dir(cfg), state.STATE_FILENAME))
    clips = man.included()

    if args.only:
        wanted = {int(part) for part in args.only.split(",") if part.strip()}
        clips = [clip for clip in clips if clip.index in wanted]
        if not clips:
            Notify.error(f"No manifest entries matched --only {args.only}")
            return EXIT_USAGE

    if not clips:
        Notify.error("Nothing to render.")
        return EXIT_USAGE

    digests = {clip.source: state.fingerprint(cfg, clip, target) for clip in clips}

    def should_skip(clip: manifest.ClipEntry) -> bool:
        if args.force:
            return False
        return tracker.is_current(pipeline.output_path(clip), digests[clip.source])

    def work(clip: manifest.ClipEntry):
        return pipeline.render(clip, index.get(clip.source))

    worker_count = config_mod.resolve_jobs(cfg)
    Notify.step(f"Rendering {len(clips)} clip(s) with {worker_count} worker(s)")

    report = jobs.run_batch(
        clips,
        work,
        label=lambda clip: os.path.basename(pipeline.output_path(clip)),
        jobs=worker_count,
        is_skip=should_skip,
    )

    for outcome in report.succeeded:
        tracker.record(pipeline.output_path(outcome.item), digests[outcome.item.source])
    tracker.save()

    _write_side_artifacts(cfg, man, analysis, pipeline)

    Notify.plain("")
    if report.failed:
        Notify.error(f"Done with errors — {report.summary()}")
        return EXIT_RENDER
    Notify.ok(f"Done — {report.summary()}")
    Notify.info(f"Output: {pipeline.output_dir}")
    return EXIT_OK


def _write_side_artifacts(cfg: dict[str, Any], man: manifest.Manifest,
                          analysis: dict[str, Any] | None, pipeline: Pipeline) -> None:
    """Write the metadata sidecar and any chapter files."""
    payload = {
        "project": cfg["project"],
        "clips": [
            {
                "output": os.path.basename(pipeline.output_path(clip)),
                "title": clip.title,
                "primary": clip.primary,
                "secondary": clip.secondary,
                "description": clip.description,
                "tags": clip.tags,
                "sources": [os.path.basename(source) for source in clip.sources()],
            }
            for clip in man.included()
        ],
    }
    out = os.path.join(pipeline.output_dir, "metadata.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    if not (cfg["marking"]["chapters_file"] and analysis):
        return

    from . import chapters as chapters_mod

    for entry in analysis.get("clips", []):
        raw = entry.get("chapters") or []
        if len(raw) < 2:
            continue
        found = [
            chapters_mod.Chapter(
                index=item["index"], start=item["start"],
                end=item["end"], title=item["title"],
            )
            for item in raw
        ]
        clip = next((c for c in man.included() if c.source == entry["path"]), None)
        if clip is None:
            continue
        stem = os.path.splitext(os.path.basename(pipeline.output_path(clip)))[0]
        with open(os.path.join(pipeline.output_dir, f"{stem}.chapters.txt"),
                  "w", encoding="utf-8") as handle:
            handle.write(chapters_mod.to_plain_text(found))


def cmd_clean(args: argparse.Namespace) -> int:
    import shutil

    cfg = _load_config(args)
    work = _work_dir(cfg)
    if not os.path.isdir(work):
        Notify.info("Nothing to clean.")
        return EXIT_OK

    if args.all:
        shutil.rmtree(work)
        Notify.ok(f"Removed {work}")
        return EXIT_OK

    # Keep analysis.json and manifest.json: they are expensive to regenerate
    # and carry the agent's work. Only intermediates go.
    removed = 0
    for name in ("trf", "frames"):
        path = os.path.join(work, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
            removed += 1
    for entry in os.listdir(work):
        if entry.endswith((".part.mp4", "_merged.mp4", ".concat.txt", ".txt")):
            os.unlink(os.path.join(work, entry))
            removed += 1
    Notify.ok(f"Removed {removed} intermediate item(s) from {work}")
    Notify.info("analysis.json and manifest.json were kept. Use --all to remove everything.")
    return EXIT_OK


def cmd_profiles(args: argparse.Namespace) -> int:
    payload = {
        "audio": [
            {"name": name, "description": description, "target_lufs": lufs}
            for name, description, lufs in audio_mod.describe()
        ],
        "looks": [
            {"name": name, "description": description}
            for name, description in presets.describe()
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    Notify.step("Look presets")
    for item in payload["looks"]:
        Notify.plain(f"  {item['name']:<10} {item['description']}")
    Notify.step("Audio profiles")
    for item in payload["audio"]:
        Notify.plain(f"  {item['name']:<10} {item['target_lufs']:>6} LUFS  {item['description']}")
    return EXIT_OK


# ---------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reelsmith",
        description=(
            "Batch-finish a folder of video: enhance audio, stabilize, brand, and caption."
        ),
    )
    parser.add_argument("--version", action="version", version=f"reelsmith {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("-c", "--config", help=f"path to {config_mod.CONFIG_FILENAME}")
        sub.add_argument("--input", help="override io.input_dir")
        sub.add_argument("--output", help="override io.output_dir")
        sub.add_argument("--logo", help="override logo.source")
        sub.add_argument("--preset", help="override look.preset")
        sub.add_argument("--audio-profile", dest="audio_profile", help="override audio.profile")
        sub.add_argument("--encoder", help="override encode.encoder")
        sub.add_argument("--jobs", type=int, help="override encode.jobs")
        sub.add_argument("--no-stabilize", action="store_true", help="disable stabilization")

    doctor_parser = subparsers.add_parser("doctor", help="check this machine can render")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=cmd_doctor)

    init_parser = subparsers.add_parser("init", help="write a reelsmith.yaml")
    init_parser.add_argument("-c", "--config", help="path to write")
    init_parser.add_argument("--input")
    init_parser.add_argument("--output")
    init_parser.add_argument("--logo")
    init_parser.add_argument("--preset")
    init_parser.add_argument("--audio-profile", dest="audio_profile")
    init_parser.add_argument("--title", help="project.title")
    init_parser.add_argument("--date", help="project.date")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=cmd_init)

    analyze_parser = subparsers.add_parser("analyze", help="gather facts about every clip")
    add_common(analyze_parser)
    analyze_parser.add_argument(
        "--lite", action="store_true",
        help="filenames and metadata only: no transcription, no frame sampling",
    )
    analyze_parser.add_argument("-o", "--output-file", dest="output_file")
    analyze_parser.add_argument("--json", action="store_true")
    analyze_parser.set_defaults(func=cmd_analyze)

    draft_parser = subparsers.add_parser("draft", help="write a starting manifest from filenames")
    add_common(draft_parser)
    draft_parser.add_argument("--analysis")
    draft_parser.add_argument("--manifest")
    draft_parser.add_argument("--force", action="store_true")
    draft_parser.set_defaults(func=cmd_draft)

    plan_parser = subparsers.add_parser("plan", help="show what a render would produce")
    add_common(plan_parser)
    plan_parser.add_argument("--analysis")
    plan_parser.add_argument("--manifest")
    plan_parser.add_argument("--json", action="store_true")
    plan_parser.set_defaults(func=cmd_plan)

    preview_parser = subparsers.add_parser("preview", help="render one short sample")
    add_common(preview_parser)
    preview_parser.add_argument("--analysis")
    preview_parser.add_argument("--manifest")
    preview_parser.add_argument("--clip", type=int, help="manifest index to sample")
    preview_parser.add_argument("--seconds", type=float, default=20.0)
    preview_parser.add_argument("--start", type=float, default=0.0)
    preview_parser.set_defaults(func=cmd_preview)

    render_parser = subparsers.add_parser("render", help="render the batch")
    add_common(render_parser)
    render_parser.add_argument("--analysis")
    render_parser.add_argument("--manifest")
    render_parser.add_argument("--only", help="comma-separated manifest indices")
    render_parser.add_argument("--force", action="store_true", help="re-render up-to-date clips")
    render_parser.set_defaults(func=cmd_render)

    clean_parser = subparsers.add_parser("clean", help="remove intermediates")
    clean_parser.add_argument("-c", "--config")
    clean_parser.add_argument("--all", action="store_true",
                              help="also remove analysis.json and manifest.json")
    clean_parser.set_defaults(func=cmd_clean)

    profiles_parser = subparsers.add_parser("profiles", help="list looks and audio profiles")
    profiles_parser.add_argument("--json", action="store_true")
    profiles_parser.set_defaults(func=cmd_profiles)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    Notify.quiet = getattr(args, "quiet", False)

    try:
        return args.func(args)
    except KeyboardInterrupt:
        Notify.error("Interrupted.")
        return 130
    except (config_mod.ConfigError, manifest.ManifestError) as exc:
        Notify.error(str(exc))
        return EXIT_USAGE
    except (ff.FFmpegNotFound, FileNotFoundError) as exc:
        Notify.error(str(exc))
        return EXIT_PREFLIGHT
    except (RenderError, ff.FFmpegError, probe.ProbeError, logo.LogoError) as exc:
        Notify.error(str(exc))
        return EXIT_RENDER
    except ValueError as exc:
        Notify.error(str(exc))
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
