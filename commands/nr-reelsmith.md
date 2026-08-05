---
description: Batch-finish a folder of video — enhance audio, stabilize, brand with a logo, and add news-style titles
argument-hint: "[input-dir] [--lite] [--preset news|concert|minimal] [--render-only]"
---

# `/claude-reelsmith:nr-reelsmith`

Turn a folder of raw video into finished, branded, correctly-levelled files.

Use the bundled `reelsmith` skill from this plugin. It is the source of truth
for the workflow; this command only sets the goal and the entry point.

## Goals

1. Understand what is actually in each clip before naming it.
2. Show the user a plan and one rendered sample **before** committing to a batch
   that may take hours.
3. Produce output that is loud enough, steady, branded and titled.

## Recommended flow

1. Run `reelsmith --version`, then `reelsmith doctor`. Stop on a required
   failure and relay the remedy.
2. Ask the user for input folder, output folder, logo, look and audio target —
   unless `$1` supplies the input folder or a `reelsmith.yaml` already exists.
3. `reelsmith analyze`, then read `_work/analysis.json` **and view the sampled
   frames** in `_work/frames/`.
4. Write `_work/manifest.json` with a title, two caption lines, a description
   and tags for every clip worth keeping.
5. `reelsmith plan` → show the table. `reelsmith preview` → give the user the
   sample path and wait for approval.
6. `reelsmith render` → report the summary and the output folder.

## Arguments

- `$1` — input directory. Skips the "where are the videos" question.
- `--lite` — no transcription and no frame sampling; titles come from filenames
  and metadata only. Faster, needs no model download, noticeably worse titles.
- `--preset` — `news`, `concert` or `minimal`. Ask if not given.
- `--render-only` — an approved manifest already exists; go straight to render.

## Authoritative workflow files

- `skills/reelsmith/SKILL.md`
- `skills/reelsmith/references/analysis.md`
- `skills/reelsmith/references/manifest.md`

## Never

- Never render a full batch without showing a plan and a preview first.
- Never invent a name, composer or work that the evidence does not support.
- Never write outside the user's chosen output folder, or modify source footage.
