# OKEEF — Project Documentation

A personal, local-first knowledgebase ("second brain") built on Google's Open
Knowledge Format (OKF v0.1) and organized with the PARA method. A local LLM
pipeline (Ollama) classifies and files dropped-in documents automatically; a
local RAG chat UI (Open WebUI) lets you query the knowledgebase in natural
language, grounded in your own notes with citations.

This document is the technical reference for how the system is built and why.
For day-to-day usage instructions, see `README.md` in the repo root — this
document goes deeper into architecture, rationale, and the debugging history
behind non-obvious design choices.

---

## 1. Background

**Open Knowledge Format (OKF v0.1)** is a Google-authored, minimally-opinionated
spec for representing knowledge as a portable "bundle": a directory tree of
markdown files ("concepts"), each with a small YAML frontmatter block. It
requires only one frontmatter field (`type`); everything else — folder
structure, taxonomy, additional metadata — is left to the implementer. Two
filenames are reserved: `index.md` (a no-frontmatter navigation page) and
`log.md` (a dated changelog). Consumers must tolerate unknown fields/types and
broken links. Spec: `https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`

**PARA** (Projects / Areas / Resources / Archives) is a personal-knowledge-
management method: Projects are active efforts with a deadline, Areas are
ongoing responsibilities with no end date, Resources are reference material,
Archives are inactive items from the other three.

OKEEF uses PARA as the top-level folder structure of an OKF bundle — OKF
doesn't prescribe folder names, so PARA fills that gap naturally.

## 2. Hardware/environment context

Built and tested on a Lenovo P14S Gen 2: NVIDIA T500 GPU (4GB VRAM — modest,
drives the choice of small local models), 40GB RAM, Windows 11. The design
assumes a personal laptop, not a server: models are chosen for low VRAM
footprint, and nothing is expected to run 24/7 except the lightweight watcher.

## 3. Architecture overview

```
                    ┌─────────────┐
   drop file  ───▶  │   _inbox\   │
                    └──────┬──────┘
                           │ watchdog (Observer, debounced)
                           ▼
                 ┌───────────────────┐
                 │  extract.py       │  .txt/.md/.pdf/.docx -> plain text
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │  classify.py      │  Ollama structured output
                 │  (qwen2.5:3b)     │  -> Classification (pydantic)
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │  okf_writer.py    │  renders OKF frontmatter + body
                 └─────────┬─────────┘
                           │
              AUTO_COMMIT=true │ AUTO_COMMIT=false
                           ▼             ▼
                  write to PARA    review_queue.py
                  folder now       stages to _staging/<id>/
                           │             │  (human edits draft.md,
                           │             │   runs `okeef approve <id>`)
                           ▼             ▼
                 ┌───────────────────┐
                 │  bundle_index.py  │  updates folder index.md + root log.md
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │  git_ops.py       │  git add + commit (atomic per file)
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │  openwebui_sync.py│  upload -> process -> attach to
                 └───────────────────┘  Knowledge collection (best-effort)
```

`pipeline.py` is the orchestrator tying every stage together. `finalize()` is
the key seam: it's the shared tail (index update -> commit -> sync) called
both by the immediate auto-commit path and by the review-mode `approve()`
path, so the two modes never diverge in what actually happens once a doc is
ready to be filed.

## 4. Repository layout

```
D:\OKEEF\
├── Knowledgebase\             bundle root -- the knowledge content itself
│   ├── index.md, log.md       hand-curated, only file allowed okf_version
│   │                          frontmatter; never auto-touched beyond log.md's
│   │                          dated entries
│   └── Projects\ Areas\ Resources\ Archives\
│                              PARA sections; each subfolder's index.md
│                              auto-regenerates between marker comments
├── App\                       the pipeline application + all runtime state
│   ├── _inbox\                watched folder; stays empty between runs
│   ├── _staging\               review-mode drafts (AUTO_COMMIT=false), gitignored
│   ├── _quarantine\            failed extractions/classifications + reason.txt
│   ├── logs\                  watcher.log, openwebui-*.log (gitignored)
│   ├── src\okeef\              the ingestion pipeline package (see §6)
│   ├── tests\                 pytest suite (19 tests as of this writing)
│   ├── config\config.yaml      shared, version-controlled config
│   ├── .env / .env.example     machine-specific config + credentials (gitignored)
│   ├── pyproject.toml          pipeline package definition + dependencies
│   ├── scripts\                register-tasks.ps1, start-openwebui.ps1,
│   │                          Start-Service.bat, Scan-ParaFolders.bat
│   ├── .venv\                  ingestion pipeline venv (gitignored)
│   ├── .venv-webui\             Open WebUI venv (gitignored)
│   └── data\openwebui\         Open WebUI's own state: sqlite DB + vector
│                                store (gitignored; regenerable via `okeef resync`
│                                except chat history itself)
└── setup.ps1                  idempotent bootstrap script (stays at the repo
                                root -- the one command a fresh clone runs first)
```

