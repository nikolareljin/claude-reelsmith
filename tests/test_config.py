"""Configuration loading, merging and validation."""

from __future__ import annotations

import pytest

from claude_reelsmith import config


def write(tmp_path, text: str) -> str:
    path = tmp_path / "reelsmith.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_defaults_load_without_a_file():
    cfg = config.load(None)
    assert cfg["look"]["preset"] == "news"
    assert cfg["audio"]["profile"] == "music"


def test_user_values_override_defaults_without_dropping_siblings(tmp_path):
    cfg = config.load(write(tmp_path, "audio:\n  profile: speech\n"))
    assert cfg["audio"]["profile"] == "speech"
    # The sibling keys in the same section survive the merge.
    assert cfg["audio"]["two_pass"] is True


def test_unknown_key_is_an_error_not_a_silent_noop(tmp_path):
    """A typo must not look like a setting that quietly does nothing."""
    with pytest.raises(config.ConfigError, match="Unknown configuration key 'audio.profil'"):
        config.load(write(tmp_path, "audio:\n  profil: speech\n"))


def test_unknown_top_level_section_is_rejected(tmp_path):
    with pytest.raises(config.ConfigError, match="Unknown configuration key 'audioo'"):
        config.load(write(tmp_path, "audioo:\n  profile: speech\n"))


def test_missing_file_is_reported_clearly():
    with pytest.raises(config.ConfigError, match="Config file not found"):
        config.load("/nonexistent/reelsmith.yaml")


def test_non_mapping_file_is_rejected(tmp_path):
    with pytest.raises(config.ConfigError, match="must contain a YAML mapping"):
        config.load(write(tmp_path, "- just\n- a list\n"))


def test_empty_file_yields_defaults(tmp_path):
    assert config.load(write(tmp_path, "")) == config.load(None)


class TestValidation:
    def test_unknown_preset_lists_the_valid_ones(self):
        cfg = config.load(None)
        cfg["look"]["preset"] = "nope"
        with pytest.raises(config.ConfigError, match="Available: concert, minimal, news"):
            config.validate(cfg)

    def test_unknown_audio_profile_is_rejected(self):
        cfg = config.load(None)
        cfg["audio"]["profile"] = "nope"
        with pytest.raises(config.ConfigError, match="Unknown audio profile"):
            config.validate(cfg)

    def test_custom_profile_requires_a_chain(self):
        cfg = config.load(None)
        cfg["audio"]["profile"] = "custom"
        with pytest.raises(config.ConfigError, match="audio.chain is empty"):
            config.validate(cfg)

    def test_custom_profile_with_a_chain_is_accepted(self):
        cfg = config.load(None)
        cfg["audio"]["profile"] = "custom"
        cfg["audio"]["chain"] = "volume=2"
        config.validate(cfg)

    def test_bad_logo_position_is_rejected(self):
        cfg = config.load(None)
        cfg["logo"]["position"] = "middle"
        with pytest.raises(config.ConfigError, match="Unknown logo position"):
            config.validate(cfg)

    @pytest.mark.parametrize("opacity", [0, -0.5, 1.5])
    def test_out_of_range_opacity_is_rejected(self, opacity):
        cfg = config.load(None)
        cfg["logo"]["opacity"] = opacity
        with pytest.raises(config.ConfigError, match="logo.opacity"):
            config.validate(cfg)

    def test_fades_longer_than_the_hold_are_rejected(self):
        """Two 4s fades cannot fit inside a 5s display window."""
        cfg = config.load(None)
        cfg["look"]["show_seconds"] = 5
        cfg["look"]["fade_seconds"] = 4
        with pytest.raises(config.ConfigError, match="fade_seconds is too long"):
            config.validate(cfg)

    def test_negative_job_count_is_rejected(self):
        cfg = config.load(None)
        cfg["encode"]["jobs"] = -1
        with pytest.raises(config.ConfigError, match="non-negative integer"):
            config.validate(cfg)


class TestJobResolution:
    def test_explicit_job_count_wins(self):
        cfg = config.load(None)
        cfg["encode"]["jobs"] = 7
        assert config.resolve_jobs(cfg) == 7

    def test_zero_selects_automatically_and_is_never_zero(self):
        assert config.resolve_jobs(config.load(None)) >= 1


def test_dump_round_trips(tmp_path):
    cfg = config.load(None)
    cfg["project"]["title"] = "Spring Concert"
    reloaded = config.load(write(tmp_path, config.dump(cfg)))
    assert reloaded["project"]["title"] == "Spring Concert"


def test_find_config_walks_up_to_parent_directories(tmp_path):
    (tmp_path / "reelsmith.yaml").write_text("", encoding="utf-8")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert config.find_config(str(nested)) == str(tmp_path / "reelsmith.yaml")


def test_find_config_returns_none_when_absent(tmp_path):
    assert config.find_config(str(tmp_path)) is None
