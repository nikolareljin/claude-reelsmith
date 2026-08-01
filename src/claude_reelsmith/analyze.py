"""The analysis stage — facts only, no judgement.

This is deliberately the boring half of the tool. It probes each file, samples
frames, measures loudness, finds silences and optionally transcribes speech,
then writes ``analysis.json``. It decides nothing about what a clip *is*.

An agent reads that file (and looks at the sampled frames) and writes
``manifest.json``. Keeping the two stages apart is what lets the same media
pipeline serve any agent, or none.
"""

from __future__ import annotations

import glob as globmod
import json
import os
from typing import Any

from . import audio as audio_mod
from . import chapters as chapters_mod
from . import ff, normalize, probe, transcribe
from .notify import Notify

ANALYSIS_FILENAME = "analysis.json"
SCHEMA_VERSION = 1

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".m2ts",
    ".mpg", ".mpeg", ".wmv", ".flv", ".3gp",
}

# Sampled frames exist to be looked at by a model, not to be archived. 640px
# wide is legible for scene, framing and on-screen text while keeping the
# per-image token cost low.
FRAME_WIDTH = 640


def list_inputs(input_dir: str, pattern: str = "*", *, recursive: bool = False) -> list[str]:
    """Find candidate video files, sorted by name.

    Filename order is used because cameras and phones name files by capture
    time, making it the closest thing to chronological order available without
    reading every file.
    """
    input_dir = os.path.abspath(os.path.expanduser(input_dir))
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    if recursive:
        matches = globmod.glob(os.path.join(input_dir, "**", pattern), recursive=True)
    else:
        matches = globmod.glob(os.path.join(input_dir, pattern))

    files = [
        os.path.abspath(path)
        for path in matches
        if os.path.isfile(path) and os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS
    ]
    return sorted(set(files))


