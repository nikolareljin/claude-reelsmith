---
name: reelsmith
description: Batch-finish a folder of video — enhance and normalise audio, stabilize, brand with a logo, and add news-style titles and captions. Use when asked to process, polish, brand, caption, or clean up a directory of video files.
---

# Reelsmith Skill

Finish a folder of raw video into branded, captioned, correctly-levelled files.

Maintained by Nikola Reljin — https://github.com/nikolareljin

## Division of labour

`reelsmith` (the CLI) does everything deterministic: probing, sampling frames,
measuring loudness, transcribing, encoding. **You** do the one thing it cannot:
look at the evidence and decide what each clip *is*.

The seam is two files. `analysis.json` holds facts. `manifest.json` holds your
judgement. Never edit a video by hand; never let the CLI guess a title.

## Pre-flight

Run `reelsmith --version`. If the command is missing, tell the user:

```
pipx install git+https://github.com/nikolareljin/claude-reelsmith
```

Then run `reelsmith doctor`. Do not proceed if a required check fails — relay
the exact remedy line it prints.

## Workflow

1. **Gather settings.** Use AskUserQuestion for: input folder, output folder,
   logo file (offer "none"), look preset, and audio profile. Read
   `references/presets.md` and `references/audio.md` before offering choices so
   the descriptions are accurate.
2. **Write the config.** `reelsmith init --input … --output … --logo … --preset … --audio-profile …`
   Skip this if a `reelsmith.yaml` already exists and the user is happy with it.
3. **Analyse.** `reelsmith analyze`. Add `--lite` only if the user declined
   transcription and frame sampling.
4. **Decide.** Read `_work/analysis.json`. **Read the sampled frames in
   `_work/frames/` with the Read tool** — they are the strongest signal about
   what a clip contains. Follow `references/analysis.md` to turn transcript,
   frames, filename and metadata into a title, a two-line caption, a
   description and tags.
5. **Write the manifest.** Start from `reelsmith draft`, then edit
   `_work/manifest.json`. Set `include: false` on setup, test and dead clips
   rather than deleting the entry.
6. **Show the plan.** `reelsmith plan`. Present the table to the user.
7. **Preview.** `reelsmith preview`. Tell the user the sample path and ask them
   to approve, edit the titles, or cancel. **Never skip this gate** — a wrong
   logo position or loudness target otherwise costs a whole batch.
8. **Render.** `reelsmith render`. Report the summary, output folder, and
   anything that failed.

## Rules

- Never invent a performer name, composer, or work that is not supported by the
  transcript, the frames, or the filename. Say "unidentified" instead.
- Never write outside the user's chosen output folder.
- Never delete or overwrite source footage. The CLI only ever reads its input.
- Respect the caption character budgets in `references/analysis.md`; text that
  overflows the frame is worse than text that is terse.
- If transcription is unavailable, say so plainly rather than guessing harder.

## Reference files

Read the one you need, when you need it.

| File | Read it when |
|---|---|
| `references/analysis.md` | Turning analysis into titles and captions (step 4) |
| `references/presets.md` | Offering or explaining a look |
| `references/audio.md` | Choosing a loudness target, or audio sounds wrong |
| `references/manifest.md` | Writing or repairing `manifest.json` |
| `references/troubleshooting.md` | Anything fails |

`templates/manifest.example.json` is a filled-in manifest to copy the shape from.
