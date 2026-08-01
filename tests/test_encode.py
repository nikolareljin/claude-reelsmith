"""Encoder selection and per-encoder quality mapping."""

from __future__ import annotations

import pytest

from claude_reelsmith import encode, ff


class TestQualityMapping:
    def test_x264_uses_crf_directly(self):
        args = encode.BY_NAME["libx264"].output_args(18, "medium")
        assert args == ["-crf", "18", "-preset", "medium"]

    def test_nvenc_translates_crf_to_cq_and_maps_the_preset(self):
        args = encode.BY_NAME["h264_nvenc"].output_args(18, "medium")
        assert "-cq" in args and "18" in args
        assert "p4" in args
        assert "-crf" not in args, "NVENC does not understand -crf"

    @pytest.mark.parametrize(
        ("preset", "expected"),
        [("ultrafast", "p1"), ("veryfast", "p2"), ("medium", "p4"), ("veryslow", "p7")],
    )
    def test_the_libx264_preset_vocabulary_maps_onto_nvenc(self, preset, expected):
        assert expected in encode.BY_NAME["h264_nvenc"].output_args(18, preset)

    def test_an_unknown_preset_falls_back_to_a_sane_default(self):
        assert "p4" in encode.BY_NAME["h264_nvenc"].output_args(18, "nonsense")

    def test_qsv_uses_global_quality(self):
        assert "-global_quality" in encode.BY_NAME["h264_qsv"].output_args(18, "medium")

    def test_vaapi_uses_constant_qp(self):
        args = encode.BY_NAME["h264_vaapi"].output_args(18, "medium")
        assert "-rc_mode" in args and "CQP" in args

    def test_videotoolbox_inverts_the_scale(self):
        """VideoToolbox runs 1-100 with higher meaning better, unlike CRF."""
        better = encode.BY_NAME["h264_videotoolbox"].output_args(18, "medium")
        worse = encode.BY_NAME["h264_videotoolbox"].output_args(28, "medium")
        assert int(better[1]) > int(worse[1])

    @pytest.mark.parametrize("quality", [0, 1, 51, 63])
    def test_videotoolbox_stays_within_its_valid_range(self, quality):
        value = int(encode.BY_NAME["h264_videotoolbox"].output_args(quality, "medium")[1])
        assert 1 <= value <= 100

    def test_every_candidate_encoder_has_a_quality_mapping(self):
        for encoder in encode.CANDIDATES:
            assert encoder.name in encode._QUALITY_MAP


class TestEncoderProperties:
    def test_libx264_is_the_software_fallback_and_ranked_last(self):
        assert encode.CANDIDATES[-1].name == "libx264"
        assert encode.CANDIDATES[-1].hardware is False

    def test_hardware_encoders_are_preferred(self):
        assert all(enc.hardware for enc in encode.CANDIDATES[:-1])

    def test_vaapi_declares_the_hardware_upload_it_needs(self):
        """Software filters cannot draw on a hardware surface."""
        assert encode.BY_NAME["h264_vaapi"].filter_suffix == "format=nv12,hwupload"
        assert "-vaapi_device" in encode.BY_NAME["h264_vaapi"].init_args

    def test_software_encoders_need_no_filter_suffix(self):
        assert encode.BY_NAME["libx264"].filter_suffix == ""


class TestSelection:
    def test_an_unknown_encoder_name_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown encoder"):
            encode.select("h264_imaginary")

    def test_auto_returns_a_working_encoder(self):
        assert encode.select("auto") in encode.available()

    def test_available_only_reports_verified_encoders(self):
        """Being compiled in is not the same as working on this machine."""
        caps = ff.capabilities()
        for encoder in encode.available():
            assert caps.has_encoder(encoder.name)

    def test_libx264_is_always_usable_where_ffmpeg_is(self):
        assert any(enc.name == "libx264" for enc in encode.available())


class TestCapabilityParsing:
    def test_the_encoder_table_header_is_not_mistaken_for_an_encoder(self):
        listing = (
            "Encoders:\n"
            " V..... = Video\n"
            " ------\n"
            " V....D libx264              libx264 H.264 / AVC\n"
            " A....D aac                  AAC (Advanced Audio Coding)\n"
        )
        names = ff._parse_listing(listing)
        assert "libx264" in names
        assert "aac" in names
        assert "------" not in names
        assert "Encoders:" not in names

    def test_real_ffmpeg_reports_the_filters_this_tool_relies_on(self):
        caps = ff.capabilities()
        assert caps.has_filter("drawtext")
        assert caps.has_filter("loudnorm")
        assert caps.has_filter("overlay")