def extract_frames(
    source: str,
    work_dir: str,
    basename: str,
    duration: float,
    count: int = 5,
) -> list[str]:
    """Sample evenly spaced frames, avoiding the very start and end.

    The first and last few percent of a clip are usually someone walking to or
    from the camera, which tells a model nothing useful about the content.
    """
    if count <= 0 or duration <= 0:
        return []

    frames_dir = os.path.join(work_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    head, tail = duration * 0.05, duration * 0.95
    span = max(tail - head, 0.0)
    if count == 1:
        offsets = [head + span / 2]
    else:
        offsets = [head + span * i / (count - 1) for i in range(count)]

    written: list[str] = []
    for number, offset in enumerate(offsets, start=1):
        out = os.path.join(frames_dir, f"{basename}_{number:02d}.jpg")
        if not os.path.isfile(out):
            try:
                ff.run_ffmpeg([
                    "-ss", f"{offset:.3f}", "-i", source,
                    "-frames:v", "1", "-q:v", "3",
                    "-vf", f"scale={FRAME_WIDTH}:-2",
                    out,
                ], timeout=120)
            except (ff.FFmpegError, ff.FFmpegNotFound) as exc:
                reason = str(exc).splitlines()[0]
                Notify.warn(f"Could not sample a frame at {offset:.1f}s: {reason}")
                continue
        if os.path.isfile(out):
            written.append(out)
    return written


def _gain_hint(measured: dict | None, target_lufs: float) -> dict[str, Any]:
    """How far the clip sits from the target, in plain numbers."""
    if not measured or "input_i" not in measured:
        return {"measured_lufs": None, "needs_gain_db": None, "verdict": "unknown"}
    try:
        current = float(measured["input_i"])
    except (TypeError, ValueError):
        return {"measured_lufs": None, "needs_gain_db": None, "verdict": "unknown"}

    if current <= -70.0:
        return {"measured_lufs": current, "needs_gain_db": None, "verdict": "silent"}

    delta = round(target_lufs - current, 1)
    if delta > 3:
        verdict = "too quiet"
    elif delta < -3:
        verdict = "too loud"
    else:
        verdict = "close to target"
    return {"measured_lufs": round(current, 1), "needs_gain_db": delta, "verdict": verdict}


def analyze_one(
    info: probe.MediaInfo,
    cfg: dict[str, Any],
    work_dir: str,
    index: int,
) -> dict[str, Any]:
    """Gather every signal for a single clip."""
    settings = cfg["analysis"]
    basename = os.path.splitext(os.path.basename(info.path))[0]
    safe_base = "".join(char if char.isalnum() or char in "-_" else "_" for char in basename)

    entry: dict[str, Any] = {
        "index": index,
        "path": info.path,
        "name": os.path.basename(info.path),
        "media": info.to_dict(),
        "frames": [],
        "transcript": None,
        "silences": [],
        "chapters": [],
        "warnings": [],
    }

    if not info.has_audio:
        entry["warnings"].append("No audio track; silence will be substituted.")

    # Loudness. Also doubles as the measurement pass reused at render time, so
    # nothing is computed twice.
    measured = None
    if info.has_audio:
        try:
            measured = audio_mod.measure(info.path, cfg["audio"], timeout=1800)
        except Exception as exc:  # noqa: BLE001 - measurement is best-effort
            entry["warnings"].append(f"Loudness measurement failed: {exc}")
            Notify.warn(f"Loudness measurement failed for {entry['name']}: {exc}")
    profile_name = cfg["audio"]["profile"]
    target_lufs = cfg["audio"].get("target_lufs")
    if target_lufs is None and profile_name != "custom":
        target_lufs = audio_mod.resolve_profile(profile_name).target_i
    entry["audio"] = {
        "measured": measured,
        "target_lufs": target_lufs,
        **_gain_hint(measured, target_lufs if target_lufs is not None else -14.0),
    }

    if settings["frames"]:
        entry["frames"] = extract_frames(
            info.path, work_dir, safe_base, info.duration, settings["frame_count"]
        )

    if settings["detect_chapters"] and info.has_audio and info.duration > 120:
        silences = chapters_mod.detect_silences(
            info.path,
            threshold_db=settings["silence_threshold_db"],
            min_seconds=settings["silence_min_seconds"],
            timeout=1800,
        )
        entry["silences"] = [{"start": s.start, "end": s.end} for s in silences]
        found = chapters_mod.derive_chapters(info.duration, silences)
        if len(found) > 1:
            entry["chapters"] = [
                {"index": c.index, "start": c.start, "end": c.end, "title": c.title}
                for c in found
            ]

    if settings["transcribe"] and info.has_audio:
        if transcribe.is_available():
            try:
                result = transcribe.transcribe(
                    info.path,
                    model_name=settings["transcribe_model"],
                    language=settings["transcribe_language"],
                    seconds=settings["transcribe_seconds"],
                )
                entry["transcript"] = result.to_dict()
            except Exception as exc:  # noqa: BLE001 - transcription is best-effort
                entry["warnings"].append(f"Transcription failed: {exc}")
                Notify.warn(f"Transcription failed for {entry['name']}: {exc}")
        else:
            entry["warnings"].append(
                "Transcription requested but faster-whisper is not installed."
            )

    return entry


def analyze(cfg: dict[str, Any], *, paths: list[str] | None = None) -> dict[str, Any]:
    """Run analysis over the configured input directory."""
    work_dir = os.path.abspath(os.path.expanduser(cfg["io"]["work_dir"]))
    os.makedirs(work_dir, exist_ok=True)

    if paths is None:
        paths = list_inputs(
            cfg["io"]["input_dir"],
            cfg["io"]["input_glob"],
            recursive=cfg["io"]["recursive"],
        )
    if not paths:
        raise FileNotFoundError(
            f"No video files matched {cfg['io']['input_glob']} in {cfg['io']['input_dir']}."
        )

    Notify.step(f"Probing {len(paths)} file(s)")
    infos, failures = probe.probe_all(paths)
    for path, reason in failures:
        Notify.warn(f"Skipping {os.path.basename(path)}: {reason}")
    if not infos:
        raise FileNotFoundError("No readable video files were found.")

    target = normalize.choose_target(
        infos,
        target_height=cfg["video"]["target_height"],
        target_fps=cfg["video"]["target_fps"],
    )
    Notify.ok(normalize.summarize(infos, target))

    clips = []
    for index, info in enumerate(infos, start=1):
        Notify.info(f"[{index}/{len(infos)}] {os.path.basename(info.path)}")
        clips.append(analyze_one(info, cfg, work_dir, index))

    return {
        "version": SCHEMA_VERSION,
        "project": cfg["project"],
        "target": {"width": target.width, "height": target.height, "fps": target.fps},
        "settings": {
            "audio_profile": cfg["audio"]["profile"],
            "look_preset": cfg["look"]["preset"],
        },
        "clips": clips,
        "skipped": [{"path": path, "reason": reason} for path, reason in failures],
    }


def save(analysis: dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(analysis, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
