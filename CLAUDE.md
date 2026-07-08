# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`D:\OKEEF` is both the OKEEF pipeline's source code **and** a live Open
Knowledge Format (OKF v0.1) / PARA-method personal knowledgebase, in the same
git repo but split into two top-level directories: `Knowledgebase\` (the
actual knowledge content — `Projects/`, `Areas/`, `Resources/`, `Archives/`,
`index.md`, `log.md`) and `App\` (everything else — the pipeline package
`App/src/okeef/`, `App/scripts/`, `App/tests/`, `App/config/`, both venvs
`App/.venv`/`App/.venv-webui`, and all runtime state: `App/_inbox`,
`App/_staging`, `App/_quarantine`, `App/logs`, `App/data`). `config.py`'s
`Config` has a matching three-way split: `repo_root` (the git top level,
`D:\OKEEF`), `app_root` (`App\`), and `bundle_root` (`Knowledgebase\`) — see
"Config precedence" below for which one each module actually uses. Don't
treat top-level `.md` files or the PARA folders as documentation to edit
freely — they are either hand-curated bundle metadata (`index.md`) or
auto-generated / user-authored knowledge content; see
`App/src/okeef/bundle_index.py` for what's safe to touch programmatically
vs. not.

Full technical documentation (architecture, module-by-module reference,
config, debugging history behind non-obvious fixes) lives in
`INITDOCS/OKEEF-Project-Documentation.md`. `README.md` is the user-facing
setup/day-2-ops guide. Read both before making non-trivial changes — this
file is intentionally a short pointer plus the essentials, not a duplicate.

## Commands

All pipeline commands run inside `App\.venv` (created by `setup.ps1`; there is
no global install). Note: the venv's `pip.exe`/`okeef.exe` launcher `.exe`s
have an absolute path to `python.exe` baked in at install time — if the venv
is ever moved again, reinstall with `python.exe -m pip install -e ...` (not
the `pip.exe` wrapper) once, which regenerates the launchers.

```powershell
# Install/reinstall the pipeline package + dev deps (editable)
App\.venv\Scripts\python.exe -m pip install -e "D:\OKEEF\App[dev]"

# Run the full test suite
App\.venv\Scripts\python.exe -m pytest App\tests -v

# Run a single test file / single test
App\.venv\Scripts\python.exe -m pytest App\tests\test_pipeline.py -v
App\.venv\Scripts\python.exe -m pytest App\tests\test_pipeline.py::test_process_file_commits_to_git -v

# Run one file through the pipeline manually
App\.venv\Scripts\okeef.exe process-file <path>

# Run the inbox watcher in the foreground (Ctrl+C to stop)
App\.venv\Scripts\okeef.exe watch

# Scan the PARA folders for hand-added files never run through the pipeline,
# and OKF-ify them in place (bucket/folder as filed by hand, never reclassified)
App\.venv\Scripts\okeef.exe scan-para

# Review-mode commands (only meaningful when .env has AUTO_COMMIT=false)
App\.venv\Scripts\okeef.exe list-staged
App\.venv\Scripts\okeef.exe approve <staging-id> [--approved-by "Name"]

# Bulk re-sync PARA content into Open WebUI's Knowledge collection
App\.venv\Scripts\okeef.exe resync
```

`App\scripts\Start-Service.bat` and `App\scripts\Scan-ParaFolders.bat` are
double-clickable wrappers around `okeef watch` and `okeef scan-para`
respectively, for running either on demand without a terminal.

There is no configured linter/formatter/type-checker in `pyproject.toml` —
don't invent one; match existing style by reading nearby code.

`App/tests/test_classify.py` hits a **real** local Ollama server
(`qwen2.5:3b-instruct`) and auto-skips if `localhost:11434` isn't reachable —
if you need it to actually run, start Ollama first. Every other test uses an
autouse `stub_classification` fixture (`App/tests/conftest.py`) that fakes
`classify.classify()`, so the rest of the suite is fast and Ollama-independent.
`App/tests/conftest.py`'s `repo_root`/`bundle_root`/`app_root`/`config`
fixtures build a throwaway, `tmp_path`-isolated repo mirroring the real
`repo_root`/`Knowledgebase`/`App` split, **with a real git repo** at
`repo_root` — pipeline tests exercise the actual `git commit` path, not a mock.

Full environment setup (Git/Python/Ollama install, both venvs, model pulls,
headless Open WebUI first-run config, Scheduled Task registration) is
`setup.ps1`, idempotent and safe to re-run. It stays at the repo root
(`D:\OKEEF\setup.ps1`, not under `App\`) since it's the one command a fresh
clone's README tells you to run first. See `README.md` for the walkthrough.

## Architecture

### Pipeline flow

`extract.py` → `classify.py` → `okf_writer.py` → (`review_queue.py` OR direct
write) → `bundle_index.py` → `git_ops.py` → `openwebui_sync.py`, orchestrated
by `pipeline.py`. Read `pipeline.py` first — its module docstring and
`finalize()` explain the whole shape.

`para_scan.py` is a second, simpler entry point into the same chain, for
files a human drops directly into a PARA folder instead of `_inbox` (`okeef
scan-para`). It reuses `extract`/`classify`/`okf_writer.render()`/
`pipeline.finalize()` unchanged, but calls `okf_writer.write_in_place()`
instead of `write()` — placement is never reclassified there; whatever
bucket/folder the human already put the file in is where it stays. See its
module docstring for the "why."

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

`App\.venv` (pipeline, small deps) and `App\.venv-webui` (Open WebUI, huge dep
tree — torch/transformers/chromadb/langchain) are kept separate to avoid
dependency conflicts, not for any deployment reason. Both live inside `App\`
and are gitignored — a sibling of `Knowledgebase\`, not inside it, precisely
so they can never again end up inside the PARA content tree.
`openwebui_sync.py`'s `resync_all()` still deliberately iterates only the
four PARA folders under `bundle_root` rather than `rglob()`-ing the whole
repo: `.venv`/`.venv-webui` used to live inside `bundle_root` before the
`App`/`Knowledgebase` split, and a naive recursive glob pulled in thousands
of unrelated `.md` files from installed packages (this happened once; see the
Project Documentation §9.1 for the regression test, still enforced today by
`test_resync_all_does_not_walk_venv_or_bundle_root`).

### Auth to Open WebUI

`openwebui_sync.py` authenticates by signing in with the admin account's own
email/password (`WEBUI_ADMIN_EMAIL`/`WEBUI_ADMIN_PASSWORD`) to get a session
JWT, **not** a generated API key — API keys were found not to reliably
survive an Open WebUI restart on the installed version. Don't reintroduce an
API-key-based auth path without re-verifying that bug is actually fixed
upstream first.

### Windows-specific pieces

`pythonw.exe` (no console window) and Task Scheduler
(`App\scripts\register-tasks.ps1`) are Windows-only, as are the `.bat`
launchers (`App\scripts\Start-Service.bat`, `App\scripts\Scan-ParaFolders.bat`);
the pipeline package itself (`App/src/okeef/`) is pure Python/`pathlib` and
portable. See `README.md`'s Cross-platform notes if porting the automation
elsewhere.
