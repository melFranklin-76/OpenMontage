# OpenMontage

**MANDATORY: Read `AGENT_GUIDE.md` before responding to ANY user message.**

Do not act on the user's request until you have read AGENT_GUIDE.md.
It contains routing rules that determine your first action based on what the user asked.
Skipping it WILL cause you to take the wrong action.

There are no instructions in this file. All instructions are in AGENT_GUIDE.md.

## Cursor Cloud specific instructions

This is a Python 3.12 + Node 22 + FFmpeg codebase. The startup update script keeps
dependencies fresh (Python deps, `feedparser`, `piper-tts`, and `remotion-composer`
`node_modules`). Below are the non-obvious caveats for running/testing here.

### Services / what this repo is
There is no long-running server. "Running the app" means executing a production
pipeline (Python tools + Remotion/HyperFrames/FFmpeg render engines). Zero API keys
are required for the core path: Piper (local TTS), Remotion, HyperFrames, and FFmpeg
are all available out of the box. Add keys in `.env` to unlock cloud providers.

### `python` vs `python3` (gotcha)
Several repo shell scripts hardcode `python` (e.g. `scripts/creator_studio_local_pipeline.sh`,
`scripts/creator_studio_preflight.sh`), but the VM only ships `python3`. A
`python` -> `python3` shim is installed at `/usr/local/bin/python`. If a script ever
fails with `python: command not found`, recreate it with
`sudo ln -sf /usr/bin/python3 /usr/local/bin/python` (or invoke `python3` directly).
`make` targets already use `python3` and are unaffected.

### Python packages install to user site
`pip` installs to `~/.local/lib/python3.12/site-packages` (user install). This is
expected and importable via `python3`/`python`. `feedparser` is required by the
Creator Studio `fish` subsystem (imported at test-collection time) but is not in
`requirements-dev.txt`; the update script installs it.

### Lint / test / run / render commands
- Lint: `make lint` (py_compile of core tool modules).
- Tests (no API keys): `make test-contracts`; full Creator Studio suite:
  `python3 -m pytest tests/contracts/ tests/creator_studio/ -q`
  (~3 min; 562 passed / 6 skipped on a clean setup). Preflight wrapper:
  `scripts/creator_studio_preflight.sh`.
- Registry/preflight capability check: `make preflight` (or
  `registry.provider_menu_summary()` — see AGENT_GUIDE.md).
- Creator Studio end-to-end (no render/providers): `scripts/creator_studio_local_pipeline.sh`.
- Real video render (core deliverable, zero keys): `python render_demo.py <name>`
  (`--list` to see demos) or `make demo`. Output lands in
  `projects/demos/renders/<name>.mp4`.

### Render engine notes
- Remotion downloads a headless Chrome shell on the first render (one-time, then cached);
  the first `render_demo.py` run is slower because of this.
- HyperFrames runs via `npx hyperframes` (no in-repo package) and needs Node >= 22
  (present). `make hyperframes-doctor` validates the runtime.
