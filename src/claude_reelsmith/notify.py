"""Console output.

Colour is optional. When ``termcolor`` is absent every helper degrades to plain
text rather than failing, so the tool stays usable on a bare interpreter.
"""

from __future__ import annotations

import os
import sys

try:  # pragma: no cover - trivial import guard
    from termcolor import colored as _colored
except ImportError:  # pragma: no cover
    def _colored(text: str, *_args: object, **_kwargs: object) -> str:
        return text


def _use_colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def _emit(text: str, colour: str | None = None, *, attrs: list[str] | None = None) -> None:
    if colour and _use_colour():
        text = _colored(text, colour, attrs=attrs)
    print(text, file=sys.stderr, flush=True)


class Notify:
    """Namespaced output helpers. All output goes to stderr.

    stdout is reserved for machine-readable payloads (``--json``), so a caller
    can pipe structured output without stripping log lines first.
    """

    quiet = False

    @staticmethod
    def info(message: str) -> None:
        if not Notify.quiet:
            _emit(f"  {message}")

    @staticmethod
    def step(message: str) -> None:
        if not Notify.quiet:
            _emit(f"\n▸ {message}", "cyan", attrs=["bold"])

    @staticmethod
    def ok(message: str) -> None:
        if not Notify.quiet:
            _emit(f"  ✓ {message}", "green")

    @staticmethod
    def warn(message: str) -> None:
        _emit(f"  ! {message}", "yellow")

    @staticmethod
    def error(message: str) -> None:
        _emit(f"  ✗ {message}", "red", attrs=["bold"])

    @staticmethod
    def plain(message: str) -> None:
        if not Notify.quiet:
            _emit(message)