`Knowledgebase\` and `App\` used to be flattened together at the repo root;
they were split apart so PARA content isn't sitting alongside venvs/tests/
runtime state. `config.py`'s `Config` has a matching three-way split
(`repo_root`, `app_root`, `bundle_root`) -- see §10 for which modules use which.

Two Python virtual environments are used deliberately: the pipeline's
dependencies (pydantic, watchdog, PyMuPDF, ollama client, etc.) are small and
stable; Open WebUI's dependency tree is enormous (torch, transformers,
langchain, chromadb...). Keeping them separate avoids version conflicts and
keeps the pipeline's own footprint light.

## 5. The OKF document, concretely

Every concept document OKEEF writes looks like this:

```yaml
---
type: project-charter            # REQUIRED by spec; free string
title: Home Network Upgrade Project
description: A project to replace an aging router...
tags:
  - network-upgrade
  - router-replacement
timestamp: '2026-07-07T14:41:49Z'
source_file: Home Network Upgrade Project.txt
ingested_by: okeef-pipeline/0.1
---

# Summary

<LLM-generated 2-4 sentence summary>

# Content

<full extracted source text -- nothing is discarded>

# Source

Original file: `Home Network Upgrade Project.txt`
Ingested: 2026-07-07T14:41:49Z
```

Design choices here:
- **`# Content` keeps the full original text**, not just a summary — both for
  human trust (nothing silently lost) and because RAG recall benefits from
  having the complete text available for chunking, not just a condensed
  version.
- **Non-markdown originals** (PDF/DOCX) are kept as a sibling attachment,
  same basename (`recipe.md` + `recipe.original.pdf`), referenced via the
  custom `source_file` frontmatter key. OKF explicitly requires consumers to
  tolerate producer-defined custom keys, so this is spec-conformant.
