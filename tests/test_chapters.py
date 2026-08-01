"""Silence detection and chapter derivation."""

from __future__ import annotations

from claude_reelsmith import chapters


def silence(start: float, end: float) -> chapters.Silence:
    return chapters.Silence(start=start, end=end)


class TestSilence:
    def test_duration_and_midpoint(self):
        gap = silence(100.0, 110.0)
        assert gap.duration == 10.0
        assert gap.midpoint == 105.0


class TestDeriveChapters:
    def test_no_silences_gives_one_chapter_spanning_the_clip(self):
        found = chapters.derive_chapters(600.0, [])
        assert len(found) == 1
        assert (found[0].start, found[0].end) == (0.0, 600.0)

    def test_each_long_gap_starts_a_new_chapter(self):
        found = chapters.derive_chapters(900.0, [silence(300, 310), silence(600, 612)])
        assert len(found) == 3
        assert found[0].start == 0.0
        assert found[1].start == 305.0
        assert found[2].end == 900.0

    def test_a_short_pause_mid_performance_is_not_a_boundary(self):
        """A two-second breath is not a new item."""
        found = chapters.derive_chapters(600.0, [silence(10, 12), silence(15, 17)])
        assert len(found) == 1

    def test_chapters_are_contiguous_and_ordered(self):
        found = chapters.derive_chapters(900.0, [silence(300, 310), silence(600, 612)])
        for earlier, later in zip(found, found[1:], strict=False):
            assert earlier.end == later.start
            assert earlier.index < later.index

    def test_a_tiny_trailing_chapter_folds_into_its_predecessor(self):
        found = chapters.derive_chapters(305.0, [silence(295, 300)])
        assert len(found) == 1

    def test_zero_duration_yields_nothing(self):
        assert chapters.derive_chapters(0.0, [silence(1, 5)]) == []

    def test_titles_follow_the_template(self):
        found = chapters.derive_chapters(900.0, [silence(300, 310)],
                                         title_template="Part {index}")
        assert found[0].title == "Part 1"
        assert found[1].title == "Part 2"


class TestSerialisation:
    def test_ffmetadata_has_a_header_and_one_block_per_chapter(self):
        found = chapters.derive_chapters(900.0, [silence(300, 310)])
        text = chapters.to_ffmetadata(found)
        assert text.startswith(";FFMETADATA1")
        assert text.count("[CHAPTER]") == 2
        assert "TIMEBASE=1/1000" in text

    def test_ffmetadata_times_are_milliseconds(self):
        found = chapters.derive_chapters(900.0, [silence(300, 310)])
        assert "START=305000" in chapters.to_ffmetadata(found)

    def test_plain_text_uses_description_style_timestamps(self):
        found = chapters.derive_chapters(900.0, [silence(300, 310)])
        text = chapters.to_plain_text(found)
        assert "0:00  Item 1" in text
        assert "5:05  Item 2" in text

    def test_hours_appear_only_when_needed(self):
        found = chapters.derive_chapters(7500.0, [silence(3600, 3620)])
        assert "1:00:10" in chapters.to_plain_text(found)

    def test_an_empty_chapter_list_produces_no_text(self):
        assert chapters.to_plain_text([]) == ""


class TestSilenceLogParsing:
    def test_a_trailing_silence_without_an_end_marker_is_handled(self, monkeypatch):
        """ffmpeg omits silence_end when a file ends mid-silence."""
        import subprocess

        class FakeProc:
            returncode = 0
            stderr = (
                "[silencedetect @ 0x1] silence_start: 10.5\n"
                "[silencedetect @ 0x1] silence_end: 14.2 | silence_duration: 3.7\n"
                "[silencedetect @ 0x1] silence_start: 58.0\n"
            )

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
        found = chapters.detect_silences("/fake.mp4", min_seconds=2.0)
        assert len(found) == 2
        assert found[0].end == 14.2
        assert found[1].end == 60.0

    def test_a_failed_probe_returns_nothing_rather_than_raising(self, monkeypatch):
        import subprocess

        class FakeProc:
            returncode = 1
            stderr = ""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
        assert chapters.detect_silences("/fake.mp4") == []
