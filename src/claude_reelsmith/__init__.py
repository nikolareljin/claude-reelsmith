"""claude-reelsmith — batch video finishing for Claude Code.

The package is deliberately split in two halves:

* Deterministic media work (probe, analyse, render) lives here and never calls
  a model or a network service.
* Judgement (what is this clip, what should it be called) is supplied by an
  agent through ``manifest.json``.

That seam is what keeps the tool credential-free and portable across agents.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
