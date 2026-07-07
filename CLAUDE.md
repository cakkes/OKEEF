# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`D:\OKEEF` is both the OKEEF pipeline's source code **and** a live Open
Knowledge Format (OKF v0.1) / PARA-method personal knowledgebase — the two
venvs (`.venv`, `.venv-webui`), the pipeline package (`src/okeef/`), and the
actual knowledge content (`Projects/`, `Areas/`, `Resources/`, `Archives/`,
`index.md`, `log.md`) all live in the same git repo. Don't treat top-level
`.md` files or the PARA folders as documentation to edit freely — they are
either hand-curated bundle metadata (`index.md`) or auto-generated /
user-authored knowledge content; see `src/okeef/bundle_index.py` for what's
safe to touch programmatically vs. not.

Full technical documentation (architecture, module-by-module reference,
config, debugging history behind non-obvious fixes) lives in
`INITDOCS/OKEEF-Project-Documentation.md`. `README.md` is the user-facing
setup/day-2-ops guide. Read both before making non-trivial changes — this
file is intentionally a short pointer plus the essentials, not a duplicate.

## Commands

All pipeline commands run inside `.venv` (created by `setup.ps1`; there is no
global install).

```powershell
# Install/reinstall the pipeline package + dev deps (editable)
.venv\Scripts\pip.exe install -e "D:\OKEEF[dev]"

# Run the full test suite
.venv\Scripts\python.exe -m pytest tests -v

# Run a single test file / single test
.venv\Scripts\python.exe -m pytest tests\test_pipeline.py -v
.venv\Scripts\python.exe -m pytest tests\test_pipeline.py::test_process_file_commits_to_git -v

# Run one file through the pipeline manually
.venv\Scripts\okeef.exe process-file <path>

# Run the inbox watcher in the foreground (Ctrl+C to stop)
.venv\Scripts\okeef.exe watch

# Review-mode commands (only meaningful when .env has AUTO_COMMIT=false)
.venv\Scripts\okeef.exe list-staged
.venv\Scripts\okeef.exe approve <staging-id> [--approved-by "Name"]

# Bulk re-sync PARA content into Open WebUI's Knowledge collection
.venv\Scripts\okeef.exe resync
```

There is no configured linter/formatter/type-checker in `pyproject.toml` —
don't invent one; match existing style by reading nearby code.

`tests/test_classify.py` hits a **real** local Ollama server
(`qwen2.5:3b-instruct`) and auto-skips if `localhost:11434` isn't reachable —
if you need it to actually run, start Ollama first. Every other test uses an
autouse `stub_classification` fixture (`tests/conftest.py`) that fakes
`classify.classify()`, so the rest of the suite is fast and Ollama-independent.
`tests/conftest.py`'s `bundle_root`/`config` fixtures build a throwaway,
`tmp_path`-isolated OKF/PARA skeleton **with a real git repo** — pipeline
tests exercise the actual `git commit` path, not a mock.

Full environment setup (Git/Python/Ollama install, both venvs, model pulls,
headless Open WebUI first-run config, Scheduled Task registration) is
`setup.ps1`, idempotent and safe to re-run. See `README.md` for the walkthrough.

## Architecture

### Pipeline flow

`extract.py` → `classify.py` → `okf_writer.py` → (`review_queue.py` OR direct
write) → `bundle_index.py` → `git_ops.py` → `openwebui_sync.py`, orchestrated
by `pipeline.py`. Read `pipeline.py` first — its module docstring and
`finalize()` explain the whole shape.

**The `finalize()` seam is the one architectural fact everything else hangs
off of**: `pipeline.finalize(written_paths, concept_path, classification,
config, commit: bool, extra_trailers=None)` is the single shared tail
(index-update → commit → Open WebUI sync) called by *both* the immediate
`AUTO_COMMIT=true` path (`process_file()`) and the review-mode `approve()`
path after a human has approved a staged draft. `commit` is passed explicitly
rather than read from `config.auto_commit` inside `finalize()`, specifically
so `approve()` can always commit regardless of the global default. Any change
to what happens "after a doc is ready to be filed" belongs in `finalize()`,
not duplicated in both callers.

### Config precedence

`config.py`'s `load_config()` merges `config/config.yaml` (shared, committed,
cross-machine defaults) with `.env` (machine-specific, gitignored) — `.env`
always wins where both define a value (e.g. `AUTO_COMMIT`). A few values
(`OPENWEBUI_KNOWLEDGE_ID`, `WEBUI_ADMIN_EMAIL`/`PASSWORD`) exist *only* in
`.env` because they're inherently per-machine (a generated UUID, real
credentials) and have no sensible shared default. `.env` is loaded with
`encoding="utf-8-sig"` deliberately — PowerShell 5.1's `Set-Content -Encoding
utf8` writes a BOM that otherwise silently breaks the *first* key in the
file (see `INITDOCS/OKEEF-Project-Documentation.md` §9.3 for the full story).

### The OKF document shape

Every filed concept doc has YAML frontmatter (`type` is the only OKF-required
field; this pipeline also always writes `title`, `description`, `tags`,
`timestamp`, `source_file`, `ingested_by`) plus a `# Summary` / `# Content` /
`# Source` body. `# Content` holds the *complete* extracted source text, not
a summary — intentional, for both human trust and RAG recall. Classification
metadata that's only needed for *filing* (`para_bucket`, `folder_slug`,
`confidence`) is deliberately **not** persisted in the final frontmatter —
see `okf_writer.py` vs. `review_queue.py` (which *does* stage
`_para_bucket`/`_folder_slug` as temporary, human-editable keys, stripped
before the final write).

### Two-venv split

`.venv` (pipeline, small deps) and `.venv-webui` (Open WebUI, huge dep tree —
torch/transformers/chromadb/langchain) are kept separate to avoid dependency
conflicts, not for any deployment reason. Both live inside the repo root and
are gitignored. `openwebui_sync.py`'s `resync_all()` deliberately iterates
only the four PARA folders, never `rglob()`s the bundle root — `.venv`/
`.venv-webui` living inside `D:\OKEEF` means a naive recursive glob would
pull in thousands of unrelated `.md` files from installed packages (this
happened once; see the Project Documentation §9.1 for the regression test).

### Auth to Open WebUI

`openwebui_sync.py` authenticates by signing in with the admin account's own
email/password (`WEBUI_ADMIN_EMAIL`/`WEBUI_ADMIN_PASSWORD`) to get a session
JWT, **not** a generated API key — API keys were found not to reliably
survive an Open WebUI restart on the installed version. Don't reintroduce an
API-key-based auth path without re-verifying that bug is actually fixed
upstream first.

### Windows-specific pieces

`pythonw.exe` (no console window) and Task Scheduler
(`scripts\register-tasks.ps1`) are Windows-only; the pipeline package itself
(`src/okeef/`) is pure Python/`pathlib` and portable. See `README.md`'s
Cross-platform notes if porting the automation elsewhere.
