# The manifest

Read this when writing or repairing `_work/manifest.json`.

The manifest is the contract between what the CLI measured and what you
decided. It is the only place your judgement is recorded, and the only input
the renderer takes for titles.

## Shape

```json
{
  "version": 1,
  "generated_by": "claude via reelsmith skill",
  "project": {
    "title": "Spring Recital 2026",
    "date": "2026-06-14",
    "location": "St Mary's Hall"
  },
  "clips": [
    {
      "source": "/home/user/videos/IMG_4471.MOV",
      "index": 1,
      "include": true,
      "title": "Bach — Partita No. 2 in D minor",
      "primary": "Anna Petrova",
      "secondary": "Bach · Partita No. 2",
      "description": "Anna Petrova performs Bach's Partita No. 2 in D minor.",
      "tags": ["classical", "violin", "live"],
      "slug": "anna_petrova_bach",
      "merge_with": [],
      "notes": "Name confirmed from the spoken announcement at 0:04."
    }
  ]
}
```

## Fields

| Field | Required | Meaning |
|---|---|---|
| `source` | yes | Absolute path to the input file. Copy it exactly from `analysis.json` |
| `index` | no | Output ordering. Defaults to array position |
| `include` | no | `false` excludes the clip from rendering. Default `true` |
| `title` | no | Full name. Goes into the filename and container metadata |
| `primary` | no | Caption line one. ~34 characters |
| `secondary` | no | Caption line two. ~47 characters |
| `description` | no | One or two sentences for a description field |
| `tags` | no | 3-6 lowercase tags |
| `slug` | no | Filename slug. Derived from `title` when omitted |
| `merge_with` | no | Further sources concatenated after `source`, in order |
| `notes` | no | Your reasoning. Never rendered; read by humans |

Unknown fields are rejected rather than ignored, so a typo surfaces immediately
instead of silently doing nothing.

## Rules the CLI enforces

- Every clip needs a `source`.
- No two included clips may share both `index` and resolved `slug` — they would
  overwrite each other. Give one a distinct title, slug or index.
- `version` must be `1`.

## Working with it

Start from the draft:

```bash
reelsmith draft          # writes _work/manifest.json from filenames
```

Then edit it. Keep every entry from the draft; use `include: false` rather than
deleting, so the user can see and challenge your exclusions.

Check your work before rendering:

```bash
reelsmith plan           # validates and shows the table
reelsmith plan --json    # same, machine-readable
```

`plan` fails loudly on a malformed manifest. Always run it before `preview`.

## Editing after a render

The manifest is fingerprinted along with the config. Change a title and re-run
`reelsmith render`: only the affected clip re-renders, the rest are recognised
as current and skipped. There is no need to clean anything first, and no risk
of stale output surviving an edit.

To force everything: `reelsmith render --force`.
To redo one clip: `reelsmith render --only 3`.
