# Contributing

Issues and pull requests are welcome:
<https://github.com/nikolareljin/claude-reelsmith/issues>

## Development setup

```bash
git clone https://github.com/nikolareljin/claude-reelsmith
cd claude-reelsmith
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

`ffmpeg` and `ffprobe` must be on PATH. The test suite generates its own media
fixtures with them.

## Validation

Run all of these before opening a pull request:

```bash
ruff check src tests
pytest
python -m compileall src
claude plugin validate .
```

Full details in [docs/developer-guide.md](docs/developer-guide.md).

## Scope rules

- **The CLI never calls a model, a network service, or anything requiring a
  credential.** That boundary is the security posture of this project. Features
  needing one belong in the skill, where the user's own agent session provides
  it.
- **No user string is interpolated into a shell command or an ffmpeg filter
  argument.** Caption text goes through `textfile=` sidecars. Subprocesses take
  argument lists.
- **Caption geometry must be resolution-relative.** A hardcoded pixel value is
  correct at exactly one resolution and wrong everywhere else.
- **Scale and pad; never crop.** Cropping silently discards picture the user
  shot.
- **Collect failures rather than raising, wherever a batch is involved.** One
  bad file must not abandon forty-nine good ones after an hour of encoding.
- **Keep runtime dependencies minimal.** Anything heavy goes in an optional
  extra so the base install stays small.

## The carried-over filter chains

The `gentle`, `standard` and `music` audio chains, and the caption fade
expression, are ported from a tool that was tuned against real recordings.
`tests/test_audio.py` and `tests/test_caption.py` pin their exact values.

Changing them is allowed, but it needs a specific reason and a changelog entry.
"It looks cleaner" is not one.

## The resources mirror

`skills/reelsmith/` and `src/claude_reelsmith/resources/reelsmith/` must stay
byte-identical — one is loaded from a plugin checkout, the other ships in the
wheel. `tests/test_resources.py` fails on drift. After editing `skills/`:

```bash
rm -rf src/claude_reelsmith/resources/reelsmith
cp -r skills/reelsmith src/claude_reelsmith/resources/reelsmith
```

## Pull requests

- Keep them focused. One concern per PR.
- Include the reasoning, not just the change.
- Add tests. Render behaviour needs a real render test; ffmpeg is not mocked
  here, because mocking it would test the mock.
- Update the relevant documentation, in both `docs/` and
  `skills/reelsmith/references/` where they overlap.
- Note anything that changes rendered output in `CHANGELOG.md`.

## Commit messages

Imperative and concise, optionally Conventional Commits (`feat:`, `fix:`,
`docs:`). Reference an issue where one exists.

## Reporting a bug

Include:

```bash
reelsmith --version
reelsmith doctor --json
reelsmith plan --json
```

plus the full error. ffmpeg's stderr tail is included in failures and is usually
the informative part.

Please do not attach footage containing people who have not agreed to it. A
description of the shape of the input — resolution, frame rate, whether it has
audio — is almost always enough.
