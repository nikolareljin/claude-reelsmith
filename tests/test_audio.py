"""Audio profiles and two-pass loudness normalisation."""

from __future__ import annotations

import pytest

from claude_reelsmith import audio

GOOD_MEASUREMENT = {
    "input_i": "-27.4",
    "input_tp": "-9.2",
    "input_lra": "5.1",
    "input_thresh": "-37.8",
    "target_offset": "0.3",
}


class TestProfiles:
    def test_the_carried_over_profiles_are_unchanged(self):
        """These chains were tuned on real recordings; they must not drift."""
        assert audio.PROFILES["gentle"].pre == (
            "highpass=f=60,dynaudnorm=f=500:g=31:p=0.9:m=10:s=0"
        )
        assert audio.PROFILES["standard"].pre == (
            "highpass=f=50,dynaudnorm=f=400:g=31:p=0.92:m=15:s=0"
        )
        assert audio.PROFILES["music"].pre == (
            "highpass=f=50,"
            "acompressor=threshold=-20dB:ratio=2.5:attack=20:release=300:makeup=2,"
            "dynaudnorm=f=350:g=31:p=0.95:m=30:s=6"
        )

    def test_carried_over_loudness_targets_are_unchanged(self):
        assert audio.PROFILES["gentle"].target_i == -16.0
        assert audio.PROFILES["standard"].target_i == -14.0
        assert audio.PROFILES["music"].target_i == -13.0

    def test_broadcast_uses_the_ebu_r128_target(self):
        assert audio.PROFILES["broadcast"].target_i == -23.0

    def test_the_predecessors_profile_name_still_works(self):
        assert audio.resolve_profile("loud-piano") is audio.PROFILES["music"]

    def test_unknown_profile_raises(self):
        with pytest.raises(KeyError):
            audio.resolve_profile("nope")

    def test_every_profile_ends_with_a_limiter(self):
        for profile in audio.PROFILES.values():
            assert profile.post.startswith("alimiter=")


class TestRenderChain:
    def test_single_pass_omits_measured_values(self):
        chain = audio.render_chain({"profile": "music", "two_pass": False}, None)
        assert "loudnorm=I=-13.0:TP=-1.5:LRA=9.0" in chain
        assert "measured_I" not in chain

    def test_two_pass_feeds_measurements_back_and_goes_linear(self):
        chain = audio.render_chain({"profile": "music", "two_pass": True}, GOOD_MEASUREMENT)
        assert "measured_I=-27.4" in chain
        assert "measured_TP=-9.2" in chain
        assert "measured_LRA=5.1" in chain
        assert "measured_thresh=-37.8" in chain
        assert "linear=true" in chain

    def test_two_pass_falls_back_gracefully_without_measurements(self):
        chain = audio.render_chain({"profile": "music", "two_pass": True}, None)
        assert "loudnorm=" in chain
        assert "measured_I" not in chain

    def test_target_lufs_overrides_the_profile(self):
        chain = audio.render_chain({"profile": "music", "target_lufs": -20.0}, None)
        assert "I=-20.0" in chain

    def test_chain_order_is_pre_then_loudnorm_then_limiter(self):
        chain = audio.render_chain({"profile": "standard"}, None)
        assert chain.index("highpass") < chain.index("loudnorm") < chain.index("alimiter")

    def test_custom_chain_is_passed_through_verbatim(self):
        chain = audio.render_chain({"profile": "custom", "chain": "volume=3,anull"}, None)
        assert chain == "volume=3,anull"

    def test_custom_profile_without_a_chain_raises(self):
        with pytest.raises(ValueError, match="audio.chain is empty"):
            audio.render_chain({"profile": "custom", "chain": None}, None)


class TestSilenceGuard:
    """Feeding silence measurements back would amplify noise enormously."""

    @pytest.mark.parametrize("value", ["-inf", "-70.0", "-91.2"])
    def test_silent_measurements_are_refused(self, value):
        measured = {**GOOD_MEASUREMENT, "input_i": value}
        chain = audio.render_chain({"profile": "music", "two_pass": True}, measured)
        assert "measured_I" not in chain

    def test_incomplete_measurements_are_refused(self):
        chain = audio.render_chain(
            {"profile": "music", "two_pass": True}, {"input_i": "-20.0"}
        )
        assert "measured_I" not in chain

    def test_non_numeric_measurements_are_refused(self):
        measured = {**GOOD_MEASUREMENT, "input_tp": "n/a"}
        chain = audio.render_chain({"profile": "music", "two_pass": True}, measured)
        assert "measured_I" not in chain


class TestMeasurementParsing:
    def test_json_is_extracted_from_the_ffmpeg_log_tail(self):
        stderr = (
            "[Parsed_loudnorm_0 @ 0x55] \n"
            "some unrelated log line\n"
            '{\n\t"input_i" : "-27.40",\n\t"input_tp" : "-9.20",\n'
            '\t"input_lra" : "5.10",\n\t"input_thresh" : "-37.80",\n'
            '\t"target_offset" : "0.30"\n}\n'
        )
        parsed = audio._parse_loudnorm_json(stderr)
        assert parsed["input_i"] == "-27.40"

    def test_absent_json_returns_none(self):
        assert audio._parse_loudnorm_json("no json at all") is None

    def test_measurement_chain_includes_the_pre_chain(self):
        """loudnorm must measure the signal it will actually receive."""
        chain = audio.measure_chain({"profile": "music"})
        assert chain.startswith(audio.PROFILES["music"].pre)
        assert "print_format=json" in chain

    def test_custom_chains_are_not_measurable(self):
        assert audio.measure_chain({"profile": "custom", "chain": "volume=2"}) == ""


def test_describe_lists_every_profile():
    assert len(audio.describe()) == len(audio.PROFILES)
