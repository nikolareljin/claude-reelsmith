"""CLI wiring, end to end through `main()`."""

from __future__ import annotations

import json
import os

import pytest
from conftest import make_clip, requires_ffmpeg

from claude_reelsmith import __version__
from claude_reelsmith.cli import main


class TestParser:
    def test_version_exits_zero_and_prints_the_version(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            main(["--version"])
        assert exit_info.value.code == 0
        assert __version__ in capsys.readouterr().out

    def test_no_subcommand_is_a_usage_error(self):
        with pytest.raises(SystemExit) as exit_info:
            main([])
        assert exit_info.value.code == 2

    def test_every_documented_subcommand_parses(self):
        from claude_reelsmith.cli import build_parser

        parser = build_parser()
        expected = {"doctor", "init", "analyze", "draft", "plan",
                    "preview", "render", "clean", "profiles"}
        actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
        assert expected <= set(actions[0].choices)


class TestProfiles:
    def test_json_output_lists_looks_and_audio_profiles(self, capsys):
        assert main(["profiles", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert {item["name"] for item in payload["looks"]} == {"news", "concert", "minimal"}
        assert "music" in {item["name"] for item in payload["audio"]}

    def test_human_output_is_produced(self, capsys):
        assert main(["profiles"]) == 0
        assert "Look presets" in capsys.readouterr().err


class TestDoctor:
    def test_json_output_is_a_list_of_checks(self, capsys):
        main(["doctor", "--json"])
        checks = json.loads(capsys.readouterr().out)
        assert isinstance(checks, list)
        assert {"name", "ok", "detail", "remedy", "required"} <= set(checks[0])

    @requires_ffmpeg
    def test_it_passes_on_a_machine_with_ffmpeg(self):
        assert main(["doctor"]) == 0


class TestInit:
    def test_it_writes_a_loadable_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert main(["init", "--input", "./vids", "--preset", "concert"]) == 0

        from claude_reelsmith import config

        cfg = config.load(str(tmp_path / "reelsmith.yaml"))
        assert cfg["io"]["input_dir"] == "./vids"
        assert cfg["look"]["preset"] == "concert"

    def test_it_refuses_to_clobber_an_existing_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        assert main(["init"]) == 2

    def test_force_overwrites(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        assert main(["init", "--force", "--preset", "minimal"]) == 0

    def test_an_invalid_preset_is_rejected_before_writing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert main(["init", "--preset", "nonexistent"]) == 2
        assert not (tmp_path / "reelsmith.yaml").exists()


@requires_ffmpeg
class TestFullWorkflow:
    """analyze → draft → plan → render, through the CLI."""

    @pytest.fixture
    def workspace(self, tmp_path, monkeypatch):
        videos = tmp_path / "in"
        videos.mkdir()
        make_clip(videos / "01_first.mp4", duration=1.5)
        make_clip(videos / "02_second.mp4", duration=1.5, volume_db=-25)
        monkeypatch.chdir(tmp_path)
        main([
            "init", "--input", str(videos), "--output", str(tmp_path / "out"),
            "--preset", "news",
        ])
        # Keep the suite fast: stabilization is covered in test_render.py.
        config_path = tmp_path / "reelsmith.yaml"
        config_path.write_text(
            config_path.read_text().replace("stabilize: true", "stabilize: false"),
            encoding="utf-8",
        )
        return tmp_path

    def test_analyze_writes_an_analysis_with_one_entry_per_clip(self, workspace):
        assert main(["analyze", "--lite"]) == 0
        analysis = json.loads((workspace / "_work" / "analysis.json").read_text())
        assert len(analysis["clips"]) == 2
        assert analysis["target"]["width"] == 320

    def test_analyze_measures_loudness(self, workspace):
        main(["analyze", "--lite"])
        analysis = json.loads((workspace / "_work" / "analysis.json").read_text())
        quiet = next(c for c in analysis["clips"] if "second" in c["name"])
        assert quiet["audio"]["needs_gain_db"] is not None
        assert quiet["audio"]["verdict"] in {"too quiet", "close to target", "too loud"}

    def test_draft_produces_a_manifest_covering_every_clip(self, workspace):
        main(["analyze", "--lite"])
        assert main(["draft"]) == 0
        entries = json.loads((workspace / "_work" / "manifest.json").read_text())["clips"]
        assert len(entries) == 2
        assert all(entry["title"] for entry in entries)

    def test_draft_refuses_to_clobber_without_force(self, workspace):
        main(["analyze", "--lite"])
        main(["draft"])
        assert main(["draft"]) == 2

    def test_plan_json_reports_every_clip(self, workspace, capsys):
        main(["analyze", "--lite"])
        main(["draft"])
        capsys.readouterr()
        assert main(["plan", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["clips"]) == 2
        assert all("output" in row for row in payload["clips"])

    def test_render_produces_output_and_a_metadata_sidecar(self, workspace):
        main(["analyze", "--lite"])
        main(["draft"])
        assert main(["render"]) == 0
        outputs = sorted((workspace / "out").glob("*.mp4"))
        assert len(outputs) == 2
        assert (workspace / "out" / "metadata.json").is_file()

    def test_a_second_render_skips_everything(self, workspace, capsys):
        main(["analyze", "--lite"])
        main(["draft"])
        main(["render"])
        capsys.readouterr()
        assert main(["render"]) == 0
        assert "already current" in capsys.readouterr().err

    def test_only_selects_a_single_clip(self, workspace):
        main(["analyze", "--lite"])
        main(["draft"])
        assert main(["render", "--only", "1"]) == 0
        assert len(list((workspace / "out").glob("*.mp4"))) == 1

    def test_an_unmatched_only_is_a_usage_error(self, workspace):
        main(["analyze", "--lite"])
        main(["draft"])
        assert main(["render", "--only", "99"]) == 2

    def test_clean_keeps_the_expensive_artefacts(self, workspace):
        main(["analyze", "--lite"])
        main(["draft"])
        assert main(["clean"]) == 0
        assert (workspace / "_work" / "analysis.json").is_file()
        assert (workspace / "_work" / "manifest.json").is_file()

    def test_clean_all_removes_the_work_directory(self, workspace):
        main(["analyze", "--lite"])
        assert main(["clean", "--all"]) == 0
        assert not (workspace / "_work").exists()


class TestErrorHandling:
    def test_a_missing_input_directory_is_a_preflight_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["init", "--input", str(tmp_path / "nope")])
        assert main(["analyze"]) == 3

    def test_a_malformed_config_is_a_usage_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reelsmith.yaml").write_text("audio:\n  bogus_key: 1\n", encoding="utf-8")
        assert main(["analyze"]) == 2

    def test_a_malformed_manifest_is_a_usage_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        work = tmp_path / "_work"
        os.makedirs(work, exist_ok=True)
        (work / "manifest.json").write_text('{"version": 99, "clips": []}', encoding="utf-8")
        assert main(["plan"]) == 2

    def test_draft_without_an_analysis_is_a_usage_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        assert main(["draft"]) == 2
