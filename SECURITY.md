# Security

## Reporting a vulnerability

Report privately through GitHub Security Advisories:

<https://github.com/nikolareljin/claude-reelsmith/security/advisories/new>

Or contact the maintainer, Nikola Reljin, via
[GitHub](https://github.com/nikolareljin). Please do not open a public issue for
a security problem.

Include the version (`reelsmith --version`), your platform, and steps to
reproduce. Expect an acknowledgement within a few days.

## Design posture

Several properties are structural rather than the result of hardening, which is
why they are worth stating.

**No credentials exist.** The CLI has no network client and no authentication
code. Judgement is supplied by the user's own agent session; transcription runs
locally. There is nothing to leak, rotate, or misconfigure.

**No shell.** Every subprocess is invoked with an argument list. `shell=True`
appears nowhere. No user-supplied string is ever concatenated into a command.

**No filter-string interpolation.** Caption text reaches `drawtext` through
`textfile=` sidecars, never inside the filter argument. This started as a way to
survive apostrophes and accents; it also means a crafted title cannot escape
into the filtergraph. File paths that must appear in a filter are escaped
explicitly.

**Path confinement.** Rendered output is resolved and checked against the
configured output directory. A `io.output_name_template` containing a path
traversal is refused rather than followed. A test covers this.

**Atomic writes.** Renders go to a `.part.mp4` and are moved into place with
`os.replace()`. An interrupted or killed run never leaves a truncated file that
a later run would mistake for finished work.

**Failure isolation.** A malformed or hostile input file fails its own clip and
is reported; it does not abort the batch or the process.

## Untrusted input

reelsmith parses media files with ffmpeg and ffprobe. Those are the largest
attack surface here and they are not part of this project — keep ffmpeg updated
through your package manager.

`manifest.json` is treated as untrusted: unknown fields are rejected, the schema
version is checked, and colliding output names are refused before any encoding
starts.

## Optional dependencies

- **faster-whisper** downloads a model from Hugging Face on first use. This is
  the only outbound network access in the system, and it happens inside that
  library. Skip it with `reelsmith analyze --lite`.
- **CairoSVG**, **Inkscape**, **rsvg-convert** rasterise SVG logos. They parse a
  file you supply. Only the SVG path uses them; a PNG logo does not.

## Supported versions

Only the latest release receives fixes. This is a young project; upgrade rather
than expecting backports.

## Scanning

The repository runs `gitleaks` on every push and pull request, and weekly on a
schedule.
