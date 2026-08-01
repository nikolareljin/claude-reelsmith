"""Reconciling mixed input onto one canvas."""

from __future__ import annotations

import pytest

from claude_reelsmith import normalize
from claude_reelsmith.probe import MediaInfo


def info(width=1920, height=1080, fps=30.0, rotation=0, has_audio=True, duration=10.0):
    return MediaInfo(
        path=f"/v/{width}x{height}.mp4",
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        rotation=rotation,
        has_audio=has_audio,
        audio_channels=2 if has_audio else 0,
        audio_sample_rate=48000 if has_audio else 0,
        video_codec="h264",
        audio_codec="aac" if has_audio else "",
        pix_fmt="yuv420p",
        size_bytes=1024,
        mtime=0.0,
    )


class TestRotation:
    def test_a_90_degree_rotation_swaps_the_display_dimensions(self):
        clip = info(1920, 1080, rotation=90)
        assert (clip.display_width, clip.display_height) == (1080, 1920)
        assert clip.is_portrait

    def test_negative_rotation_is_handled(self):
        assert info(1920, 1080, rotation=-90).display_width == 1080

    def test_180_degrees_does_not_swap(self):
        assert info(1920, 1080, rotation=180).display_width == 1920


class TestTargetSelection:
    def test_the_most_common_shape_wins_over_the_largest(self):
        """One stray 4K clip must not force an expensive 4K batch."""
        clips = [info(1920, 1080) for _ in range(5)] + [info(3840, 2160)]
        assert normalize.choose_target(clips).height == 1080

    def test_ties_break_toward_the_larger_frame(self):
        clips = [info(1280, 720), info(1920, 1080)]
        assert normalize.choose_target(clips).height == 1080

    def test_an_explicit_height_override_preserves_aspect(self):
        target = normalize.choose_target([info(1920, 1080)], target_height=720)
        assert (target.width, target.height) == (1280, 720)

    def test_dimensions_are_always_even_for_yuv420p(self):
        target = normalize.choose_target([info(1921, 1081)])
        assert target.width % 2 == 0
        assert target.height % 2 == 0

    def test_rotation_is_respected_when_choosing_the_target(self):
        clips = [info(1920, 1080, rotation=90) for _ in range(3)]
        target = normalize.choose_target(clips)
        assert (target.width, target.height) == (1080, 1920)

    def test_an_empty_input_set_is_rejected(self):
        with pytest.raises(ValueError, match="empty input set"):
            normalize.choose_target([])

    def test_fps_defaults_when_no_clip_reports_one(self):
        assert normalize.choose_target([info(fps=0)]).fps == 30.0


class TestVideoFilter:
    def test_a_matching_clip_needs_no_filter(self):
        target = normalize.Target(1920, 1080, 30.0)
        assert normalize.video_filter(info(1920, 1080, fps=30.0), target) == ""

    def test_mismatched_clips_are_scaled_and_padded_never_cropped(self):
        """Cropping to fit would silently discard picture the user shot."""
        target = normalize.Target(1920, 1080, 30.0)
        chain = normalize.video_filter(info(1280, 720), target)
        assert "force_original_aspect_ratio=decrease" in chain
        assert "pad=1920:1080" in chain
        assert "crop" not in chain

    def test_sample_aspect_is_reset_after_padding(self):
        target = normalize.Target(1920, 1080, 30.0)
        assert "setsar=1" in normalize.video_filter(info(1280, 720), target)

    def test_portrait_into_landscape_is_pillarboxed(self):
        target = normalize.Target(1920, 1080, 30.0)
        chain = normalize.video_filter(info(1080, 1920), target)
        assert "pad=1920:1080" in chain
        assert "crop" not in chain

    def test_frame_rate_is_converted_when_it_differs(self):
        target = normalize.Target(1920, 1080, 30.0)
        assert "fps=30.0" in normalize.video_filter(info(1920, 1080, fps=25.0), target)

    def test_a_trivial_frame_rate_difference_is_ignored(self):
        target = normalize.Target(1920, 1080, 30.0)
        assert normalize.video_filter(info(1920, 1080, fps=30.001), target) == ""


class TestSilentClips:
    def test_a_clip_with_audio_needs_no_extra_input(self):
        assert normalize.audio_input_args(info(has_audio=True)) == []

    def test_a_silent_clip_gets_a_generated_track_instead_of_failing(self):
        args = normalize.audio_input_args(info(has_audio=False))
        assert "anullsrc=channel_layout=stereo:sample_rate=48000" in args

    def test_the_generated_track_matches_the_clip_length(self):
        args = normalize.audio_input_args(info(has_audio=False, duration=42.5))
        assert "42.500" in args


def test_summary_names_every_kind_of_mismatch():
    clips = [info(1920, 1080), info(1280, 720, fps=25.0), info(has_audio=False)]
    text = normalize.summarize(clips, normalize.choose_target(clips))
    assert "3 clips" in text
    assert "different frame sizes" in text
    assert "different frame rates" in text
    assert "no audio track" in text
