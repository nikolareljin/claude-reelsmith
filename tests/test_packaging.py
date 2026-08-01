"""Repository-level invariants: version sync, resource mirroring, site integrity.

These catch the kind of mistake that is invisible in review and only shows up
after a release.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

try:  # tomllib landed in the standard library in 3.11
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import claude_reelsmith

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills" / "reelsmith"
RESOURCES = ROOT / "src" / "claude_reelsmith" / "resources" / "reelsmith"
SITE = ROOT / "site" / "index.html"


class TestVersionSync:
    """The version lives in three files and they must agree."""

    def test_plugin_manifest_matches_the_package(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        assert manifest["version"] == claude_reelsmith.__version__

    def test_pyproject_matches_the_package(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text())
        assert data["project"]["version"] == claude_reelsmith.__version__

    def test_the_version_is_semver(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", claude_reelsmith.__version__)

    def test_the_changelog_documents_this_version(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        assert f"## [{claude_reelsmith.__version__}]" in changelog


class TestPluginManifest:
    def test_it_carries_exactly_the_house_fields(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        assert set(manifest) == {
            "name", "version", "description", "author",
            "homepage", "repository", "license", "keywords",
        }

    def test_the_name_matches_the_repository(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        assert manifest["name"] == "claude-reelsmith"
        assert manifest["repository"].endswith("/claude-reelsmith")

    def test_no_component_path_fields_are_declared(self):
        """Commands, agents and skills are auto-discovered from the repo root."""
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        for field in ("commands", "agents", "skills", "hooks"):
            assert field not in manifest

    def test_the_description_matches_pyproject(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
        assert manifest["description"] == pyproject["project"]["description"]


class TestResourceMirror:
    """`skills/` is loaded from a checkout; `resources/` ships in the wheel."""

    def test_the_same_files_exist_on_both_sides(self):
        skill_files = {p.relative_to(SKILLS) for p in SKILLS.rglob("*") if p.is_file()}
        resource_files = {p.relative_to(RESOURCES) for p in RESOURCES.rglob("*") if p.is_file()}
        assert skill_files == resource_files, (
            "skills/ and src/claude_reelsmith/resources/ have drifted. Re-sync with:\n"
            "  rm -rf src/claude_reelsmith/resources/reelsmith\n"
            "  cp -r skills/reelsmith src/claude_reelsmith/resources/reelsmith"
        )

    def test_every_mirrored_file_is_byte_identical(self):
        for source in SKILLS.rglob("*"):
            if not source.is_file():
                continue
            mirrored = RESOURCES / source.relative_to(SKILLS)
            assert source.read_bytes() == mirrored.read_bytes(), f"drift in {source.name}"


class TestSkillStructure:
    def test_the_skill_has_name_and_description_frontmatter(self):
        text = (SKILLS / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert re.search(r"^name:\s*reelsmith\s*$", frontmatter, re.MULTILINE)
        assert re.search(r"^description:\s*\S", frontmatter, re.MULTILINE)

    def test_the_skill_entry_file_stays_short_enough_to_dispatch(self):
        """Detail belongs in references/, loaded on demand."""
        lines = (SKILLS / "SKILL.md").read_text(encoding="utf-8").splitlines()
        assert len(lines) < 120, f"SKILL.md is {len(lines)} lines; move detail into references/"

    def test_every_referenced_file_exists(self):
        text = (SKILLS / "SKILL.md").read_text(encoding="utf-8")
        for match in re.finditer(r"`((?:references|templates)/[\w.\-]+)`", text):
            assert (SKILLS / match.group(1)).is_file(), f"missing {match.group(1)}"

    def test_the_skill_names_its_author(self):
        text = (SKILLS / "SKILL.md").read_text(encoding="utf-8")
        assert "Nikola Reljin" in text

    def test_the_example_manifest_validates(self):
        from claude_reelsmith import manifest as manifest_mod

        data = json.loads((SKILLS / "templates" / "manifest.example.json").read_text())
        parsed = manifest_mod.from_dict(data)
        assert len(parsed.clips) >= 2
        # It demonstrates exclusion, which is the behaviour agents get wrong.
        assert any(not clip.include for clip in parsed.clips)


class TestCommand:
    def test_it_declares_description_and_argument_hint(self):
        text = (ROOT / "commands" / "nr-reelsmith.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        assert re.search(r"^description:\s*\S", frontmatter, re.MULTILINE)
        assert re.search(r"^argument-hint:\s*\S", frontmatter, re.MULTILINE)

    def test_it_points_at_the_skill_rather_than_restating_it(self):
        text = (ROOT / "commands" / "nr-reelsmith.md").read_text(encoding="utf-8")
        assert "skills/reelsmith/SKILL.md" in text


class TestSite:
    def test_the_page_exists_and_declares_a_title(self):
        html = SITE.read_text(encoding="utf-8")
        assert "<title>" in html
        assert "claude-reelsmith" in html

    def test_it_is_self_contained_with_no_external_assets(self):
        """The page must not depend on a CDN staying up.

        Only tags that actually fetch something count. `rel="author"` and
        `rel="canonical"` are metadata and may legitimately point off-site.
        """
        html = SITE.read_text(encoding="utf-8")
        fetching = [
            tag for tag in re.findall(r"<(?:script|link)[^>]*>", html)
            if re.search(r'rel="(stylesheet|preconnect|preload|prefetch)"', tag)
            or re.search(r"<script[^>]+src=", tag)
        ]
        for tag in fetching:
            assert "//" not in tag.split("=", 1)[-1], f"external asset: {tag}"

    def test_styles_and_scripts_are_inline(self):
        html = SITE.read_text(encoding="utf-8")
        assert "<style>" in html
        assert not re.search(r"<script[^>]+src=", html)

    def test_every_local_link_resolves(self):
        html = SITE.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"]+)"', html):
            if href.startswith(("http", "#", "mailto:", "data:")):
                continue
            assert (SITE.parent / href).exists(), f"broken local link: {href}"

    def test_every_anchor_target_exists(self):
        html = SITE.read_text(encoding="utf-8")
        ids = set(re.findall(r'id="([^"]+)"', html))
        for href in re.findall(r'href="#([^"]+)"', html):
            assert href in ids, f"anchor #{href} has no target"

    def test_it_credits_the_author_with_both_links(self):
        html = SITE.read_text(encoding="utf-8")
        assert 'name="author" content="Nikola Reljin"' in html
        assert "github.com/nikolareljin" in html
        assert "linkedin.com/in/nikolareljin" in html

    def test_it_does_not_promise_a_pypi_install(self):
        """The package is installed from git, not PyPI."""
        html = SITE.read_text(encoding="utf-8")
        assert "pip install claude-reelsmith" not in html


class TestAttribution:
    @pytest.mark.parametrize("filename", ["README.md", "ABOUT.md"])
    def test_the_author_and_both_links_appear(self, filename):
        text = (ROOT / filename).read_text(encoding="utf-8")
        assert "Nikola Reljin" in text
        assert "github.com/nikolareljin" in text
        assert "linkedin.com/in/nikolareljin" in text

    def test_the_licence_is_attributed(self):
        assert "Nikola Reljin" in (ROOT / "LICENSE").read_text(encoding="utf-8")

    def test_pyproject_declares_the_author_urls(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text())
        urls = data["project"]["urls"]
        assert urls["Author"] == "https://github.com/nikolareljin"
        assert "Repository" in urls and "Issues" in urls

    def test_about_cross_links_the_other_plugins(self):
        text = (ROOT / "ABOUT.md").read_text(encoding="utf-8")
        assert "claude-docsmith" in text
        assert "claude-reposec" in text


class TestDocumentation:
    REQUIRED = [
        "README.md", "ABOUT.md", "CHANGELOG.md", "CONTRIBUTING.md",
        "LICENSE", "PRIVACY.md", "SECURITY.md", "TERMS.md",
    ]

    @pytest.mark.parametrize("filename", REQUIRED)
    def test_the_boilerplate_file_exists(self, filename):
        assert (ROOT / filename).is_file()

    def test_every_readme_link_into_docs_resolves(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in re.findall(r'\]\((docs/[\w./-]+)\)', text):
            assert (ROOT / target).is_file(), f"README links to missing {target}"

    def test_the_porting_guide_exists_and_names_other_agents(self):
        text = (ROOT / "docs" / "porting-to-other-agents.md").read_text(encoding="utf-8")
        for agent in ("Codex", "Cursor", "Gemini", "OpenCode", "MCP"):
            assert agent in text

    def test_relative_links_between_docs_resolve(self):
        for path in (ROOT / "docs").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r'\]\((\.\.?/[\w./-]+)\)', text):
                resolved = (path.parent / target).resolve()
                assert resolved.exists(), f"{path.name} links to missing {target}"
