# Look presets

Read this when offering a look, or when the user says the captions look wrong.

Run `reelsmith profiles` for the live list — this file explains the choice.

## news

Broadcast lower third. Bold name over a lighter subtitle, both on a translucent
bar, logo in a corner. Fades in over a second, holds fifteen, fades out.

The most legible option, because the bar guarantees contrast no matter what is
behind it. Pick this when the footage is unpredictable, or when the user says
"like the news".

## concert

Serif name, no bar, a soft drop shadow for legibility, longer hold (18s).
Restrained enough for a programme, and readable without covering the picture.

Pick this for recitals, ceremonies, lectures — anything where a heavy graphic
bar would look out of place. The shadow does the work the bar would otherwise
do, so it survives a bright background, but it is less bulletproof than `news`.

## minimal

Logo only, no text at all.

Pick this when the footage already carries its own titles, or when the user
wants nothing but enhancement and branding.

## Title cards and outros

Independent of the preset, and off by default. Enable in `reelsmith.yaml`:

```yaml
slate:
  intro_enabled: true
  intro_seconds: 2.5
  outro_enabled: true
  outro_text: "Thank you for watching"
```

The intro card uses `project.title` and `project.date`, with the logo centred
above. Cards are rendered with the same encoder settings as the main video and
joined without re-encoding.

## Adjusting a preset

The preset supplies defaults; explicit `look.*` values in the config win.

```yaml
look:
  preset: news
  show_seconds: 25       # hold much longer
  font_color: "#FFD700"
  box_color: "black@0.75"
```

Geometry is not directly configurable, and that is deliberate: sizes and
positions are computed from the frame so the same config works at 1080p, 4K and
portrait. To make captions uniformly bigger, the preset's `caption_scale` is the
intended lever.

## Logo placement

```yaml
logo:
  source: ~/brand/logo.svg
  position: top-right      # or top-left, bottom-right, bottom-left
  height_fraction: 0.1389  # of frame height — 150px at 1080p
  margin_fraction: 0.0509  # of frame height — 55px at 1080p
  opacity: 0.85
  crop: "W:H:X:Y"          # trim whitespace from the source file
```

SVG is rasterised once per run using Inkscape, rsvg-convert or CairoSVG,
whichever is present. `bottom-*` positions collide with the caption in the
`news` and `concert` presets — use a top corner unless the preset is `minimal`.
