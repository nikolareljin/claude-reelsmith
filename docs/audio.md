# Audio and loudness

The canonical reference, including symptoms and fixes, is
[`skills/reelsmith/references/audio.md`](../skills/reelsmith/references/audio.md).
This page is the human-facing version.

## Targets

| Profile | Target | Use for |
|---|---|---|
| `music` | -13 LUFS | Live acoustic music recorded at a distance. **Default** |
| `standard` | -14 LUFS | Mixed material |
| `web` | -14 LUFS | YouTube and similar |
| `speech` | -16 LUFS | Interviews, lectures, talking heads |
| `gentle` | -16 LUFS | Already-good recordings; preserves dynamics |
| `broadcast` | -23 LUFS | EBU R128 delivery |

Lower numbers are quieter. -23 LUFS sounds dramatically quieter than -13 and is
correct only when a broadcaster requires it.

```yaml
audio:
  profile: speech
```

## What each profile actually does

Four stages, in order:

1. **High-pass** — removes rumble, handling noise, air conditioning.
2. **Level** — compression and `dynaudnorm` lift quiet passages without
   crushing loud ones. This is the part that makes a distant recording usable.
3. **Normalise** — `loudnorm` lands the clip on its target loudness.
4. **Limit** — `alimiter` catches inter-sample peaks so nothing clips.

Raising a quiet recording is not a volume slider. Live music has a huge dynamic
range: loud passages near clipping, quiet ones near the noise floor. Turning
everything up distorts the peaks. Turning up only the quiet parts is the goal,
and it is what stage 2 does.

## Two-pass normalisation

On by default.

Run once, `loudnorm` works in a dynamic mode that only approaches its target.
Run it twice — measuring first, feeding the measurements back — and it lands on
target and stays linear. `reelsmith analyze` already reads every file, so the
measurement pass is effectively free.

Verify the result:

```bash
ffmpeg -i out/01_clip.mp4 -af ebur128=framelog=quiet -f null -
```

Look for `Integrated loudness / I:` — it should be within about 1 LU of the
target.

Silence is guarded: a clip measuring at or below -70 LUFS is left alone rather
than amplified, because normalising silence amplifies only noise.

Disable if you need it:

```yaml
audio:
  two_pass: false
```

## Overrides

Keep a profile's shaping, change its target:

```yaml
audio:
  profile: music
  target_lufs: -16.0
```

Supply a chain outright — this disables two-pass, since there is nothing
meaningful to measure:

```yaml
audio:
  profile: custom
  chain: "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95"
```

## Reading the analysis

Every clip in `analysis.json` carries a verdict:

```json
"audio": {
  "measured_lufs": -31.4,
  "target_lufs": -13.0,
  "needs_gain_db": 18.4,
  "verdict": "too quiet"
}
```

`needs_gain_db` above roughly 20 means a very quiet source. It will be lifted,
but so will its noise floor.

`"verdict": "silent"` means no usable audio. A clip with no audio track at all
gets a generated silent track so it stays in the batch, correctly branded and
titled, rather than failing the render.

## Symptoms

| Symptom | Cause | Fix |
|---|---|---|
| Pumping, breathing | Levelling too aggressive | `music` → `standard` → `gentle` |
| Still quiet | Source recorded too low | Check `verdict`; normalisation cannot fix capture level |
| Distorted | Source is clipped | Not recoverable downstream |
| One clip much louder | `two_pass` off | Turn it on |
