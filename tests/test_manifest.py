"""The manifest contract."""

from __future__ import annotations

import json

import pytest

from claude_reelsmith import manifest


def entry(**overrides) -> dict:
    base = {"source": "/videos/a.mp4", "index": 1, "title": "A Title"}
    base.update(overrides)
    return base


def doc(*clips) -> dict:
    return {"version": 1, "clips": list(clips) or [entry()]}


class TestSlugify:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # The em-dash is stripped, and the run of whitespace it leaves
            # behind collapses to a single separator.
            ("Bach — Partita No. 2", "bach_partita_no_2"),
            ("O'Brien, Anna", "obrien_anna"),
            ("  spaced  out  ", "spaced_out"),
            ("Trailing...", "trailing"),
        ],
    )
    def test_punctuation_is_stripped(self, text, expected):
        assert manifest.slugify(text) == expected

    def test_accented_letters_survive(self):
        assert manifest.slugify("Dvořák") == "dvořák"

    def test_empty_input_falls_back(self):
        assert manifest.slugify("!!!", fallback="clip") == "clip"


class TestLoading:
    def test_a_minimal_manifest_loads(self):
        man = manifest.from_dict(doc())
        assert man.clips[0].title == "A Title"

    def test_missing_index_is_filled_from_position(self):
        man = manifest.from_dict(doc(
            {"source": "/a.mp4"}, {"source": "/b.mp4"}
        ))
        assert [clip.index for clip in man.clips] == [1, 2]

    def test_a_clip_without_a_source_is_rejected(self):
        with pytest.raises(manifest.ManifestError, match="has no 'source'"):
            manifest.from_dict(doc({"title": "orphan"}))

    def test_unknown_clip_fields_are_rejected(self):
        with pytest.raises(manifest.ManifestError, match="unknown fields: colour"):
            manifest.from_dict(doc(entry(colour="red")))

    def test_a_future_schema_version_is_refused(self):
        with pytest.raises(manifest.ManifestError, match="schema version 99"):
            manifest.from_dict({"version": 99, "clips": []})

    def test_a_missing_clips_array_is_rejected(self):
        with pytest.raises(manifest.ManifestError, match="missing a 'clips' array"):
            manifest.from_dict({"version": 1})

    def test_colliding_outputs_are_caught_before_rendering(self):
        """Two clips with the same index and slug would overwrite each other."""
        with pytest.raises(manifest.ManifestError, match="same output name"):
            manifest.from_dict(doc(
                {"source": "/a.mp4", "index": 1, "title": "Same"},
                {"source": "/b.mp4", "index": 1, "title": "Same"},
            ))

    def test_excluded_clips_do_not_trigger_collisions(self):
        man = manifest.from_dict(doc(
            {"source": "/a.mp4", "index": 1, "title": "Same"},
            {"source": "/b.mp4", "index": 1, "title": "Same", "include": False},
        ))
        assert len(man.included()) == 1

    def test_invalid_json_reports_the_path(self, tmp_path):
        bad = tmp_path / "manifest.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(manifest.ManifestError, match="not valid JSON"):
            manifest.load(str(bad))

    def test_a_missing_file_is_reported(self):
        with pytest.raises(manifest.ManifestError, match="Manifest not found"):
            manifest.load("/nonexistent/manifest.json")


class TestClipEntry:
    def test_slug_is_derived_from_the_title_when_absent(self):
        clip = manifest.ClipEntry(source="/a.mov", title="Bach — Partita")
        assert clip.resolved_slug() == "bach_partita"

    def test_slug_falls_back_to_the_filename(self):
        clip = manifest.ClipEntry(source="/videos/IMG_4471.MOV")
        assert clip.resolved_slug() == "img_4471"

    def test_an_explicit_slug_wins(self):
        clip = manifest.ClipEntry(source="/a.mov", title="Ignored", slug="chosen")
        assert clip.resolved_slug() == "chosen"

    def test_merged_sources_are_ordered_primary_first(self):
        clip = manifest.ClipEntry(source="/a.mov", merge_with=["/b.mov", "/c.mov"])
        assert clip.sources() == ["/a.mov", "/b.mov", "/c.mov"]


class TestOutputNames:
    def test_the_default_template_renders(self):
        clip = manifest.ClipEntry(source="/a.mov", index=3, title="Bach")
        assert manifest.output_name(clip, "{index:02d}_{slug}.mp4") == "03_bach.mp4"

    def test_the_original_filename_stem_is_available(self):
        clip = manifest.ClipEntry(source="/videos/IMG_4471.MOV", index=1)
        assert manifest.output_name(clip, "{stem}.mp4") == "IMG_4471.mp4"

    def test_an_unknown_field_names_the_valid_ones(self):
        clip = manifest.ClipEntry(source="/a.mov")
        with pytest.raises(manifest.ManifestError, match="Available fields"):
            manifest.output_name(clip, "{nonexistent}.mp4")


def test_save_and_load_round_trip(tmp_path):
    original = manifest.from_dict(doc(entry(
        title="Bach — Partita", secondary="Anna Petrova", tags=["live", "concert"]
    )))
    path = str(tmp_path / "manifest.json")
    manifest.save(original, path)
    reloaded = manifest.load(path)
    assert reloaded.clips[0].title == "Bach — Partita"
    assert reloaded.clips[0].tags == ["live", "concert"]


def test_saved_manifests_are_utf8_not_escaped(tmp_path):
    man = manifest.from_dict(doc(entry(title="Dvořák — Humoresque")))
    path = tmp_path / "manifest.json"
    manifest.save(man, str(path))
    assert "Dvořák" in path.read_text(encoding="utf-8")


def test_draft_from_analysis_makes_filenames_readable():
    analysis = {"clips": [
        {"path": "/videos/01_anna-petrova_bach.mp4"},
        {"path": "/videos/02_marco_vivaldi.mp4"},
    ]}
    draft = manifest.draft_from_analysis(analysis)
    assert draft.clips[0].title == "01 anna petrova bach"
    assert draft.clips[1].index == 2
    # Every entry gets a usable title so a render is never blocked.
    assert all(clip.title for clip in draft.clips)


def test_draft_output_is_valid_manifest_json(tmp_path):
    draft = manifest.draft_from_analysis({"clips": [{"path": "/v/a.mp4"}]})
    path = str(tmp_path / "m.json")
    manifest.save(draft, path)
    manifest.from_dict(json.loads(open(path, encoding="utf-8").read()))
