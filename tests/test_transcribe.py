"""Subtitle generation.

The transcription itself is faster-whisper's job and is not re-tested here.
What matters is that a transcript becomes valid SubRip.
"""

from __future__ import annotations

import pytest

from claude_reelsmith import transcribe


def transcript(*segments) -> transcribe.Transcript:
    parsed = [transcribe.Segment(start=s, end=e, text=t) for s, e, t in segments]
    return transcribe.Transcript(
        language="en",
        text=" ".join(segment.text for segment in parsed),
        segments=parsed,
    )


class TestTimestamps:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0.0, "00:00:00,000"),
            (1.5, "00:00:01,500"),
            (61.25, "00:01:01,250"),
            (3661.001, "01:01:01,001"),
            (-5.0, "00:00:00,000"),
        ],
    )
    def test_srt_timestamp_formatting(self, seconds, expected):
        assert transcribe._srt_timestamp(seconds) == expected


class TestSrt:
    def test_segments_are_numbered_from_one(self):
        body = transcribe.to_srt(transcript((0.0, 2.0, "First"), (2.0, 4.0, "Second")))
        lines = body.splitlines()
        assert lines[0] == "1"
        assert lines[4] == "2"

    def test_the_arrow_separator_is_present(self):
        body = transcribe.to_srt(transcript((0.0, 2.5, "Hello")))
        assert "00:00:00,000 --> 00:00:02,500" in body

    def test_empty_segments_are_dropped(self):
        body = transcribe.to_srt(transcript((0.0, 1.0, ""), (1.0, 2.0, "Real")))
        assert body.count("-->") == 1

    def test_an_empty_transcript_yields_an_empty_document(self):
        assert transcribe.to_srt(transcript()).strip() == ""

    def test_unicode_survives(self):
        body = transcribe.to_srt(transcript((0.0, 1.0, "Dvořák — Humoresque")))
        assert "Dvořák — Humoresque" in body


class TestWriting:
    def test_a_sidecar_is_written_and_readable(self, tmp_path):
        path = tmp_path / "clip.srt"
        written = transcribe.write_srt(transcript((0.0, 2.0, "Hello")), str(path))
        assert written == str(path)
        assert "Hello" in path.read_text(encoding="utf-8")

    def test_no_file_is_written_when_there_is_no_speech(self, tmp_path):
        path = tmp_path / "clip.srt"
        assert transcribe.write_srt(transcript(), str(path)) is None
        assert not path.exists()

    def test_intermediate_directories_are_created(self, tmp_path):
        path = tmp_path / "nested" / "deeper" / "clip.srt"
        assert transcribe.write_srt(transcript((0.0, 1.0, "Hi")), str(path))
        assert path.is_file()


class TestTranscriptHelpers:
    def test_head_truncates_to_the_requested_length(self):
        long = transcript((0.0, 1.0, "word " * 500))
        assert len(long.head(100)) == 100

    def test_round_trip_through_a_dict(self):
        original = transcript((0.0, 2.0, "Hello"), (2.0, 4.0, "World"))
        data = original.to_dict()
        assert data["language"] == "en"
        assert len(data["segments"]) == 2
        assert data["segments"][0] == {"start": 0.0, "end": 2.0, "text": "Hello"}


def test_availability_reports_a_boolean():
    assert isinstance(transcribe.is_available(), bool)
