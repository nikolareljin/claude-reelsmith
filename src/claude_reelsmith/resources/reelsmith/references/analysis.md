# Turning analysis into titles and captions

Read this at step 4, when `analysis.json` exists and you are deciding what each
clip is.

## The evidence, ranked

For each clip you have up to four signals. They are not equally trustworthy.

| Signal | Where | Trust |
|---|---|---|
| Sampled frames | `clips[].frames` — **open these with Read** | Highest for *what is happening*: instruments, number of people, venue, on-screen text, banners, programme boards |
| Transcript | `clips[].transcript.text` | Highest for *names and titles* when someone announces them |
| Filename | `clips[].name` | Reliable only when it is clearly deliberate (`03_anna-petrova_bach.mp4`), worthless when it is camera-generated (`IMG_4471.MOV`, `C0023.MP4`) |
| Metadata | `clips[].media` | Good for ordering, duration and shape. Never for content |

**Look at the frames.** They are sampled specifically for you and cost little.
A frame showing four players with string instruments settles a question no
amount of filename staring will.

## Reading a transcript

Announcements usually sit in the first 20 seconds: *"Next, Anna Petrova will
play the Partita No. 2 in D minor by Bach."* That single sentence gives you
performer, work and composer.

Beware:
- Whisper mangles proper nouns, especially non-English names. "Dvorak" may
  arrive as "Devorjak". Correct it when you are confident; leave it when you
  are not.
- A transcript of applause and coughing is not content. If the text is under
  ~15 meaningful characters, treat the clip as having no transcript.
- Speech in the clip does not mean the speech is *about* the clip.

## Writing the fields

**`title`** — the full, correct name of the item. Used for the filename and the
container metadata. `Bach — Partita No. 2 in D minor`

**`primary`** — caption line one, the largest text on screen. Usually the
person. Keep it short; this is the line most likely to overflow.
`Anna Petrova`

**`secondary`** — caption line two. Usually the work, or the role.
`Bach · Partita No. 2 in D minor`

**`description`** — one or two sentences for a video description field. Fold in
project context (`analysis.project`) when it exists.

**`tags`** — 3-6 lowercase tags. Genre, instrument, event type.

**`include`** — `false` for setup shots, test recordings, accidental starts,
and clips that are only someone walking to the camera. Set the flag; do not
delete the entry, so the user can see what you excluded and disagree.

## Caption length

Text is drawn at a size proportional to the frame, so the budget depends on
resolution. `reelsmith plan` will not truncate for you — overflowing text runs
off the frame edge.

Safe budgets at a 16:9 frame:

| Line | Characters |
|---|---|
| `primary` | ~34 |
| `secondary` | ~47 |

Portrait video is sized to its narrow axis, so the same budgets apply. When a
work title will not fit, shorten it in the caption and keep the full form in
`title` and `description`:

- `primary`: `Anna Petrova`
- `secondary`: `Bach · Partita No. 2`
- `title`: `Bach — Partita No. 2 in D minor, BWV 1004`

## Ordering

`analysis.json` lists clips in filename order, which is capture order for
almost every camera and phone. Keep it unless the evidence contradicts it.

Set `index` to control output numbering. Two clips sharing an index and a slug
is an error the CLI will refuse.

## Merging

When one item was recorded as several consecutive clips (a card change, a
battery swap), put the first in `source` and the rest in `merge_with`, in
order. They become one output with one caption.

## When you do not know

Say so. `Unidentified performer` is a fine caption. A confidently wrong name
that reaches a published video is much worse than an honest gap, and the user
can fix a gap in seconds.

Put your reasoning in `notes` — it is ignored by the renderer and read by the
human checking your work.
