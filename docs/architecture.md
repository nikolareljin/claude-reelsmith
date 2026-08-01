# Architecture

## The central split

reelsmith divides cleanly in two, and almost every design decision follows from
where that line sits.

```
                    ┌──────────────────────────────────┐
                    │  DETERMINISTIC — the reelsmith   │
                    │  CLI. No model. No network.      │
                    │  No credentials.                 │
                    │                                  │
                    │  probe · sample frames · measure │
                    │  loudness · detect silence ·     │
                    │  transcribe · encode             │
                    └──────────────┬───────────────────┘
                                   │
                        analysis.json + frames/
                                   │
                    ┌──────────────▼───────────────────┐
                    │  JUDGEMENT — an agent.           │
                    │                                  │
                    │  What is this clip? What should  │
                    │  it be called? Is it worth       │
                    │  keeping at all?                 │
                    └──────────────┬───────────────────┘
                                   │
                            manifest.json
                                   │
                    ┌──────────────▼───────────────────┐
                    │  DETERMINISTIC — render          │
                    └──────────────────────────────────┘
```

Three consequences:

**No credentials exist.** The model half runs inside the user's existing agent
session. There is no API key to store, rotate or leak, and no code path that
could exfiltrate footage.

**Any agent can drive it.** The interface is two JSON files and a shell command.
See [porting-to-other-agents.md](porting-to-other-agents.md).

**The expensive half is testable.** Media processing is pure input-to-output and
is covered by tests that run real ffmpeg. Judgement is not tested here, because
it is not here.

---

## Modules

| Module | Responsibility |
|---|---|
| `cli` | Argument parsing, config resolution, command dispatch |
| `config` | `DEFAULTS`, deep merge, validation |
| `ff` | Subprocess wrappers, capability detection |
| `probe` | ffprobe → `MediaInfo`, including rotation metadata |
| `normalize` | Choose a common canvas; scale-and-pad filters |
| `analyze` | Orchestrate fact-gathering → `analysis.json` |
| `transcribe` | Local Whisper; SRT generation |
| `chapters` | Silence detection → chapter boundaries |
| `audio` | Named profiles; two-pass loudness normalisation |
| `caption` | Resolution-relative geometry; `drawtext` construction |
| `presets` | Look bundles |
| `fonts` | Cross-platform font discovery |
| `logo` | SVG/PNG preparation |
| `encode` | Encoder detection, verification, quality mapping |
| `slate` | Title and closing cards |
| `manifest` | The agent contract: schema, validation, slugs |
| `state` | Fingerprinting for correct resumption |
| `pipeline` | Filtergraph assembly and rendering |
| `jobs` | Bounded concurrency, progress, failure collection |
| `doctor` | Preflight checks |
| `notify` | Console output (stderr; stdout is for data) |

---

## Filter order

The order in `pipeline._video_chain` is not arbitrary.

1. **Stabilise.** `vidstabtransform` must see the same geometry that
   `vidstabdetect` measured, so it runs before any scaling.
2. **Normalise.** Scale and pad onto the common canvas, then fix SAR and fps.
3. **Burn in subtitles**, if enabled — after scaling, so they are sized to the
   final frame.
4. **Logo overlay.** Sized as a fraction of the output height.
5. **Captions.** Geometry computed against the final frame size.
6. **Hardware upload**, last. Software filters cannot draw on a hardware
   surface, so VAAPI's `format=nv12,hwupload` must terminate the chain.

Audio is a separate branch, joined at the map stage: pre-chain, `loudnorm`,
limiter.

---

## Design decisions worth knowing

### Geometry is computed, not configured

Caption sizes and positions derive from a scale reference — the frame's shorter
side — against a 1080 baseline. At 1920×1080 the arithmetic reproduces a
hand-tuned layout exactly; at 4K it doubles; portrait video is sized to its
narrow axis, which is the one that actually constrains a caption.

This replaced hardcoded pixel offsets that silently assumed 1080p.

### Text never enters the filter string

Captions reach `drawtext` through `textfile=` sidecars. A name containing an
apostrophe, comma, colon or accent would otherwise have to survive several
layers of ffmpeg escaping. Writing it to a file removes the problem rather than
managing it — and it means no user-supplied string is ever interpolated into a
command.

### Two-pass loudness

Single-pass `loudnorm` runs in a dynamic mode that only approaches its target.
Because `analyze` already reads every file, measuring costs almost nothing, and
`render` feeds those measurements back for a linear pass that lands on target.

A guard rejects measurements at or below -70 LUFS: normalising silence just
amplifies noise.

### Scale and pad, never crop

Cropping to fit silently discards picture the user shot. Letterboxing is
visible, honest, and reversible.

### Encoders are verified, not assumed

`ffmpeg -encoders` lists what was compiled in. A build with NVENC support on a
machine with no NVIDIA card still advertises `h264_nvenc` and fails at render
time. Each hardware candidate encodes three synthetic frames before being
selected.

### Fingerprinted resumption

A clip is done only if its output exists *and* the hash of (input identity,
render-affecting config, manifest entry) matches. Changing the audio profile
invalidates; changing the job count does not.

The predecessor keyed resumption on file existence alone, so editing the config
and re-running silently kept the old renders.

### Failures are collected, not raised

One unreadable file in a folder of fifty must not abandon the other forty-nine
after an hour of encoding. `jobs.run_batch` collects outcomes and reports them
together.

### Threads, not processes

Every worker spends its life waiting on an ffmpeg subprocess, so the GIL is not
the bottleneck and threads avoid pickling state across processes.

---

## Concurrency

`encode.jobs` defaults to half the cores. Hardware encoders have their own
limits — consumer NVENC allows a small number of concurrent sessions — so more
workers is not always faster. Stabilization detection is CPU-bound and scales
well; encoding may not.

---

## Where state lives

```
_work/
├── analysis.json        facts (expensive to regenerate)
├── manifest.json        judgement (expensive to regenerate)
├── state.json           render fingerprints
├── frames/              sampled JPEGs
├── trf/                 stabilization transform files
├── *.primary.txt        caption sidecars
└── *_merged.mp4         concatenated intermediates
```

`reelsmith clean` removes intermediates and keeps the first two.
`reelsmith clean --all` removes everything.
