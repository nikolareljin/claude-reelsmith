"""The manifest — the contract between deterministic tooling and judgement.

``reelsmith analyze`` writes facts. An agent reads those facts, decides what
each clip *is*, and writes a manifest. ``reelsmith render`` consumes the
manifest and never asks why.

Keeping that seam explicit and file-shaped is what makes this tool portable:
any agent that can read JSON, look at images and run a command can drive it.
See ``docs/porting-to-other-agents.md``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = 1
MANIFEST_FILENAME = "manifest.json"


class ManifestError(RuntimeError):
    """Raised for a malformed or inconsistent manifest."""


def slugify(text: str, *, fallback: str = "clip") -> str:
    """Filesystem-safe slug. Unicode letters are kept, punctuation is not."""
    cleaned = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[\s-]+", "_", cleaned)
    return slug or fallback


@dataclass
class ClipEntry:
    """One output the render stage will produce."""

    source: str
    index: int = 0
    include: bool = True
    title: str = ""
    primary: str = ""
    secondary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    slug: str = ""
    merge_with: list[str] = field(default_factory=list)
    notes: str = ""

    def resolved_slug(self) -> str:
        return self.slug or slugify(self.title or os.path.splitext(
            os.path.basename(self.source))[0])

    def sources(self) -> list[str]:
        """Every input contributing to this output, in order."""
        return [self.source, *self.merge_with]


@dataclass
class Manifest:
    """A full render plan."""

    version: int = SCHEMA_VERSION
    generated_by: str = ""
    project: dict[str, Any] = field(default_factory=dict)
    clips: list[ClipEntry] = field(default_factory=list)

    def included(self) -> list[ClipEntry]:
        return [clip for clip in self.clips if clip.include]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_by": self.generated_by,
            "project": self.project,
            "clips": [asdict(clip) for clip in self.clips],
        }


def from_dict(data: dict[str, Any]) -> Manifest:
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a JSON object.")

    version = data.get("version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ManifestError(
            f"Manifest schema version {version} is not supported "
            f"(this build understands version {SCHEMA_VERSION})."
        )

    raw_clips = data.get("clips")
    if not isinstance(raw_clips, list):
        raise ManifestError("Manifest is missing a 'clips' array.")

    known = set(ClipEntry.__dataclass_fields__)
    clips: list[ClipEntry] = []
    for position, raw in enumerate(raw_clips, start=1):
        if not isinstance(raw, dict):
            raise ManifestError(f"clips[{position - 1}] is not an object.")
        source = raw.get("source")
        if not source:
            raise ManifestError(f"clips[{position - 1}] has no 'source'.")
        unknown = set(raw) - known
        if unknown:
            raise ManifestError(
                f"clips[{position - 1}] has unknown fields: {', '.join(sorted(unknown))}"
            )
        entry = ClipEntry(**{key: raw[key] for key in raw})
        if not entry.index:
            entry.index = position
        clips.append(entry)

    _check_unique_outputs(clips)

    return Manifest(
        version=version,
        generated_by=str(data.get("generated_by") or ""),
        project=data.get("project") or {},
        clips=clips,
    )


def _check_unique_outputs(clips: list[ClipEntry]) -> None:
    """Two clips resolving to the same output name would silently overwrite."""
    seen: dict[tuple[int, str], str] = {}
    for clip in clips:
        if not clip.include:
            continue
        key = (clip.index, clip.resolved_slug())
        if key in seen:
            raise ManifestError(
                f"Two clips resolve to the same output name "
                f"(index {key[0]}, slug '{key[1]}'): {seen[key]} and {clip.source}. "
                f"Give one of them a distinct title, slug or index."
            )
        seen[key] = clip.source


def load(path: str) -> Manifest:
    if not os.path.isfile(path):
        raise ManifestError(f"Manifest not found: {path}")
    with open(path, encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"Manifest is not valid JSON: {path}\n  {exc}") from exc
    return from_dict(data)


def save(man: Manifest, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(man.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def draft_from_analysis(analysis: dict[str, Any]) -> Manifest:
    """A manifest skeleton derived from filenames alone.

    This is the ``--lite`` path and the starting point an agent edits. Titles
    are a readable rendering of the filename, which is often wrong but never
    empty, so a render always has something to show.
    """
    clips: list[ClipEntry] = []
    for position, item in enumerate(analysis.get("clips", []), start=1):
        stem = os.path.splitext(os.path.basename(item["path"]))[0]
        readable = re.sub(r"[_\-]+", " ", stem).strip()
        clips.append(
            ClipEntry(
                source=item["path"],
                index=position,
                title=readable,
                primary=readable,
                secondary="",
                slug=slugify(readable, fallback=f"clip_{position:02d}"),
            )
        )
    return Manifest(
        generated_by="reelsmith analyze (filename draft)",
        project=analysis.get("project", {}),
        clips=clips,
    )


def output_name(clip: ClipEntry, template: str) -> str:
    """Render the configured output filename template."""
    try:
        return template.format(
            index=clip.index,
            slug=clip.resolved_slug(),
            title=clip.title,
            stem=os.path.splitext(os.path.basename(clip.source))[0],
        )
    except (KeyError, ValueError) as exc:
        raise ManifestError(
            f"Bad io.output_name_template '{template}': {exc}. "
            f"Available fields: index, slug, title, stem."
        ) from exc
