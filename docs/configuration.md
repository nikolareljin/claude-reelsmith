# Configuration

Everything lives in `reelsmith.yaml`. Write a fully-commented one with:

```bash
reelsmith init --input ~/Videos/recital --output ~/Videos/out
```

reelsmith looks for `reelsmith.yaml` in the current directory, then walks up
through parent directories. Override with `-c path/to/file.yaml`.

Every value has a default, so a config only needs the keys you want to change.
**Unknown keys are an error, not a silent no-op** — a typo tells you immediately
instead of quietly doing nothing.

---

## `project`

Free-form context. Never required; used for container metadata, title cards, and
as background when an agent writes descriptions.

```yaml
project:
  title: "Spring Recital 2026"
  subtitle: "Junior division"
  date: "2026-06-14"
  location: "St Mary's Hall"
```

## `io`

```yaml
io:
  input_dir: "."                              # where the footage is
  input_glob: "*"                             # only video extensions are considered
  output_dir: "./reelsmith-out"
  work_dir: "./_work"                         # analysis, frames, intermediates
  output_name_template: "{index:02d}_{slug}.mp4"
  recursive: false                            # descend into subdirectories
```

`output_name_template` fields: `index`, `slug`, `title`, `stem` (the original
filename without extension). It must produce a filename — a template containing
a path traversal is refused.

## `analysis`

Which signals to gather.

```yaml
analysis:
  transcribe: true              # local Whisper
  frames: true                  # sample frames for an agent to look at
  metadata: true
  frame_count: 5
  transcribe_model: "small"     # tiny | base | small | medium | large-v3
  transcribe_language: null     # null auto-detects
  transcribe_seconds: 0         # 0 means the whole clip
  detect_chapters: true         # find item boundaries in long takes
  silence_threshold_db: -35.0
  silence_min_seconds: 2.0
```

Transcription needs `pip install 'claude-reelsmith[transcribe]'`. Larger models
are slower and more accurate; `small` is a good default. Set
`transcribe_seconds: 30` when you only need a spoken announcement at the top of
each clip — much faster than transcribing a full performance.

`reelsmith analyze --lite` turns `transcribe` and `frames` off for one run.

## `look`

```yaml
look:
  preset: "news"                # news | concert | minimal
  caption_enabled: true
  show_seconds: 15.0            # how long the caption stays up
  fade_seconds: 1.0
  font_primary: null            # null auto-discovers; or an absolute .ttf path
  font_secondary: null
  font_color: "white"
  box_color: "black@0.5"
```

Values you set explicitly win over the preset's own. Caption geometry is not
directly configurable — it is derived from the frame so one config works at
1080p, 4K and portrait. See [presets](presets.md).

## `logo`

```yaml
logo:
  source: "~/brand/logo.svg"    # SVG, PNG, WebP, TIFF or JPEG
  crop: null                    # "W:H:X:Y" to trim whitespace
  position: "top-right"         # top-left | top-right | bottom-left | bottom-right
  height_fraction: 0.1389       # of frame height — 150px at 1080p
  margin_fraction: 0.0509       # of frame height — 55px at 1080p
  opacity: 1.0
```

A missing logo file is a warning, not an error: the batch continues unbranded
rather than failing hours in over a mistyped path.

## `slate`

Title and closing cards. Off by default.

```yaml
slate:
  intro_enabled: false
  intro_seconds: 2.5
  outro_enabled: false
  outro_seconds: 2.0
  outro_text: null
  background: "black"
```

## `audio`

```yaml
audio:
  profile: "music"    # music | standard | speech | gentle | web | broadcast | custom
  chain: null         # ffmpeg filter chain, only when profile is "custom"
  two_pass: true      # measure, then normalise precisely
  target_lufs: null   # override the profile's loudness target
```

See [audio](audio.md). `loud-piano` is accepted as an alias for `music` so
configs from the predecessor tool keep working.

## `video`

```yaml
video:
  stabilize: true
  shakiness: 6        # 1-10, how much motion to expect
  accuracy: 12        # 1-15, detection accuracy; higher is slower
  smoothing: 24       # frames of smoothing
  zoom: 0             # percent zoom to hide edge artefacts
  unsharp: "5:5:0.8"
  target_height: null # null matches the most common input shape
  target_fps: null
```

Stabilization needs an ffmpeg built with libvidstab. Without it the stage is
skipped with a warning rather than failing.

## `encode`

```yaml
encode:
  encoder: "auto"     # auto | libx264 | h264_nvenc | h264_qsv | h264_vaapi | ...
  quality: 18         # CRF-like; lower is better. Mapped per encoder
  preset: "medium"
  pix_fmt: "yuv420p"
  acodec: "aac"
  abitrate: "192k"
  faststart: true     # move the index to the front, for web playback
  jobs: 0             # 0 means half your cores
```

`auto` verifies each hardware encoder by encoding a few frames before choosing
it — being compiled into ffmpeg is not the same as working on your machine.
`quality` is expressed once and translated per encoder, so the same number means
roughly the same thing on NVENC as on libx264.

## `subtitles`

```yaml
subtitles:
  sidecar: true       # write a .srt beside the output
  burn_in: false      # draw subtitles into the picture
```

Both need a transcript, so both need `analysis.transcribe: true`.

## `marking`

```yaml
marking:
  embed_metadata: true    # title/artist/date/tags into the container
  rename: true            # use output_name_template
  chapters_file: true     # write a chapter list for long takes
```

---

## Example: conference talks

```yaml
project:
  title: "DevConf 2026"
  date: "2026-09-12"

io:
  input_dir: "~/Videos/devconf/raw"
  output_dir: "~/Videos/devconf/final"

look:
  preset: news

logo:
  source: "~/brand/devconf.svg"
  position: top-right

audio:
  profile: speech       # -16 LUFS, tuned for voice

video:
  stabilize: false      # tripod footage does not need it

subtitles:
  sidecar: true
```

## Example: a recital, matching the original tool

```yaml
project:
  title: "Spring Recital 2026"
  date: "2026-06-14"

look:
  preset: concert

audio:
  profile: music        # -13 LUFS

video:
  stabilize: true

encode:
  quality: 18
  preset: medium
```
