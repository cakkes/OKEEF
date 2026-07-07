# OKEEF

A personal, local-first knowledgebase ("second brain") built on Google's
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
(OKF v0.1) and organized with the [PARA method](https://fortelabs.com/blog/para/)
(Projects / Areas / Resources / Archives).

Drop files into `_inbox\`; a local pipeline (Ollama + a small classifier model)
extracts, classifies, and files them as conformant OKF markdown documents, then
commits the result to git. The whole bundle is queryable through
[Open WebUI](https://openwebui.com), a local chat UI with retrieval-augmented
generation (RAG), so you can ask questions grounded in your own notes.

Everything runs entirely locally -- no data leaves the machine, no cloud APIs
involved.

## Prerequisites

- Windows 11 (this repo's automation is Windows-specific; see [Cross-platform
  notes](#cross-platform-notes) below for adapting it elsewhere)
- PowerShell
- A GPU with at least ~4GB VRAM is enough for the default models (CPU-only also
  works, just slower)

`setup.ps1` installs the rest (Git, Python 3.11, Ollama) via `winget` if they're
not already present.

## Setup

```powershell
git clone <this-repo-url> D:\OKEEF
cd D:\OKEEF
.\setup.ps1
```

`setup.ps1` is idempotent -- safe to re-run any time, including after a partial
failure. It:

1. Installs Git / Python 3.11 / Ollama if missing.
2. Creates `.venv` (the ingestion pipeline) and installs its dependencies.
3. Pulls the two required Ollama models: `qwen2.5:3b-instruct` (classification)
   and `nomic-embed-text` (embeddings).
4. Creates the PARA folder skeleton if this is a fresh checkout without content yet.
5. Prompts for an admin email/name on first run and generates a random admin
   password, saved to `.env` (gitignored, machine-specific, never printed to the
   terminal).
6. Creates `.venv-webui` and installs Open WebUI.
7. Starts Open WebUI once to complete first-run setup **entirely headlessly, no
   browser needed**: creates the admin account, enables API keys, points the
   embedding engine at Ollama, sets chunk size/overlap and hybrid search, and
   creates the "OKEEF Bundle" Knowledge collection -- all via Open WebUI's REST API.
8. Backfills any existing content into that Knowledge collection.
9. Registers the inbox watcher as a Windows Scheduled Task (see below -- this step
   may need to be run separately if it fails with "Access is denied").

### If Scheduled Task registration fails

`Register-ScheduledTask` (and the legacy `schtasks.exe`) can fail with "Access is
denied" depending on how restrictive the current process token is, even for an
Administrator account under UAC. If `setup.ps1` reports this, run the one
remaining step yourself in a normal PowerShell window:

```powershell
.\scripts\register-tasks.ps1
```

## Day-to-day use

- **Add something to your knowledgebase**: drop a `.txt`, `.md`, `.pdf`, or
  `.docx` file into `_inbox\`. If the watcher is running (it auto-starts at
  login once the Scheduled Task is registered), it's picked up within a couple
  of seconds, classified, filed into the right PARA folder as an OKF document,
  and committed to git.
- **Chat with your knowledgebase**: run `.\scripts\start-openwebui.ps1`, then
  open <http://localhost:8080>. Not auto-started at login -- it's a manual
  run/shortcut since it's only needed while actively chatting.
- **Process one file manually** (without the watcher): `okeef process-file <path>`
- **Pause ingestion**: stop the "OKEEF Watcher" scheduled task
  (`Stop-ScheduledTask -TaskName "OKEEF Watcher"`), or just don't drop files.
- **Toggle review-before-commit mode**: set `AUTO_COMMIT=false` in `.env`. New
  drops are staged under `_staging\<id>\` (a `draft.md` you can hand-edit --
  including the proposed PARA bucket/folder, via the `_para_bucket`/
  `_folder_slug` frontmatter keys -- plus a `proposal.json` for reference)
  instead of being filed immediately. Review with `okeef list-staged`, then
  `okeef approve <id>` to file and commit it (add `--approved-by "Your Name"`
  to record it in the commit trailer).
- **Reprocess a quarantined file**: failed extractions/classifications land in
  `_quarantine\` with a `<name>.reason.txt` explaining why. Fix the underlying
  issue (or the file itself) and drop it back into `_inbox\`.
- **Re-sync Open WebUI's Knowledge collection**: `okeef resync` -- walks every
  concept doc under the PARA folders and re-uploads it. Useful after wiping
  `data\openwebui\` or if a sync failed partway (sync failures don't break
  ingestion; the git commit is the source of truth, and `resync` catches up).

## Known issues

- **"Failed to attach file... 400: We could not find what you're looking
  for"** on `okeef resync` or a sync warning in `logs\watcher.log`: the
  installed Open WebUI version has been observed to make an existing Knowledge
  collection unreachable via its API after several rapid restarts, even though
  the row is still present and intact in `data\openwebui\webui.db` (confirmed
  by inspecting the SQLite file directly). The fix is to create a fresh
  collection and point `OPENWEBUI_KNOWLEDGE_ID` at it:
  ```powershell
  # after signing in and getting $headers (see setup.ps1 for the exact calls)
  $k = Invoke-RestMethod -Uri "http://localhost:8080/api/v1/knowledge/create" -Headers $headers -Method Post `
      -Body (@{name="OKEEF Bundle"; description="Personal OKF/PARA knowledgebase"} | ConvertTo-Json) `
      -ContentType "application/json"
  # replace OPENWEBUI_KNOWLEDGE_ID in .env with $k.id, then: okeef resync
  ```
  This doesn't lose any content -- the git-committed OKF documents are the
  source of truth; `resync` re-populates whatever collection ID you point it at.

## How it's built

```
D:\OKEEF\
├── index.md, log.md              bundle root (hand-curated; never auto-touched
│                                  beyond log.md's dated entries)
├── Projects\ Areas\ Resources\ Archives\
│                                  PARA sections; each subfolder's index.md is
│                                  auto-generated between marker comments
├── _inbox\                       drop files here
├── _staging\                     review-mode drafts (AUTO_COMMIT=false)
├── _quarantine\                  failed extractions/classifications
├── src\okeef\                    the ingestion pipeline (see module docstrings)
├── config\config.yaml            shared config (models, chunk size, PARA buckets)
├── .env                          machine-specific: AUTO_COMMIT override,
│                                  Open WebUI admin/API credentials, knowledge_id
├── setup.ps1, scripts\           bootstrap + service management
└── data\openwebui\               Open WebUI's own state (regenerable via resync,
                                   except chat history itself)
```

Each `src/okeef/*.py` module has a docstring explaining its role; `pipeline.py`
is the best starting point -- it's the orchestrator tying extraction,
classification, writing, indexing, committing, and syncing together.

## Smoke test

After setup, confirm everything works end to end:

```powershell
"Testing OKEEF." | Out-File _inbox\smoke-test.txt -Encoding utf8
# wait a few seconds for the watcher (or run: okeef process-file _inbox\smoke-test.txt)
git log --oneline -1        # should show a new "ingest(...)" commit
```

Then open <http://localhost:8080> (after running `scripts\start-openwebui.ps1`)
and ask a question about the file you just added -- the answer should be
grounded in it and cite the source.

## Cross-platform notes

The pipeline code (`src/okeef/`) is pure Python and portable as-is. What's
Windows-specific:

- `pythonw.exe` (no-console launch) -- macOS/Linux don't need an equivalent;
  just run the command directly or via a `systemd`/`launchd` unit.
- Task Scheduler (`scripts\register-tasks.ps1`) -- replace with a `launchd`
  `.plist` (macOS, `RunAtLoad`) or a `systemd --user` service / cron `@reboot`
  entry (Linux) running `python -m okeef.cli watch`.
- `winget` in `setup.ps1` -- swap for `brew` (macOS) or your distro's package
  manager for installing Git/Python/Ollama; Ollama and Open WebUI both ship
  native installers for macOS/Linux too.
- Path handling in the pipeline itself already uses `pathlib`, so it doesn't
  need changes.
