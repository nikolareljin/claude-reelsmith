# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-01

First release. A Claude Code plugin and a companion CLI that finish a folder of
raw video: enhanced audio, stabilized picture, logo, news-style captions, and
meaningful filenames.

### Added

- **`/nr-reelsmith` command and `reelsmith` skill.** The plugin ships markdown
  only; the CLI does the media work. Claude supplies the judgement — reading
  sampled frames and transcripts to decide what each clip is before naming it.
- **`reelsmith` CLI** with nine subcommands: `doctor`, `init`, `analyze`,
  `draft`, `plan`, `preview`, `render`, `profiles`, `clean`.
- **Six audio profiles** from -23 LUFS (EBU R128 broadcast) to -13 LUFS (live
  acoustic music), each doing high-pass, levelling, normalisation and limiting
  in that order.
- **Two-pass loudness normalisation.** `analyze` measures, `render` feeds the
  measurements back for a linear pass that lands on target. Single-pass
  `loudnorm` only approaches it.
- **Three look presets** — `news`, `concert`, `minimal` — plus optional title
  and closing cards.
- **Resolution-relative caption geometry.** Sizes and positions derive from the
  frame's shorter side against a 1080 baseline, so one config is correct at
  1080p, 4K and portrait.
- **Hardware encoding** with NVENC, Quick Sync, VAAPI, VideoToolbox and AMF,
  each verified by encoding synthetic frames before selection, falling back to
  libx264. Quality is expressed once on a CRF-like scale and mapped per encoder.
- **Parallel rendering** with a bounded worker pool, per-clip progress, and
  failure collection so one bad file cannot abandon a batch.
- **Local transcription** through faster-whisper, with `.srt` sidecars and
  optional burn-in. Optional dependency; the tool degrades to a metadata-only
  path without it.
- **Chapter detection** for long continuous takes, via silence analysis.
- **Marking**: logo bug, container metadata, meaningful filenames, chapter
  files.
- **`reelsmith doctor`** — preflight for ffmpeg, filters, fonts and encoders,
  with a platform-specific install command for anything missing.
- **GitHub Pages site** and a full `docs/` tree, including
  `docs/porting-to-other-agents.md` for driving the CLI from Codex, Cursor,
  Gemini CLI, OpenCode, Continue/Cline, or an MCP server.

### Carried over from the predecessor tool

The following were ported deliberately and are pinned by tests, because they
encode tuning arrived at against real recordings:

- The `gentle`, `standard` and `music` (formerly `loud-piano`) filter chains and
  their loudness targets.
- The caption fade expression.
- `textfile=` sidecars for caption text, so punctuation and accents cannot break
  the filtergraph.
- Two-pass `vidstab` stabilization, and transform-file reuse.
- Atomic `.part.mp4` → `os.replace()` output.
- The three-way SVG rasteriser fallback, with `realpath` for snap-confined
  Inkscape.

`loud-piano` is accepted as an alias for `music` so existing configs keep
working.

### Fixed relative to the predecessor

- **Editing the config now invalidates output.** Resumption was keyed on the
  output file merely existing, so changing the audio profile and re-running
  silently kept the old renders. Output is now fingerprinted against input
  identity, the render-affecting config, and the manifest entry.
- **Non-1080p footage renders correctly.** Caption offsets, font sizes and logo
  dimensions were hardcoded pixel values that assumed 1080p.
- **Clips with no audio track render** instead of failing the batch on an
  unmappable `[0:a]`; a silent track is generated.
- **Mixed resolutions and frame rates are reconciled** by scaling and padding —
  never cropping, which would silently discard picture.
- **The concat intermediate honours the configured encode settings** rather than
  hardcoding its own and becoming the quality bottleneck.
- **Missing fonts are detected before rendering**, with an install command,
  rather than surfacing as a raw ffmpeg error.
- **ffmpeg failures carry ffmpeg's stderr** instead of a bare
  `CalledProcessError`.
- **The generated `upload.sh` was dropped entirely.** It interpolated titles
  into a bash script escaping only `"`, so a name containing a backtick or `$`
  was shell-expanded.

### Security

- No API keys, anywhere. The model half runs in the user's existing agent
  session; transcription runs locally.
- Subprocesses are argument lists; `shell=True` is never used.
- User text reaches ffmpeg only through `textfile=` sidecars, never through
  filter-string interpolation.
- Output paths are confined to the configured output directory.
- `.gitignore` blocks media, `local/`, `_work/` and generated config, so real
  footage and real names cannot be committed.

[0.1.0]: https://github.com/nikolareljin/claude-reelsmith/releases/tag/0.1.0
