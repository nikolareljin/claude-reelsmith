# Troubleshooting

Run this first — it catches most problems and prints the exact fix:

```bash
reelsmith doctor
```

## Install

**`reelsmith: command not found` after installing the plugin.**
The plugin and the CLI install separately. The plugin is markdown; the CLI does
the work.

```bash
pipx install git+https://github.com/nikolareljin/claude-reelsmith
```

**`ffmpeg was not found on PATH`**

| Platform | Command |
|---|---|
| Debian/Ubuntu | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | `winget install Gyan.FFmpeg`, or use WSL |

**`No font found for 'sans-bold'`**

```bash
sudo apt install fonts-dejavu-core
```

Or point at a file: `look.font_primary: /path/to/Font-Bold.ttf`.

**`This ffmpeg build has no drawtext filter`** — the build lacks freetype.
Install a full ffmpeg, or use `look.preset: minimal`.

**libvidstab missing** — stabilization is skipped with a warning; everything
else proceeds. Silence it with `video.stabilize: false`.

## Finding files

**`No video files matched`** — check `io.input_dir` and `io.input_glob`. Only
recognised video extensions are considered even when the glob is `*`. For
subdirectories set `io.recursive: true`.

**`No video stream in …`** — a non-video file matched the glob. Narrow it.

## Analysis

**`Transcription requested but faster-whisper is not installed`**

```bash
pipx inject claude-reelsmith 'claude-reelsmith[transcribe]'
```

Or skip it: `reelsmith analyze --lite`.

**Transcription is very slow.** The first run downloads a model. Then:

```yaml
analysis:
  transcribe_model: tiny    # much faster, less accurate
  transcribe_seconds: 30    # only the announcement at the top
```

**Names in the transcript are wrong.** Whisper mangles proper nouns, especially
non-English ones. Correct them in `manifest.json` — the transcript is evidence,
not output.

## Rendering

**Captions run off the frame.** The text is too long. Shorten `primary` and
`secondary`. Geometry is proportional to the frame, so this is never a
resolution problem.

**The logo covers the caption.** `bottom-*` positions collide with the caption
in `news` and `concert`. Use a top corner.

**Output is letterboxed or pillarboxed.** Expected when input shapes are mixed —
clips are padded rather than cropped so nothing you shot is lost. Force a shape
with `video.target_height`, or process portrait and landscape as separate
batches.

**A hardware encoder fails mid-batch.** Encoders are smoke-tested at startup,
but a driver can still fail under load:

```bash
reelsmith render --encoder libx264
```

**Rendering is very slow.** Check which encoder `doctor` reports. Then:

```bash
reelsmith render --jobs 8              # more workers
```
```yaml
encode:
  quality: 23        # lower quality, much faster
  preset: veryfast
video:
  stabilize: false   # stabilization is the expensive stage
```

**`Refusing to write outside the output directory`** —
`io.output_name_template` contains a path traversal. Keep it to a filename.

## Resumption

**Nothing re-renders after a change.** It should: output is fingerprinted
against input identity, render-affecting config, and the manifest entry. If a
real change is not picked up, that is a bug — please report it. Workaround:

```bash
reelsmith render --force
```

**Everything re-renders after one edit.** Something in the render-affecting
config changed too. Job count, output directory and project metadata
deliberately do not invalidate.

**Redo just one clip:** `reelsmith render --only 3`

**An interrupted run left a mess:**

```bash
reelsmith clean          # intermediates only; keeps analysis and manifest
reelsmith clean --all    # everything
```

Partly-written outputs are never left behind — renders go to a `.part.mp4` and
are moved into place atomically.

## Reporting a problem

Include the full error, plus:

```bash
reelsmith --version
reelsmith doctor --json
reelsmith plan --json
```

Errors carry ffmpeg's own stderr tail, which is usually the informative part.

<https://github.com/nikolareljin/claude-reelsmith/issues>
