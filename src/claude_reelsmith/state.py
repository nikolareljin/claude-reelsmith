"""Render state, for correct resumption.

The predecessor decided a clip was done if its output file existed. That made
editing the config a silent no-op: change the audio profile, re-run, and the
old renders stayed. Its own troubleshooting notes described this as a footgun.

Here a clip is done only if the output exists *and* its fingerprint matches —
input identity, the config that actually affects rendering, and the manifest
entry. Change any of them and the clip re-renders.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

STATE_FILENAME = "state.json"

# Config sections whose values change the rendered result. `io.output_dir` and
# job counts are excluded: moving the output or using more workers should not
# invalidate work.
_RELEVANT = ("look", "logo", "slate", "audio", "video", "encode", "subtitles", "marking")
_IGNORED_KEYS = {("encode", "jobs")}


def _relevant_config(cfg: dict[str, Any]) -> dict[str, Any]:
    subset: dict[str, Any] = {}
    for section in _RELEVANT:
        values = dict(cfg.get(section, {}))
        for ignored_section, ignored_key in _IGNORED_KEYS:
            if section == ignored_section:
                values.pop(ignored_key, None)
        subset[section] = values
    subset["io"] = {"output_name_template": cfg["io"]["output_name_template"]}
    return subset


def _file_identity(path: str) -> list[Any]:
    try:
        stat = os.stat(path)
    except OSError:
        return [path, None, None]
    return [os.path.basename(path), stat.st_size, round(stat.st_mtime, 3)]


def fingerprint(cfg: dict[str, Any], clip: Any, target: Any) -> str:
    """Stable hash of everything that determines this clip's output."""
    payload = {
        "config": _relevant_config(cfg),
        "target": {"width": target.width, "height": target.height, "fps": target.fps},
        "clip": {
            "index": clip.index,
            "title": clip.title,
            "primary": clip.primary,
            "secondary": clip.secondary,
            "description": clip.description,
            "tags": list(clip.tags),
            "slug": clip.resolved_slug(),
        },
        "inputs": [_file_identity(path) for path in clip.sources()],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


class State:
    """Fingerprints of completed renders, persisted in the work directory."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._data: dict[str, str] = {}
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    self._data = {k: str(v) for k, v in loaded.items()}
            except (OSError, json.JSONDecodeError):
                # A corrupt state file must not block a render; the worst case
                # is redoing work that was already done.
                self._data = {}

    def is_current(self, output_path: str, digest: str) -> bool:
        if not os.path.isfile(output_path):
            return False
        return self._data.get(os.path.basename(output_path)) == digest

    def record(self, output_path: str, digest: str) -> None:
        self._data[os.path.basename(output_path)] = digest

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2, sort_keys=True)
            handle.write("\n")

    def forget(self, output_path: str) -> None:
        self._data.pop(os.path.basename(output_path), None)
