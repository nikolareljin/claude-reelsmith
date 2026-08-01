"""Thin, safe wrappers around ffmpeg and ffprobe.

Two rules hold everywhere in this package and are enforced here:

1. Commands are argument lists. ``shell=True`` is never used, so no user string
   can reach a shell interpreter.
2. Failures carry ffmpeg's own stderr. The predecessor tool raised a bare
   ``CalledProcessError`` that told the user nothing.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
from dataclasses import dataclass


class FFmpegNotFound(RuntimeError):
    """Raised when the ffmpeg or ffprobe binary is not on PATH."""


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg or ffprobe invocation exits non-zero."""

    def __init__(self, args: list[str], returncode: int, stderr: str) -> None:
        self.args_list = args
        self.returncode = returncode
        self.stderr = stderr
        tail = "\n".join(stderr.strip().splitlines()[-12:])
        super().__init__(
            f"{args[0]} exited {returncode}\n"
            f"  command: {' '.join(args)}\n"
            f"  stderr tail:\n{tail}"
        )


def require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise FFmpegNotFound(
            f"{binary} was not found on PATH. Install ffmpeg and try again "
            f"(Debian/Ubuntu: sudo apt install ffmpeg; macOS: brew install ffmpeg)."
        )
    return path


def run(args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run a command, capturing stderr so failures are explainable."""
    require(args[0])
    proc = subprocess.run(  # noqa: S603 - argument list, never a shell string
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise FFmpegError(args, proc.returncode, proc.stderr)
    return proc


def run_ffmpeg(args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run ffmpeg with the flags every invocation in this package wants."""
    return run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error", *args],
               timeout=timeout)


@dataclass(frozen=True)
class Capabilities:
    """What the installed ffmpeg can actually do."""

    version: str
    filters: frozenset[str]
    encoders: frozenset[str]

    def has_filter(self, name: str) -> bool:
        return name in self.filters

    def has_encoder(self, name: str) -> bool:
        return name in self.encoders

    @property
    def can_stabilize(self) -> bool:
        return self.has_filter("vidstabdetect") and self.has_filter("vidstabtransform")

    @property
    def can_caption(self) -> bool:
        return self.has_filter("drawtext")


def _parse_listing(text: str) -> frozenset[str]:
    """Pull names out of ``ffmpeg -filters`` / ``-encoders`` table output.

    Both tables use a flags column then the name in the second field. Header
    lines and the ``---`` separator are skipped by requiring a plausible name.
    """
    names: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        flags, name = parts[0], parts[1]
        # Flag columns are short and never contain a letter-only word boundary
        # like a real name; the separator row is all dashes.
        if set(flags) <= set("-") or len(flags) > 8:
            continue
        if name.replace("_", "").replace("-", "").isalnum():
            names.add(name)
    return frozenset(names)


@functools.lru_cache(maxsize=1)
def capabilities() -> Capabilities:
    """Probe ffmpeg once per process and cache the answer."""
    require("ffmpeg")
    version = subprocess.run(  # noqa: S603
        ["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True
    ).stdout.splitlines()
    version_line = version[0].split(" version ", 1)[-1].split()[0] if version else "unknown"

    filters = _parse_listing(
        subprocess.run(  # noqa: S603
            ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True
        ).stdout
    )
    encoders = _parse_listing(
        subprocess.run(  # noqa: S603
            ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
        ).stdout
    )
    return Capabilities(version=version_line, filters=filters, encoders=encoders)
