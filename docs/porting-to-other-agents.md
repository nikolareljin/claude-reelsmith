# Porting reelsmith to other agents

reelsmith is primarily a Claude Code plugin. It does not have to be.

Only **two files** in this repository are Claude-specific:

- `commands/nr-reelsmith.md`
- `skills/reelsmith/SKILL.md` (and its `references/`)

Everything else — the entire `reelsmith` CLI — is agent-agnostic. It has no
model, no API client, and no knowledge that an agent exists. Porting to another
agent means writing that agent's equivalent of those two files. It does not mean
reimplementing anything.

---

## The contract

```
reelsmith analyze  ──▶  analysis.json  ──▶  ┌─────────────┐
                       + frames/*.jpg       │  YOUR AGENT │
                                            └─────────────┘
reelsmith render   ◀──  manifest.json  ◀────────┘
```

An agent needs exactly three capabilities:

1. **Run a shell command** — to invoke `reelsmith`.
2. **Read and write JSON files** — `analysis.json` in, `manifest.json` out.
3. **View images** — to look at the sampled frames.

Capability 3 is optional. Without it, fall back to `reelsmith analyze --lite`
and reason from transcript, filename and metadata alone. Titles get noticeably
worse; nothing breaks.

### What the agent must do

1. Verify `reelsmith --version` runs; print an install hint if not.
2. Run `reelsmith doctor`; stop on a required failure and relay the remedy.
3. Collect settings from the user and run `reelsmith init`.
4. Run `reelsmith analyze`.
5. Read `_work/analysis.json`. For each entry, combine `transcript.text`, the
   images at `frames[]`, `name`, and `media` into a title, two caption lines, a
   description and tags.
6. Write `_work/manifest.json` per [the schema](../skills/reelsmith/references/manifest.md).
7. Run `reelsmith plan`; show the table to the user.
8. Run `reelsmith preview`; **wait for approval**.
9. Run `reelsmith render`; report the result.

Step 8 is not optional. A batch can take hours, and a wrong logo position or
loudness target discovered afterwards means doing all of it again.

### Data shapes

`analysis.json`:

```jsonc
{
  "version": 1,
  "project": { "title": "…", "date": "…" },
  "target":  { "width": 1920, "height": 1080, "fps": 30.0 },
  "clips": [{
    "index": 1,
    "path": "/abs/path/IMG_4471.MOV",
    "name": "IMG_4471.MOV",
    "media": { "duration": 522.4, "display_width": 1920, "has_audio": true, … },
    "audio": { "measured_lufs": -31.4, "needs_gain_db": 18.4, "verdict": "too quiet" },
    "frames": ["/abs/_work/frames/IMG_4471_01.jpg", …],
    "transcript": { "language": "en", "text": "…", "segments": […] },
    "chapters": […],
    "warnings": []
  }]
}
```

`manifest.json` is documented in full in
[`skills/reelsmith/references/manifest.md`](../skills/reelsmith/references/manifest.md).
The judgement rules — how to weigh a transcript against a frame, caption length
budgets, when to refuse to guess — are in
[`skills/reelsmith/references/analysis.md`](../skills/reelsmith/references/analysis.md).
Both files are plain Markdown with nothing Claude-specific in them. Port them
verbatim.

---

## Per-agent mappings

### OpenAI Codex

Codex reads `AGENTS.md` from the repository root and supports prompt files.

```
AGENTS.md                  ← paste SKILL.md content here
.codex/prompts/reelsmith.md ← paste nr-reelsmith.md content here
```

Drop the YAML frontmatter from both; Codex does not use it. Keep the reference
files where they are and link to them by relative path — Codex can open them.

### Cursor

Cursor uses `.cursor/rules/*.mdc` with its own frontmatter:

```mdc
---
description: Batch-finish a folder of video with reelsmith
globs: ["**/reelsmith.yaml", "**/manifest.json"]
alwaysApply: false
---

<contents of SKILL.md, minus its frontmatter>
```

Use `@`-references (`@references/analysis.md`) instead of the Markdown table so
Cursor pulls the file in on demand.

### Gemini CLI

Gemini CLI reads `GEMINI.md` and supports TOML custom commands:

```toml
# .gemini/commands/reelsmith.toml
description = "Batch-finish a folder of video"
prompt = """
<contents of nr-reelsmith.md, minus its frontmatter>
"""
```

Put the skill body in `GEMINI.md` so it is always in context.

### OpenCode

Declare a command in `opencode.json` pointing at a Markdown file:

```json
{
  "command": {
    "reelsmith": {
      "template": "{file:./commands/nr-reelsmith.md}",
      "description": "Batch-finish a folder of video"
    }
  }
}
```

### Continue, Cline, Roo

All three read plain rules files (`.continuerules`, `.clinerules`). Concatenate
`SKILL.md` and `references/analysis.md` into one file — these agents generally
do not do on-demand reference loading, so progressive disclosure is lost and the
rules file gets long. Trim the troubleshooting reference to keep it manageable.

### Anything else — wrap it as MCP

For universal reach, expose the CLI as a Model Context Protocol server. Four
tools cover the whole workflow:

| Tool | Wraps | Returns |
|---|---|---|
| `reelsmith_doctor` | `reelsmith doctor --json` | Check results |
| `reelsmith_analyze` | `reelsmith analyze` | The analysis object, plus frame paths |
| `reelsmith_preview` | `reelsmith preview` | Path to the sample |
| `reelsmith_render` | `reelsmith render` | Summary and output paths |

Every subcommand that produces structured data already supports `--json`, so the
server is a thin shell-out with no parsing of human-readable output.

Two notes. Return frame paths, not encoded images — most MCP hosts read files
themselves, and inlining several JPEGs per clip is wasteful. And keep the
preview gate: a tool that renders a whole batch without confirmation is a
footgun regardless of which agent is holding it.

---

## What not to port

Do not reimplement the media pipeline. The ffmpeg filter chains encode real
tuning: two-pass `loudnorm` with a silence guard, resolution-relative caption
geometry, `textfile=` sidecars so punctuation cannot break the filtergraph, and
scale-and-pad that never crops. Reproducing them from scratch is a large amount
of subtle work and the CLI is already a `pip install` away on every platform
ffmpeg runs on.

If the pipeline is missing something your agent needs, an issue or a pull
request against this repository serves every agent at once.
