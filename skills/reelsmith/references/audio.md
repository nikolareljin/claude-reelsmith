# Audio profiles and loudness

Read this when choosing an audio target, or when the user says the sound is too
quiet, too loud, or pumping.

## What "make it louder" actually means

Raising the volume of a quiet recording is not a gain slider. Phone recordings
of live music have a huge dynamic range: the loud passages are near clipping
while the quiet ones sit near the noise floor. Turning everything up distorts
the peaks; turning up only the quiet parts is what you want.

Each profile therefore does four things in order:

1. **High-pass** — remove rumble, handling noise, air conditioning.
2. **Level** — compression and `dynaudnorm` bring quiet passages up without
   crushing loud ones.
3. **Normalise** — `loudnorm` lands the whole clip on a defined loudness.
4. **Limit** — `alimiter` catches inter-sample peaks so nothing clips.

## Two-pass normalisation

On by default, and worth understanding. Run once, `loudnorm` works in a
dynamic mode that only approaches the target. Run it twice — measuring first,
then feeding those measurements back — and it lands on the target and stays
linear.

`reelsmith analyze` already reads every file, so the measurement pass is
effectively free and the result is a genuinely accurate level.

Silence is guarded: a clip measuring at or below -70 LUFS is left alone rather
than amplified, because normalising silence just amplifies noise.

## Choosing a target

| Profile | Target | Use for |
|---|---|---|
| `music` | -13 LUFS | Live acoustic music recorded at a distance. Loud and forward. The default |
| `standard` | -14 LUFS | Mixed material when unsure |
| `web` | -14 LUFS | YouTube and similar streaming platforms |
| `speech` | -16 LUFS | Interviews, lectures, talking heads |
| `gentle` | -16 LUFS | Already-good recordings where dynamics matter |
| `broadcast` | -23 LUFS | EBU R128 delivery, when a broadcaster requires it |

Lower numbers are quieter. -23 LUFS sounds dramatically quieter than -13 and is
correct only when something downstream demands it.

`music` is tuned on real phone-recorded piano and is the reason this tool
exists. Prefer it for any live acoustic performance.

## Reading the analysis

Each clip in `analysis.json` carries a verdict:

```json
"audio": {
  "measured_lufs": -31.4,
  "target_lufs": -13.0,
  "needs_gain_db": 18.4,
  "verdict": "too quiet"
}
```

A `needs_gain_db` above roughly 20 means a very quiet source. It will be lifted,
but so will its noise floor — worth mentioning to the user rather than letting
them discover it in the output.

`"verdict": "silent"` means no usable audio at all.

## Overrides

Keep a profile's shaping but change its target:

```yaml
audio:
  profile: music
  target_lufs: -16.0
```

Or supply a chain outright, which disables two-pass because there is nothing
meaningful to measure:

```yaml
audio:
  profile: custom
  chain: "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95"
```

## Symptoms

**Pumping or breathing** — levelling is too aggressive. Move `music` → `standard`
→ `gentle`.

**Still too quiet** — check `verdict`. If it already says "close to target", the
source is quiet in a way normalisation cannot fix; the recording level was too
low at capture.

**Distorted** — the source is clipped. No downstream processing recovers a
clipped waveform.

**One clip much louder than the rest** — expected when `two_pass` is off. Turn
it on.
