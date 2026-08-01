# Troubleshooting

Read this when a command fails. Run `reelsmith doctor` first — it catches most
of what follows and prints the exact remedy.

## Install and environment

**`reelsmith: command not found`**
```bash
pipx install git+https://github.com/nikolareljin/claude-reelsmith
```
If `pipx` is unavailable: `python3 -m pip install --user git+https://…`

**`ffmpeg was not found on PATH`**
Debian/Ubuntu `sudo apt install ffmpeg` · macOS `brew install ffmpeg` ·
Windows `winget install Gyan.FFmpeg` (or run under WSL).

**`No font found for 'sans-bold'`**
`sudo apt install fonts-dejavu-core`, or point at a file directly:
```yaml
look:
  font_primary: /path/to/Font-Bold.ttf
  font_secondary: /path/to/Font.ttf
```

**`This ffmpeg build has no drawtext filter`**
The build lacks freetype. Install a full ffmpeg, or use `look.preset: minimal`
to render without captions.

**libvidstab missing** — stabilization is skipped with a warning and everything
else proceeds. Set `video.stabilize: false` to silence it.

## Analysis

**`No video files matched`**
Check `io.input_dir` and `io.input_glob`. The glob defaults to `*` but only
recognised video extensions are considered. For nested folders set
`io.recursive: true`.

**`Transcription requested but faster-whisper is not installed`**
```bash
pip install 'claude-reelsmith[transcribe]'
```
Or accept the metadata-only path with `reelsmith analyze --lite`.

**Transcription is very slow** — the first run downloads a model. Use a smaller
one (`analysis.transcribe_model: tiny`) or limit the window to the announcement:
`analysis.transcribe_seconds: 30`.

**`No video stream in …`** — the file was matched by the glob but is not video.
Narrow `io.input_glob`.

## Rendering

**Captions run off the frame** — the text is too long. Shorten `primary` and
`secondary`; the budgets are in `analysis.md`. Geometry is proportional to the
frame, so this is always a text-length problem, never a resolution problem.

**The logo is in the wrong place, or covers the caption** — `bottom-*` positions
collide with the caption in the `news` and `concert` presets. Use a top corner.

**Output is letterboxed or pillarboxed** — expected when input shapes are mixed.
Clips are scaled and padded, never cropped, because cropping would silently
discard picture. Force a shape with `video.target_height`, or process portrait
and landscape footage as separate batches.

**A hardware encoder fails mid-batch** — force software encoding:
```bash
reelsmith render --encoder libx264
```
Encoders are smoke-tested at startup, but a driver can still fail under load.

**Rendering is very slow** — check which encoder `doctor` reports. Raise
`encode.jobs`, or lower quality (`encode.quality: 23`) for drafts. `preset:
ultrafast` trades file size for speed.

**`Refusing to write outside the output directory`** — `io.output_name_template`
contains a path traversal. Keep it to a filename.

## Resumption

**Nothing re-renders after I changed something** — it should. Output is
fingerprinted against input identity, the render-affecting config, and the
manifest entry. If a change genuinely is not picked up, that is a bug; work
around it with `reelsmith render --force`.

**Everything re-renders when I only changed one title** — check whether a config
value changed too. Job count, output directory and project metadata deliberately
do *not* invalidate; anything affecting pixels or audio does.

**An interrupted run left a mess** — `reelsmith clean` removes intermediates and
keeps `analysis.json` and `manifest.json`. `reelsmith clean --all` removes
everything. Partly-written outputs are never left behind: renders go to a
`.part.mp4` and are moved into place atomically.

## Getting more detail

Failures carry ffmpeg's own stderr tail. When reporting a problem, include the
full error, plus `reelsmith doctor --json` and `reelsmith plan --json`.