- **`para_bucket`, `folder_slug`, `confidence`** (the LLM's classification
  metadata beyond what's needed for the final doc) are *not* persisted in the
  final frontmatter — they're consumed once during filing/logging and
  discarded, keeping the committed document's frontmatter clean and stable
  regardless of pipeline internals. (In review-mode staging, `_para_bucket`/
  `_folder_slug` *do* appear temporarily, as human-editable staging-only keys
  in `_staging/<id>/draft.md` — stripped before the final write.)

## 6. The pipeline, module by module

All in `App/src/okeef/`:

| Module | Responsibility |
|---|---|
| `config.py` | Loads `config/config.yaml` (shared) + `.env` (machine-specific) into a frozen `Config` dataclass. `.env` values win over `config.yaml` where both exist (e.g. `AUTO_COMMIT`). |
| `models.py` | `Classification` — the pydantic schema shared between the classifier and every downstream consumer: `para_bucket`, `okf_type`, `title`, `description`, `summary`, `tags`, `folder_slug`, `confidence`. |
| `extract.py` | Per-filetype text extraction: `.txt`/`.md` (UTF-8-sig, BOM-tolerant), `.pdf` (PyMuPDF), `.docx` (python-docx). Raises `ExtractionError` for empty/scanned/unsupported files, which the watcher turns into a quarantine. |
| `classify.py` | One Ollama structured-output call (`qwen2.5:3b-instruct`) per file. System prompt spells out PARA bucket definitions, a suggested (non-exhaustive) `okf_type` vocabulary, and formatting rules; `_sanitize()` is a safety net for cases where the model doesn't follow formatting instructions exactly. |
| `okf_writer.py` | `render()` turns extracted text + a `Classification` into an `OKFDoc` (frontmatter dict + body string). `write()` decides the final PARA path from `classification.para_bucket`/`folder_slug` (with collision-safe uniquing) and writes the file(s), deleting the source if it came from `_inbox`. `write_in_place()` is the `para_scan.py` variant: same collision-safe write, but the target folder is always `source_path.parent` (bucket/folder ignored) and the source is always deleted. Kept as separate functions from `render()` specifically so review-mode can render without committing to a final location. |
| `bundle_index.py` | Regenerates each folder's `index.md` auto-index section (between `<!-- OKEEF:AUTO-INDEX:START/END -->` markers) after a write, walking up from the concept's folder to (but not including) the bundle root — the root `index.md` is hand-curated and deliberately never auto-touched. Also appends a dated entry to root `log.md`. |
| `git_ops.py` | Thin `git add` + `git commit` wrapper, shelling out to `git.exe` (located via `shutil.which` or common install paths). |
| `review_queue.py` | Implements the `AUTO_COMMIT=false` path: `stage_draft()` writes a rendered doc to `_staging/<id>/draft.md` (+ `proposal.json` + the original source file) instead of filing it; `load_staged()` reconstructs a `Classification` from a (possibly hand-edited) draft; `cleanup_staged()` removes the staging dir after approval. |
| `watcher.py` | `watchdog`-based `Observer` on `_inbox/`, with per-path debounce + a size-stability/exclusive-open probe before treating a file as ready (handles slow Explorer copies), a startup catch-up scan (handles gaps while the watcher wasn't running), and quarantine-on-failure. |
| `pipeline.py` | The orchestrator: `process_file()`, `approve()`, and the shared `finalize()` tail (index update, commit, Open WebUI sync). |
| `para_scan.py` | `find_candidates()` walks the PARA buckets for files never run through the pipeline (supported extension, not an existing `.original.*` attachment, `.md` files missing the `type` frontmatter key); `scan()` runs each through extract/classify/render/`write_in_place()`/`finalize()`, always writing+committing immediately (no staging). Placement is never reclassified — see §4/§6's `okf_writer.py` entry. |
| `openwebui_sync.py` | Pushes a concept doc into Open WebUI's Knowledge collection: sign in (session JWT) -> upload file -> poll processing status -> attach to collection. `resync_all()` bulk-syncs every concept doc under the PARA folders. |
| `cli.py` | The `okeef` command group: `process-file`, `watch`, `scan-para`, `list-staged`, `approve`, `resync`. |

## 7. Review mode (`AUTO_COMMIT=false`)

By default (`AUTO_COMMIT=true`), a dropped file is classified, filed, and
committed with zero human interaction. Setting `AUTO_COMMIT=false` in `.env`
inserts a review step:

1. `process_file()` renders the doc as normal, but instead of writing it to
   its final PARA location, `review_queue.stage_draft()` writes it to
   `_staging/<8-char-id>/draft.md`, plus a `proposal.json` (informational:
   original filename, confidence, timestamp) and the original source file.
2. `draft.md`'s frontmatter includes two **staging-only** keys —
   `_para_bucket` and `_folder_slug` — alongside the normal OKF fields. A
   human can hand-edit *any* of this (title, type, tags, description, body
   content, and the proposed filing location) directly in one file.
3. `okeef list-staged` shows what's waiting, with the model's confidence.
4. `okeef approve <id> [--approved-by "Name"]` re-parses the (possibly
   edited) `draft.md`, reconstructs a `Classification`, and runs it through
   the *exact same* `write()` -> `finalize()` tail as the immediate path —
   the only difference is the commit gets `Reviewed: true` (and optionally
   `Approved-By: ...`) trailers. The staging directory is then deleted.

This mode exists as a documented, load-bearing seam (not a bolted-on
afterthought) — `finalize()` takes an explicit `commit: bool` rather than
reading `config.auto_commit` internally, precisely so `approve()` can always
commit regardless of the global default.

## 8. Retrieval / Open WebUI integration

- **Embedding model**: `nomic-embed-text` via Ollama (small, CPU-friendly,
  8192-token context avoids truncating whole concept docs).
- **Vector store**: Open WebUI's own built-in Knowledge-collection store
  (Chroma under the hood), not a hand-rolled external one — Open WebUI ties
  citation/incremental-sync metadata to its own internal file records, so an
  external store would mean reimplementing that plumbing for no benefit.
- **Sync mechanism** (`openwebui_sync.py`): signs in with the admin account's
  own email/password to get a session JWT (see §9.2 for why, not a generated
  API key), then `POST /api/v1/files/` (upload) -> poll
  `GET .../process/status` until `"completed"` -> `POST
  /api/v1/knowledge/{id}/file/add`. Runs after every successful commit,
  best-effort (failures log a warning, never break ingestion — the git
  commit is the source of truth; `okeef resync` catches up later).
- **`okeef resync`** walks every `.md` under the four PARA folders (never the
  whole bundle root — see §9.1) and re-syncs each. It's meant for the
  *first-time* backfill of pre-existing content into a freshly created
  Knowledge collection, or general catch-up after `data\openwebui\` is
  wiped/rebuilt — it is **not** safe to run repeatedly against a collection
  that already has the same content, since Open WebUI correctly rejects
  re-uploading unchanged content as a duplicate (`setup.ps1` accounts for
  this — see §9.4).
- **Chunking/hybrid search**: Open WebUI's own chunker, configured to
  800-token chunks / 150-token overlap, with `ENABLE_RAG_HYBRID_SEARCH`
  (BM25 + vector + reranking) turned on for better exact-term recall on tags
  and proper nouns.

## 9. Design decisions & debugging history

These are documented because they were non-obvious and cost real debugging
time — future changes to this system should account for them.

### 9.1 `resync_all()` must not walk the whole bundle root

**Bug found**: an early version of `resync_all()` did
`bundle_root.rglob("*.md")`. Back when `Knowledgebase\` and `App\` were still
flattened together at the repo root, `.venv/` and `.venv-webui/` lived
*inside* `bundle_root`, so this recursed into thousands of unrelated markdown
files from installed Python packages (`LICENSE.md`, `pytest_cache/README.md`,
etc.), which got embedded into the Knowledge collection and surfaced in chat
retrieval results.

**Fix**: `resync_all()` iterates only `config.para_buckets` (Projects/Areas/
Resources/Archives), never the bundle root. The later `App`/`Knowledgebase`
split (§4) makes the venvs' presence inside `bundle_root` structurally
impossible now, but the scoped iteration stays as defense in depth. Regression
test:
`App/tests/test_openwebui_sync.py::test_resync_all_does_not_walk_venv_or_bundle_root`.

### 9.2 Open WebUI API keys don't reliably survive a restart

**Observed**: a freshly generated Open WebUI API key works immediately, but
after stopping and restarting the `open-webui serve` process, the same key
returns `401 {"detail":"Your session has expired or the token is
invalid."}` — even after explicitly re-enabling `ENABLE_API_KEYS` via the
admin config API. Setting `ENABLE_API_KEYS=true` as a process environment
variable at startup doesn't help either, since it's a `PersistentConfig`
value that only seeds from the env var when no DB row exists yet — once a
row exists (even if effectively "false"), the env var is ignored.

**Fix**: `openwebui_sync.py` doesn't use API keys at all. It signs in with
the admin account's own `WEBUI_ADMIN_EMAIL`/`WEBUI_ADMIN_PASSWORD` (the same
credentials already needed for headless admin bootstrap) to get a session
JWT, which defaults to a ~4 week expiry and was not observed to have this
problem. `resync_all()` signs in once and reuses the token across every file
in the batch rather than re-authenticating per file.

### 9.3 `.env` written by PowerShell 5.1 carries a UTF-8 BOM

**Bug found**: `Set-Content -Encoding utf8` in Windows PowerShell 5.1 always
writes a UTF-8 byte-order-mark, even though "utf8" sounds BOM-less. This
silently corrupted the *first* key in a freshly created `.env`
(`WEBUI_ADMIN_EMAIL` became invisible to `os.environ.get()`, while
`WEBUI_ADMIN_PASSWORD` on the next line loaded fine) — a confusing symptom
because most of the config appeared to work.

**Fix, two layers**:
1. Any script that creates `.env` writes plain BOM-free UTF-8 via
   `[System.IO.File]::WriteAllText(path, content, [System.Text.UTF8Encoding]::new($false))`
   instead of `Set-Content -Encoding utf8`.
2. `config.py` loads `.env` with `load_dotenv(path, encoding="utf-8-sig")`,
   which strips a BOM if present and behaves identically to `"utf-8"` if not
   — defensive in case a BOM-carrying `.env` shows up again some other way.
   The same `utf-8-sig` pattern is used in `extract.py` for plain-text source
   files, found via an earlier, analogous bug.

### 9.4 A Knowledge collection can become unreachable after rapid restarts

**Observed**: after several quick stop/start cycles of Open WebUI during
testing, a previously-working Knowledge collection ID started returning `404`
from `GET /api/v1/knowledge/{id}` and was absent from `GET
/api/v1/knowledge/` (list), *despite* the row being fully intact when the
SQLite file (`data\openwebui\webui.db`) was inspected directly with a
separate Python process. This survived a clean restart, ruling out an
in-memory cache issue — it appears to be an application-level bug in the
installed Open WebUI version's knowledge-retrieval query.

**Fix (workaround, not a root-cause fix)**: delete the orphaned row and
create a fresh collection via the API (this has reliably worked every time),
then update `OPENWEBUI_KNOWLEDGE_ID` in `.env` and run `okeef resync`. No
content is lost — the git-committed OKF documents remain the source of
truth; the Knowledge collection is a derived index. Documented as a "Known
Issue" with the exact recovery commands in `README.md`.

### 9.5 `setup.ps1` must not unconditionally resync on every run

Directly downstream of §9.1/§8's dedup behavior: `setup.ps1`'s backfill step
originally called `okeef resync` unconditionally, which broke on every
re-run after the first (same content, same hash, correctly rejected as
duplicate). Fixed to only backfill when a Knowledge collection was *just*
created in that same run (`$needsOpenWebUiConfig`); later re-runs correctly
no-op with an explanatory message, and the user can run `okeef resync`
manually if they ever need to catch a collection up (e.g. after the §9.4
recovery procedure).

### 9.6 `Register-ScheduledTask`'s CIM provider can lie about success

`Register-ScheduledTask` was observed to write a non-terminating "Access is
denied" error to the error stream while the script's `$ErrorActionPreference
= "Stop"` didn't catch it, and execution continued to print a false "success"
message. `App\scripts\register-tasks.ps1` now wraps the call in `try/catch` *and*
independently verifies the task exists via `Get-ScheduledTask` afterward
before reporting success — belt-and-suspenders, since either mechanism alone
was insufficient.

Separately: Task Scheduler registration could not be completed from an
automated/sandboxed session on this environment (both `Register-ScheduledTask`
and the legacy `schtasks.exe` returned "Access is denied" despite the account
being an Administrator) — this points to a restriction on the calling
process's own token rather than the user's account permissions, and needs to
be run by the user directly in their own interactive shell.

## 10. Configuration reference

### `config/config.yaml` (shared, version-controlled)

| Key | Default | Notes |
|---|---|---|
| `auto_commit` | `true` | Overridable per-machine via `.env`'s `AUTO_COMMIT`. |
| `para_buckets` | `[Projects, Areas, Resources, Archives]` | |
| `classify_model` | `qwen2.5:3b-instruct` | Ollama model tag for classification. |
| `embed_model` | `nomic-embed-text` | Ollama model tag for embeddings (informational here; the effective setting lives in Open WebUI's own admin config, set during setup). |
| `ollama_host` | `http://localhost:11434` | |
| `chunk_size` / `chunk_overlap` | `800` / `150` | Also set in Open WebUI's retrieval config during setup; kept here for reference/consistency. |
| `openwebui.base_url` | `http://localhost:8080` | |

### `.env` (machine-specific, gitignored — see `.env.example`), lives in `App\`

| Key | Purpose |
|---|---|
| `AUTO_COMMIT` | Override `config.yaml`'s value without editing it. |
| `OKEEF_APP_ROOT` | Override the app root path (rarely needed); `repo_root`/`bundle_root` are derived from it (see §4). |
| `WEBUI_ADMIN_EMAIL` / `WEBUI_ADMIN_PASSWORD` / `WEBUI_ADMIN_NAME` | Headlessly bootstraps the Open WebUI admin account on first startup **and** is reused indefinitely by `openwebui_sync.py` to authenticate (see §9.2) — keep these set permanently, not just for first-run. |
| `OPENWEBUI_KNOWLEDGE_ID` | The Knowledge collection UUID `openwebui_sync.py` pushes into. Per-machine (each Open WebUI instance generates its own on creation). |

`config.py`'s `Config` splits what used to be a single `bundle_root` into
three fields: `repo_root` (git top level, `D:\OKEEF`, used only by
`git_ops.commit_files()`), `app_root` (`App\`, used for `_inbox`/`_staging`/
`_quarantine`/`logs`), and `bundle_root` (`Knowledgebase\`, used for
everything PARA-content-related — index/log updates, `okf_writer.write()`'s
target dir, `resync_all()`'s bucket iteration).

## 11. CLI reference

All commands run inside `App\.venv` (`App\.venv\Scripts\okeef.exe ...`, or
`okeef ...` if that venv's `Scripts\` is on `PATH`):

| Command | Purpose |
|---|---|
| `okeef process-file <path>` | Run one file through the full pipeline manually (extract -> classify -> file/stage -> commit). |
| `okeef watch` | Run the startup catch-up scan, then watch `App\_inbox\` continuously (foreground; this is what the Scheduled Task runs headlessly via `pythonw.exe -m okeef.cli watch`, and what `App\scripts\Start-Service.bat` runs on demand). |
| `okeef scan-para` | Scan the PARA folders for files added by hand (bypassing `_inbox`) and OKF-ify each one in place — bucket/folder exactly as filed by hand, never reclassified. Always writes and commits immediately; doesn't participate in the `AUTO_COMMIT=false` staging flow. Also runnable via `App\scripts\Scan-ParaFolders.bat`. |
| `okeef list-staged` | List drafts awaiting review (`AUTO_COMMIT=false` mode only). |
| `okeef approve <id> [--approved-by NAME]` | File and commit a staged draft. |
| `okeef resync` | Bulk-sync every concept doc under the PARA folders into Open WebUI's Knowledge collection. See §8/§9.5 for when this is and isn't safe to run. |

## 12. Testing

`pytest` suite in `App\tests\`, run via
`App\.venv\Scripts\python.exe -m pytest App\tests -v`.

- `test_extract.py` — BOM-stripping regression test.
- `test_pipeline.py` — extract/write/index/commit behavior, using a real
  (throwaway, `tmp_path`-isolated) git repo per test.
- `test_review_queue.py` — stage/list/approve flow, including that a
  hand-edited title/bucket in a staged draft is honored on approval.
- `test_para_scan.py` — `find_candidates()` filtering (skips already-OKF'd
  `.md`, `.original.*` attachment siblings) and `scan()` writing in place
  without reclassifying the bucket.
- `test_classify.py` — **integration tests against the real Ollama server**;
  auto-skipped if `localhost:11434` isn't reachable, rather than failing.
- `test_openwebui_sync.py` — mocked-HTTP unit tests for the sign-in/upload/
  process/attach flow, plus the `resync_all()` scoping regression test
  from §9.1.

`App/tests/conftest.py` holds shared fixtures: an autouse
`stub_classification` fixture that replaces the real Ollama call with the
original deterministic stub logic (so most tests stay fast and don't need
Ollama running), and `repo_root`/`bundle_root`/`app_root`/`config` fixtures
that build a temp repo mirroring the real `repo_root`/`Knowledgebase`/`App`
split, with a real git repo at `repo_root`.

## 13. Replicating to another machine

See `README.md`'s **Setup** section for the user-facing walkthrough — in
short, `git clone` + `.\setup.ps1`, which is idempotent and handles every
step short of Task Scheduler registration (see §9.6) via `winget` installs,
venv creation, Ollama model pulls, and Open WebUI's entirely headless
first-run configuration (admin account, embeddings, chunking, Knowledge
collection — all via REST API, no browser interaction required).

Cross-platform notes (this automation is currently Windows-specific) are
also in `README.md`.

## 14. Build history (phases)

The system was built incrementally, each phase committed and verified
working before moving to the next:

0. Bootstrap — OKF/PARA skeleton, git init.
1. Static pipeline core — extract/write/index/commit, classification stubbed.
2. Inbox watcher — `watchdog`, debounce, quarantine.
3. Real Ollama classification.
4. Review-mode toggle (`AUTO_COMMIT` seam).
5. Open WebUI embedding/retrieval integration.
6. Windows service management (Scheduled Task + launcher scripts).
7. Replicability validation (`setup.ps1` idempotency testing) + this
   documentation + `README.md`.
8. Repository split (`Knowledgebase`/`App`, §4), `Config`'s `repo_root`/
   `app_root`/`bundle_root` split, the PARA-folder scanner (`para_scan.py`,
   §6), and the `Start-Service.bat`/`Scan-ParaFolders.bat` on-demand
   launchers.

Full detail is in the git log — every phase and every bug fix in §9 has its
own commit with a detailed message explaining what changed and why.
