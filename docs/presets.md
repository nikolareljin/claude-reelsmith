# Looks and presets

Run `reelsmith profiles` for the live list.

The canonical description of each look — including when to pick it and how to
adjust one — is
[`skills/reelsmith/references/presets.md`](../skills/reelsmith/references/presets.md),
which the agent loads when offering you a choice. This page covers the same
ground for a human reader and adds the parts an agent does not need.

## The three looks

| Preset | Caption | Best for |
|---|---|---|
| `news` | Bold name + subtitle on a translucent bar | Unpredictable footage; maximum legibility |
| `concert` | Serif name, no bar, soft shadow, longer hold | Recitals, ceremonies, lectures |
| `minimal` | None — logo only | Footage that already has titles |

Choose with `--preset` or in `reelsmith.yaml`:

```yaml
look:
  preset: concert
```

## Why geometry is not configurable

There is no `caption_y` or `font_size` option, and that is deliberate.

Sizes and positions are computed from the frame's shorter side against a 1080
baseline. One config therefore produces a proportionally identical result at
1080p, 4K and portrait. Exposing pixel offsets would let you set a value that
looks right on one resolution and is wrong on every other — which is precisely
the failure this design removed.

If captions are too large or too small overall, that is a preset-level change
(`caption_scale`), not a per-value one. Open an issue if the existing presets do
not cover your case.

## What you can change

```yaml
look:
  preset: news
  show_seconds: 25            # hold longer
  fade_seconds: 1.5
  font_color: "#FFD700"
  box_color: "black@0.75"
  font_primary: /usr/share/fonts/truetype/custom/Brand-Bold.ttf
  font_secondary: /usr/share/fonts/truetype/custom/Brand-Regular.ttf
```

Anything you set explicitly wins over the preset's own value.

Fonts are auto-discovered across Linux, macOS and Windows locations. Set an
absolute `.ttf` path to use a brand face.

## Logo

```yaml
logo:
  source: ~/brand/logo.svg
  position: top-right
  height_fraction: 0.1389
  margin_fraction: 0.0509
  opacity: 0.85
  crop: "800:300:0:100"
```

SVG is rasterised once per run via Inkscape, rsvg-convert or CairoSVG. Use
`crop` to trim whitespace baked into the source file — the four numbers are
width, height, x offset, y offset, applied after rasterisation.

**Avoid `bottom-left` and `bottom-right`** with the `news` and `concert`
presets: the logo will sit on top of the caption.

## Title cards

Off by default, and independent of the preset:

```yaml
slate:
  intro_enabled: true
  intro_seconds: 2.5
  outro_enabled: true
  outro_seconds: 2.0
  outro_text: "Thank you for watching"
  background: black
```

The intro uses `project.title` and `project.date` with the logo centred above.
Cards are rendered with the same encoder settings as the main video and joined
without re-encoding, so they cost seconds rather than minutes.
