"""Render-state fingerprinting.

The behaviour under test is the fix for a real footgun in the tool this package
replaces: it treated an existing output file as proof the work was done, so
changing the config and re-running silently kept the old renders.
"""

from __future__ import annotations

import copy

from claude_reelsmith import config, manifest, state
from claude_reelsmith.normalize import Target

TARGET = Target(1920, 1080, 30.0)


def make_clip(tmp_path, **overrides):
    source = tmp_path / "a.mp4"
    source.write_bytes(b"pretend video")
    fields = {"source": str(source), "index": 1, "title": "Bach"}
    fields.update(overrides)
    return manifest.ClipEntry(**fields)


def test_identical_inputs_produce_an_identical_fingerprint(tmp_path):
    cfg = config.load(None)
    clip = make_clip(tmp_path)
    assert state.fingerprint(cfg, clip, TARGET) == state.fingerprint(cfg, clip, TARGET)


class TestInvalidation:
    def test_changing_the_audio_profile_invalidates(self, tmp_path):
        cfg = config.load(None)
        clip = make_clip(tmp_path)
        before = state.fingerprint(cfg, clip, TARGET)
        changed = copy.deepcopy(cfg)
        changed["audio"]["profile"] = "speech"
        assert state.fingerprint(changed, clip, TARGET) != before

    def test_changing_the_look_preset_invalidates(self, tmp_path):
        cfg = config.load(None)
        clip = make_clip(tmp_path)
        before = state.fingerprint(cfg, clip, TARGET)
        changed = copy.deepcopy(cfg)
        changed["look"]["preset"] = "concert"
        assert state.fingerprint(changed, clip, TARGET) != before

    def test_changing_the_logo_invalidates(self, tmp_path):
        cfg = config.load(None)
        clip = make_clip(tmp_path)
        before = state.fingerprint(cfg, clip, TARGET)
        changed = copy.deepcopy(cfg)
        changed["logo"]["position"] = "bottom-left"
        assert state.fingerprint(changed, clip, TARGET) != before

    def test_editing_the_caption_text_invalidates(self, tmp_path):
        cfg = config.load(None)
        before = state.fingerprint(cfg, make_clip(tmp_path), TARGET)
        after = state.fingerprint(cfg, make_clip(tmp_path, primary="New chyron"), TARGET)
        assert after != before

    def test_replacing_the_source_file_invalidates(self, tmp_path):
        cfg = config.load(None)
        clip = make_clip(tmp_path)
        before = state.fingerprint(cfg, clip, TARGET)
        (tmp_path / "a.mp4").write_bytes(b"different content, different size")
        assert state.fingerprint(cfg, clip, TARGET) != before

    def test_a_different_render_target_invalidates(self, tmp_path):
        cfg = config.load(None)
        clip = make_clip(tmp_path)
        before = state.fingerprint(cfg, clip, TARGET)
        assert state.fingerprint(cfg, clip, Target(3840, 2160, 30.0)) != before


class TestNonInvalidation:
    """Things that must NOT throw away hours of finished encoding."""

    def test_changing_the_worker_count_does_not_invalidate(self, tmp_path):
        cfg = config.load(None)
        clip = make_clip(tmp_path)
        before = state.fingerprint(cfg, clip, TARGET)
        changed = copy.deepcopy(cfg)
        changed["encode"]["jobs"] = 8
        assert state.fingerprint(changed, clip, TARGET) == before

    def test_changing_the_output_directory_does_not_invalidate(self, tmp_path):
        cfg = config.load(None)
        clip = make_clip(tmp_path)
        before = state.fingerprint(cfg, clip, TARGET)
        changed = copy.deepcopy(cfg)
        changed["io"]["output_dir"] = "/somewhere/else"
        assert state.fingerprint(changed, clip, TARGET) == before

    def test_changing_project_metadata_does_not_invalidate(self, tmp_path):
        cfg = config.load(None)
        clip = make_clip(tmp_path)
        before = state.fingerprint(cfg, clip, TARGET)
        changed = copy.deepcopy(cfg)
        changed["project"]["location"] = "Elsewhere"
        assert state.fingerprint(changed, clip, TARGET) == before


class TestPersistence:
    def test_a_recorded_render_is_reported_current(self, tmp_path):
        output = tmp_path / "01_bach.mp4"
        output.write_bytes(b"rendered")
        tracker = state.State(str(tmp_path / "state.json"))
        tracker.record(str(output), "abc123")
        assert tracker.is_current(str(output), "abc123")

    def test_a_different_fingerprint_is_not_current(self, tmp_path):
        output = tmp_path / "01_bach.mp4"
        output.write_bytes(b"rendered")
        tracker = state.State(str(tmp_path / "state.json"))
        tracker.record(str(output), "abc123")
        assert not tracker.is_current(str(output), "different")

    def test_a_deleted_output_is_not_current_even_if_recorded(self, tmp_path):
        tracker = state.State(str(tmp_path / "state.json"))
        tracker.record(str(tmp_path / "gone.mp4"), "abc123")
        assert not tracker.is_current(str(tmp_path / "gone.mp4"), "abc123")

    def test_state_survives_a_save_and_reload(self, tmp_path):
        output = tmp_path / "01.mp4"
        output.write_bytes(b"x")
        path = str(tmp_path / "state.json")
        first = state.State(path)
        first.record(str(output), "digest")
        first.save()
        assert state.State(path).is_current(str(output), "digest")

    def test_a_corrupt_state_file_does_not_block_rendering(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("{ this is not json", encoding="utf-8")
        tracker = state.State(str(path))
        assert not tracker.is_current(str(tmp_path / "any.mp4"), "digest")

    def test_forget_drops_a_recorded_entry(self, tmp_path):
        output = tmp_path / "01.mp4"
        output.write_bytes(b"x")
        tracker = state.State(str(tmp_path / "state.json"))
        tracker.record(str(output), "digest")
        tracker.forget(str(output))
        assert not tracker.is_current(str(output), "digest")
