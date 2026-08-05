<div align="center">

# claude-reelsmith

**Point Claude at a folder of video. Get back finished, branded, correctly-levelled files.**

[![Release](https://img.shields.io/github/v/tag/nikolareljin/claude-reelsmith?color=F97316&label=release&sort=semver)](https://github.com/nikolareljin/claude-reelsmith/tags)
[![Python](https://img.shields.io/badge/python-3.10%2B-F97316)](https://www.python.org/)
[![CI](https://github.com/nikolareljin/claude-reelsmith/actions/workflows/ci.yml/badge.svg)](https://github.com/nikolareljin/claude-reelsmith/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-F97316)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-github%20pages-F97316)](https://nikolareljin.github.io/claude-reelsmith/)

</div>

Raw footage from a phone or a handycam is quiet, shaky, unlabelled and named
`IMG_4471.MOV`. Making it presentable means normalising the audio, steadying the
picture, adding a logo and a caption, and giving every file a name that means
something — for every clip, one at a time.

reelsmith does the mechanical half. Claude does the part that needs judgement:
it watches sampled frames, reads the transcript, and works out what each clip
actually *is* before naming it.

---

## What is included

| Component | What it does |
|---|---|
| `/claude-reelsmith:nr-reelsmith` command | Entry point. Runs the whole workflow |
| `reelsmith` skill | The workflow itself, plus reference material Claude loads as needed |
| `reelsmith` CLI | All deterministic media work: probe, analyse, transcribe, render |

**No API keys.** Claude's vision and language work happen inside your existing
Claude Code session. Transcription runs locally through Whisper. Nothing is
uploaded anywhere, and there is no credential to configure or leak.

---

## What it does to your video

- **Audio** — high-pass, level, then two-pass `loudnorm` onto a defined
  loudness. Quiet clips come back at a usable level; already-loud clips are not
  crushed. Six targets from -23 LUFS (broadcast) to -13 LUFS (live music).
- **Picture** — two-pass stabilization, and mixed input reconciled onto one
  canvas. Clips are scaled and padded, never cropped.
- **Branding** — logo bug from SVG or PNG, any corner, sized proportionally to
  the frame.
- **Captions** — news-style lower third with the name and the work, faded in and
  out. Geometry is computed from the frame, so 1080p, 4K and vertical all work.
- **Marking** — meaningful filenames, title/artist/date written into the
  container, `.srt` sidecars, and chapter markers for long continuous takes.
- **Speed** — hardware encoding when your machine has it (NVENC, Quick Sync,
  VAAPI, VideoToolbox), several clips at once.

---

## Install as a Claude Code plugin

**Step 1** — add the marketplace:

```
/plugin marketplace add nikolareljin/claude-plugins
```

**Step 2** — install the plugin:

```
/plugin install claude-reelsmith@nikolareljin-plugins
```

Restart Claude Code or run `/reload-plugins`, then verify the plugin appears in `/plugin`.

**Step 3** — install the CLI it drives:

```bash
pipx install git+https://github.com/nikolareljin/claude-reelsmith
```

<sub>No pipx? `python3 -m pip install --user git+https://github.com/nikolareljin/claude-reelsmith`</sub>

**Step 4** — check your machine can do the work:

```bash
reelsmith doctor
```

Every row should be `✓`. Any that is not prints the exact command that fixes it.

### Optional extras

```bash
pipx inject claude-reelsmith 'claude-reelsmith[transcribe]'   # local Whisper
pipx inject claude-reelsmith 'claude-reelsmith[svg]'          # SVG logos without Inkscape
```

You also need **ffmpeg** on your PATH — `sudo apt install ffmpeg`,
`brew install ffmpeg`, or `winget install Gyan.FFmpeg`.

---

## Quick start

In Claude Code:

```
/claude-reelsmith:nr-reelsmith
```

Claude asks where the videos are, where output should go, whether you have a
logo, and which look you want. Then it analyses every clip, shows you a table of
what it proposes to call each one, renders **one short sample** so you can check
the look, and waits for your approval before starting the batch.

```
Analyzed 24 files (2h 41m total)

  #  file            proposed title             fix
  1  IMG_4471.MOV    Bach — Partita No. 2       +18.4 dB, stabilize
  2  IMG_4472.MOV    Vivaldi — Spring           +3.1 dB, stabilize
  3  IMG_4470.MOV    (excluded: camera test)    —
  ...

Sample rendered: out/_preview/sample_01.mp4  (20s)

Proceed with all 23?  [yes / edit titles / cancel]
```

Settings are saved to `reelsmith.yaml`, so next time `/claude-reelsmith:nr-reelsmith` is one
keypress.

### Without Claude

The CLI is usable on its own. Titles come from filenames rather than
understanding, but everything else is identical:

```bash
reelsmith init --input ~/Videos/recital --output ~/Videos/out --preset news
reelsmith analyze --lite
reelsmith draft
$EDITOR _work/manifest.json
reelsmith plan
reelsmith preview
reelsmith render
```

---

## Commands

| Command | What it does |
|---|---|
| `reelsmith doctor` | Check ffmpeg, filters, fonts, encoders. Start here |
| `reelsmith init` | Write a `reelsmith.yaml` |
| `reelsmith analyze` | Probe, sample frames, measure loudness, transcribe → `analysis.json` |
| `reelsmith draft` | Turn that into a starting `manifest.json` |
| `reelsmith plan` | Show what a render would produce |
| `reelsmith preview` | Render one short sample |
| `reelsmith render` | Do the work |
| `reelsmith profiles` | List looks and audio targets |
| `reelsmith clean` | Remove intermediates |

---

## Output

```
reelsmith-out/
├── 01_anna_petrova_bach.mp4        branded, captioned, levelled
├── 01_anna_petrova_bach.srt        subtitle sidecar
├── 01_anna_petrova_bach.chapters.txt
├── 02_marco_ruiz_vivaldi.mp4
├── metadata.json                   titles, descriptions, tags
└── _preview/
    └── sample_01.mp4
```

Source footage is never modified. reelsmith only ever reads its input.

---

## How it fits together

```
reelsmith analyze  ──▶  analysis.json  ──▶  Claude reads it, and looks
                       + sampled frames      at the frames
                                                    │
                                                    ▼
reelsmith render  ◀──  manifest.json  ◀──  titles, captions, tags
```

`analysis.json` holds facts. `manifest.json` holds judgement. Keeping them
separate is what makes the tool honest about which is which — and what lets any
agent drive it. See [docs/porting-to-other-agents.md](docs/porting-to-other-agents.md).

---

## Troubleshooting

### `reelsmith: command not found` after installing the plugin

The plugin and the CLI install separately. Run step 3 above.

### Captions run off the edge of the frame

The text is too long, not the resolution wrong. Caption geometry is proportional
to the frame. Shorten `primary` and `secondary` in the manifest.

### Output is letterboxed

Expected when input shapes are mixed. Clips are padded rather than cropped so
nothing you shot is discarded. Force a shape with `video.target_height`.

### Nothing re-renders after I changed the config

It should — output is fingerprinted against the config and the manifest. If it
genuinely does not, that is a bug; `reelsmith render --force` works around it.

More in [docs/troubleshooting.md](docs/troubleshooting.md).

---

## FAQ

### Does anything leave my machine?

No. Transcription runs locally. Claude's reasoning happens in your Claude Code
session over footage you explicitly point it at. There is no telemetry, no
upload, and no API key.

### Does it work on things that are not concerts?

Yes. The `music` audio profile and the `concert` look come from a classical
recital, but nothing else assumes one. Conference talks, sports, interviews and
family video all work — pick `speech` and `news`.

### Will it re-encode footage that is already fine?

Yes; every clip is re-encoded because captions and branding are burned in. Use
`look.preset: minimal` and `video.stabilize: false` for the lightest touch.

### Can it handle 4K, or vertical phone video?

Both. Caption and logo geometry is derived from the frame, and portrait video is
sized to its narrow axis so text stays proportionate.

---

## Configuration

Everything lives in `reelsmith.yaml`. See [docs/configuration.md](docs/configuration.md).

## Documentation

- [Configuration](docs/configuration.md) — every option
- [Looks and presets](docs/presets.md)
- [Audio and loudness](docs/audio.md)
- [Architecture](docs/architecture.md) — how the pieces fit
- [Porting to other agents](docs/porting-to-other-agents.md)
- [Developer guide](docs/developer-guide.md)
- [Troubleshooting](docs/troubleshooting.md)

## Documentation site

<https://nikolareljin.github.io/claude-reelsmith/>

---

## Author

Built and maintained by **Nikola Reljin**, software engineer.

- GitHub — <https://github.com/nikolareljin>
- LinkedIn — <https://www.linkedin.com/in/nikolareljin>

Also by the same author, in the same marketplace:
[claude-docsmith](https://nikolareljin.github.io/claude-docsmith/) (documentation) ·
[claude-reposec](https://nikolareljin.github.io/claude-reposec/) (security scanning).

Full list and background in [ABOUT.md](ABOUT.md).

## License

MIT — see [LICENSE](LICENSE).
