"""End-to-end rendering against real ffmpeg.

These tests encode actual video. They are slow by unit-test standards and worth
every second: the filtergraph is the part of this package most likely to break,
and it cannot be verified by inspection.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest
from conftest import make_clip, requires_ffmpeg

from claude_reelsmith import config, encode, manifest, normalize, presets, probe
from claude_reelsmith.pipeline import Pipeline, RenderError

pytestmark = requires_ffmpeg


def build(cfg, tmp_path, target=None, output_dir=None) -> Pipeline:
    target = target or normalize.Target(320, 240, 15.0)
    return Pipeline(
        cfg=cfg,
        target=target,
        encoder=encode.BY_NAME["libx264"],
        look=presets.effective_look(cfg),
        logo_png="",
        work_dir=str(tmp_path / "_work"),
        output_dir=str(output_dir or tmp_path / "out"),
    )


def base_config(tmp_path, **overrides):
    cfg = config.load(None)
    cfg["io"]["work_dir"] = str(tmp_path / "_work")
    cfg["io"]["output_dir"] = str(tmp_path / "out")
    # Stabilisation doubles the runtime of every test for no extra coverage of
    # the parts under test; the one test that needs it turns it back on.
    cfg["video"]["stabilize"] = False
    cfg["encode"]["quality"] = 35
    cfg["encode"]["preset"] = "ultrafast"
    for section, values in overrides.items():
        cfg[section].update(values)
    return cfg


def clip_for(source, **overrides):
    fields = {"source": source, "index": 1, "title": "Test Title",
              "primary": "Test Title", "secondary": "Subtitle line"}
    fields.update(overrides)
    return manifest.ClipEntry(**fields)


class TestBasicRender:
    def test_a_clip_renders_to_a_playable_file(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4")
        pipeline = build(base_config(tmp_path), tmp_path)
        result = pipeline.render(clip_for(source))

        assert os.path.isfile(result.output)
        info = probe.probe(result.output)
        assert info.width == 320
        assert info.height == 240
        assert info.has_audio

    def test_no_partial_file_is_left_behind(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4")
        pipeline = build(base_config(tmp_path), tmp_path)
        result = pipeline.render(clip_for(source))
        assert not os.path.exists(result.output + ".part.mp4")

    def test_a_missing_source_is_reported_clearly(self, tmp_path):
        pipeline = build(base_config(tmp_path), tmp_path)
        with pytest.raises(RenderError, match="Input file not found"):
            pipeline.render(clip_for("/nonexistent/clip.mp4"))


class TestCaptions:
    def test_awkward_characters_survive_into_a_render(self, tmp_path, clip_factory):
        """The textfile= route exists precisely so this cannot break."""
        source = clip_factory("a.mp4")
        pipeline = build(base_config(tmp_path), tmp_path)
        clip = clip_for(
            source,
            primary="O'Brien, Anna: \"Sonata\" [live] 100%",
            secondary="Dvořák — Humoresque, Op. 101",
        )
        assert os.path.isfile(pipeline.render(clip).output)

    def test_the_minimal_preset_renders_without_captions(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4")
        cfg = base_config(tmp_path, look={"preset": "minimal"})
        assert os.path.isfile(build(cfg, tmp_path).render(clip_for(source)).output)

    def test_the_concert_preset_renders(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4")
        cfg = base_config(tmp_path, look={"preset": "concert"})
        assert os.path.isfile(build(cfg, tmp_path).render(clip_for(source)).output)

    def test_a_clip_with_no_caption_text_still_renders(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4")
        pipeline = build(base_config(tmp_path), tmp_path)
        clip = clip_for(source, primary="", secondary="")
        assert os.path.isfile(pipeline.render(clip).output)


class TestDifficultInput:
    def test_a_silent_clip_renders_with_a_generated_audio_track(self, tmp_path, clip_factory):
        """Mapping [0:a] on a silent clip used to fail the whole batch."""
        source = clip_factory("silent.mp4", audio=False)
        pipeline = build(base_config(tmp_path), tmp_path)
        result = pipeline.render(clip_for(source))
        assert probe.probe(result.output).has_audio

    def test_a_smaller_clip_is_padded_up_to_the_target(self, tmp_path, clip_factory):
        source = clip_factory("small.mp4", width=160, height=120)
        pipeline = build(base_config(tmp_path), tmp_path)
        info = probe.probe(pipeline.render(clip_for(source)).output)
        assert (info.width, info.height) == (320, 240)

    def test_a_portrait_clip_is_pillarboxed_not_cropped(self, tmp_path, clip_factory):
        source = clip_factory("portrait.mp4", width=240, height=320)
        pipeline = build(base_config(tmp_path), tmp_path)
        info = probe.probe(pipeline.render(clip_for(source)).output)
        assert (info.width, info.height) == (320, 240)

    def test_a_different_frame_rate_is_converted(self, tmp_path, clip_factory):
        source = clip_factory("slow.mp4", fps=10)
        pipeline = build(base_config(tmp_path), tmp_path)
        info = probe.probe(pipeline.render(clip_for(source)).output)
        assert abs(info.fps - 15.0) < 0.5


class TestMerging:
    def test_multiple_sources_concatenate_into_one_output(self, tmp_path, clip_factory):
        first = clip_factory("a.mp4", duration=2.0)
        second = clip_factory("b.mp4", duration=2.0)
        pipeline = build(base_config(tmp_path), tmp_path)
        clip = clip_for(first, merge_with=[second])
        info = probe.probe(pipeline.render(clip).output)
        assert info.duration > 3.0


class TestMetadata:
    def test_manifest_values_are_written_into_the_container(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4")
        cfg = base_config(tmp_path)
        cfg["project"]["title"] = "Spring Concert"
        cfg["project"]["date"] = "2026-06-14"
        pipeline = build(cfg, tmp_path)
        clip = clip_for(source, title="Bach — Partita", primary="Anna Petrova",
                        description="Recorded live.", tags=["concert", "live"])
        result = pipeline.render(clip)

        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_entries", "format_tags", result.output],
            capture_output=True, text=True, check=True,
        )
        tags = json.loads(proc.stdout)["format"]["tags"]
        assert tags["title"] == "Bach — Partita"
        assert tags["artist"] == "Anna Petrova"
        assert tags["album"] == "Spring Concert"
        assert tags["date"] == "2026-06-14"

    def test_metadata_can_be_switched_off(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4")
        cfg = base_config(tmp_path, marking={"embed_metadata": False})
        result = build(cfg, tmp_path).render(clip_for(source, title="Hidden"))
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_entries", "format_tags", result.output],
            capture_output=True, text=True, check=True,
        )
        tags = json.loads(proc.stdout)["format"].get("tags", {})
        assert tags.get("title") != "Hidden"


class TestLoudness:
    def test_a_quiet_clip_is_lifted_toward_the_target(self, tmp_path):
        """The point of the tool: quiet footage comes back at a usable level."""
        quiet = make_clip(tmp_path / "quiet.mp4", volume_db=-30, duration=3.0)
        cfg = base_config(tmp_path, audio={"profile": "standard", "two_pass": False})
        result = build(cfg, tmp_path).render(clip_for(quiet))

        assert measure_lufs(quiet) < -25
        assert measure_lufs(result.output) > -22

    def test_two_pass_lands_close_to_the_target(self, tmp_path):
        from claude_reelsmith import audio as audio_mod

        quiet = make_clip(tmp_path / "quiet.mp4", volume_db=-30, duration=3.0)
        cfg = base_config(tmp_path, audio={"profile": "standard", "two_pass": True})
        measured = audio_mod.measure(quiet, cfg["audio"])
        assert measured is not None, "measurement pass produced no statistics"

        result = build(cfg, tmp_path).render(
            clip_for(quiet), {"audio": {"measured": measured}}
        )
        # -14 LUFS target; short synthetic tones are noisy, so allow 3 LU.
        assert abs(measure_lufs(result.output) - (-14.0)) < 3.0


class TestPreview:
    def test_a_preview_is_shorter_than_the_source(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4", duration=4.0)
        pipeline = build(base_config(tmp_path), tmp_path)
        out = str(tmp_path / "out" / "sample.mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pipeline.render(clip_for(source), preview_seconds=1.0, output_override=out)
        assert probe.probe(out).duration < 2.0


class TestStabilization:
    def test_a_stabilized_render_produces_a_transform_file(self, tmp_path, clip_factory):
        from claude_reelsmith import ff

        if not ff.capabilities().can_stabilize:
            pytest.skip("this ffmpeg has no libvidstab")

        source = clip_factory("shaky.mp4", duration=1.5)
        cfg = base_config(tmp_path)
        cfg["video"]["stabilize"] = True
        pipeline = build(cfg, tmp_path)
        result = pipeline.render(clip_for(source))

        assert os.path.isfile(result.output)
        trf_dir = tmp_path / "_work" / "trf"
        assert list(trf_dir.glob("*.trf")), "no transform file was produced"


class TestPathConfinement:
    def test_writing_outside_the_output_directory_is_refused(self, tmp_path, clip_factory):
        source = clip_factory("a.mp4")
        cfg = base_config(tmp_path)
        cfg["io"]["output_name_template"] = "../../escaped_{index}.mp4"
        pipeline = build(cfg, tmp_path)
        with pytest.raises(RenderError, match="Refusing to write outside"):
            pipeline.output_path(clip_for(source))


def measure_lufs(path: str) -> float:
    """Integrated loudness of a rendered file, via ffmpeg's ebur128 filter."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", path,
         "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    lines = proc.stderr.splitlines()
    for index, line in enumerate(lines):
        if "Integrated loudness" in line:
            for candidate in lines[index + 1: index + 4]:
                if "I:" in candidate:
                    return float(candidate.split("I:")[1].split("LUFS")[0].strip())
    raise AssertionError(f"could not measure loudness of {path}")
