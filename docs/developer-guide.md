# Developer guide

## Setup

```bash
git clone https://github.com/nikolareljin/claude-reelsmith
cd claude-reelsmith
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

You need `ffmpeg` and `ffprobe` on PATH. The test suite generates its own media
fixtures with them.

## Validation

```bash
ruff check src tests
pytest
python -m compileall src
```

The full suite runs in well under a minute. Render tests encode real video —
about 20 short clips — and skip automatically when ffmpeg is absent.

Validate the plugin itself:

```bash
claude plugin validate .
claude --plugin-dir .        # load it in a session
```

## Layout

```
.claude-plugin/plugin.json   plugin manifest
commands/nr-reelsmith.md     slash command
skills/reelsmith/            skill, references, templates
src/claude_reelsmith/        the CLI
  resources/reelsmith/       byte-identical copy of skills/, shipped in the wheel
tests/                       pytest
site/                        GitHub Pages source
docs/                        prose documentation
```

### The resources mirror

`skills/reelsmith/` is what Claude Code loads from a plugin checkout.
`src/claude_reelsmith/resources/reelsmith/` is the same content shipped inside
the wheel, so a pip-only install still carries the workflow documentation.

They must stay identical. `tests/test_resources.py` fails on drift. After
editing anything under `skills/`:

```bash
rm -rf src/claude_reelsmith/resources/reelsmith
cp -r skills/reelsmith src/claude_reelsmith/resources/reelsmith
```

## Testing conventions

**Media fixtures are generated, not committed.** `tests/conftest.py` builds tiny
`testsrc` clips on demand. Two seconds of 320×240 is a few kilobytes and lets
the suite exercise the real filtergraph.

**ffmpeg is not mocked.** Mocking it would test the mock. The filtergraph is the
part most likely to break and the part least amenable to inspection.

**Geometry has a regression guard.** `tests/test_caption.py` asserts that a
1080p frame produces the exact pixel values of the hand-tuned layout this tool
inherited. Changing the maths is allowed; changing 1080p output is not, unless
that is the deliberate point of the change.

## Adding a look preset

1. Add a `Preset` to `presets.PRESETS`.
2. Add a render test in `tests/test_render.py` that exercises it.
3. Document it in `skills/reelsmith/references/presets.md` and `docs/presets.md`.
4. Re-sync the resources mirror.

Geometry stays in `caption.py`. A preset selects typography, timing and
treatment — it must never introduce a hardcoded pixel value, or it will break on
some resolution.

## Adding an audio profile

1. Add a `Profile` to `audio.PROFILES`, ending with a limiter.
2. Add cases to `tests/test_audio.py`.
3. Document the target in both audio references.

The existing `gentle`, `standard` and `music` chains are carried over from real
tuning. `tests/test_audio.py` pins their exact strings — do not change them
without a specific reason and a note in the changelog.

## Adding an encoder

1. Add an `Encoder` to `encode.CANDIDATES`, ranked by preference.
2. Add its quality mapping to `encode._QUALITY_MAP`.
3. Add mapping tests. `tests/test_encode.py` asserts every candidate has a
   mapping, so an omission fails immediately.

Hardware encoders are smoke-tested at startup by encoding three synthetic
frames. If your encoder needs setup beyond `init_args` and `filter_suffix`, the
`Encoder` dataclass will need extending.

## Releasing

Version lives in three places and they must agree — `tests/test_version.py`
enforces it:

- `.claude-plugin/plugin.json`
- `pyproject.toml`
- `src/claude_reelsmith/__init__.py`

Then:

1. Branch `release/X.Y.Z`.
2. Bump all three; update `CHANGELOG.md`.
3. `ruff check`, `pytest`, `claude plugin validate .`.
4. PR to `main`.

On merge, `.github/workflows/release-tag.yml` reads the branch name and pushes
an unprefixed semver tag (`0.2.0`, not `v0.2.0`).

Marketplace registration is a separate PR to
[`nikolareljin/claude-plugins`](https://github.com/nikolareljin/claude-plugins).

## Scope rules

- The CLI never calls a model, a network service, or anything needing a
  credential. That boundary is the security posture; do not cross it.
- No user string is ever interpolated into a shell command or an ffmpeg filter
  argument. Caption text goes through `textfile=` sidecars.
- New caption geometry must be resolution-relative.
- Prefer collecting failures over raising, wherever a batch is involved.
- Keep runtime dependencies minimal. Anything heavy belongs in an optional
  extra.
