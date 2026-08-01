# Privacy

## Nothing leaves your machine

reelsmith has no network client. It does not phone home, collect telemetry,
check for updates, or transmit footage, filenames, transcripts or metadata
anywhere.

- **Transcription** runs locally through faster-whisper. Audio is never
  uploaded. The only network access in the whole system is the one-time model
  download performed by faster-whisper itself, from Hugging Face, the first time
  you transcribe.
- **Rendering** is ffmpeg on your machine.
- **There are no credentials.** No API key, no token, no account. There is no
  code path that could authenticate to a remote service, because there is no
  remote service.

## What the agent sees

When you run `/nr-reelsmith` in Claude Code, Claude reads the files reelsmith
produced — `analysis.json`, and the sampled frames in `_work/frames/`. That
content travels to Anthropic under the terms of your existing Claude Code
subscription, exactly as any file you ask Claude to read does.

Concretely, Claude sees:

- Filenames, durations, resolutions and loudness measurements.
- Up to five sampled still frames per clip, at 640 pixels wide.
- The transcript, where transcription was enabled.
- Anything you put in `project.*` in your config.

Claude does **not** see the video files themselves. Frames are stills, not
footage.

If that is more than you want to share, `reelsmith analyze --lite` disables
transcription and frame sampling. Titles come from filenames alone; everything
else is unchanged. The CLI is also fully usable with no agent at all — see the
"Without Claude" section of the README.

Using a different agent changes who receives that data. See
[docs/porting-to-other-agents.md](docs/porting-to-other-agents.md).

## What is written to disk

Inside your working directory only:

```
_work/
├── analysis.json     measurements, transcripts, warnings
├── manifest.json     titles and captions
├── state.json        render fingerprints
├── frames/           sampled JPEGs
├── trf/              stabilization data
└── *.txt             caption text sidecars
```

Output goes to your configured output directory. Source footage is never
modified — reelsmith only reads its input.

## Footage of other people

Recordings of identifiable people — especially children, at recitals and school
events — are personal data in most jurisdictions. reelsmith processes whatever
you point it at and makes no judgement about consent. That responsibility is
yours.

Two practical notes:

- The repository's `.gitignore` blocks media files, `local/`, `_work/` and
  generated config, so footage and real names cannot be committed by accident.
- When reporting a bug, describe the input rather than attaching it. Resolution,
  frame rate and whether it has audio is almost always enough.

## Questions

<https://github.com/nikolareljin/claude-reelsmith/issues>
