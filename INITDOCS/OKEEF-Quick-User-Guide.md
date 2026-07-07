# OKEEF Quick User Guide

Your personal knowledgebase at `D:\OKEEF`. This is the short, practical
version — for setup or technical details, see `README.md` or
`INITDOCS/OKEEF-Project-Documentation.md`.

## Add something to your knowledgebase

Drop a file into `D:\OKEEF\_inbox\` — `.txt`, `.md`, `.pdf`, or `.docx`.

That's it. Within a few seconds, it's automatically:
- read and summarized
- tagged and filed into the right folder (Projects, Areas, Resources, or Archives)
- saved permanently (committed to git)

The file disappears from `_inbox` once it's been processed — that's normal,
it's now living in its new folder as a formatted note.

**No watcher running?** Files just sit in `_inbox` until the watcher starts
(it should start automatically when you log in, once set up — see README).
You can also process one file manually any time:
```powershell
D:\OKEEF\.venv\Scripts\okeef.exe process-file "D:\OKEEF\_inbox\yourfile.txt"
```

## Ask questions about your notes

1. Start the chat interface:
   ```powershell
   D:\OKEEF\scripts\start-openwebui.ps1
   ```
2. Open your browser to **http://localhost:8080**
3. Ask a question — answers are grounded in your actual notes, with citations
   showing which file the answer came from.

Close the terminal window (or Ctrl+C) when you're done chatting — it doesn't
need to stay running.

## Where does my stuff get filed?

Everything is organized using the **PARA** method:

| Folder | What goes here |
|---|---|
| **Projects** | Active things with a deadline or a specific outcome (e.g. "Plan the Q3 launch") |
| **Areas** | Ongoing responsibilities with no end date (e.g. health, finances, a role you maintain) |
| **Resources** | Reference material, things you want to remember (e.g. a recipe, an article) |
| **Archives** | Stuff that's done/inactive |

The AI decides which folder fits based on the content — it's not always
perfect, especially for genuinely ambiguous content. See below for how to fix it.

## Something got filed wrong

Two ways to fix it:

**Just move it.** Everything is plain markdown files — open File Explorer,
drag the `.md` file to the folder you actually want, and it'll stay there.
(Optional cleanup: run `okeef` reindex commands aren't needed for a manual
move — the next automated ingest will refresh the folder listing naturally.)

**Or turn on review-before-filing mode**, so you approve everything before
it's saved, instead of fixing it after the fact:
1. Open `D:\OKEEF\.env` in Notepad
2. Add or change the line: `AUTO_COMMIT=false`
3. Save. New files now get staged for your review instead of filed immediately.

With review mode on:
- `okeef list-staged` — see what's waiting for review
- Open `_staging\<id>\draft.md` in any text editor — you can fix the title,
  tags, or even which folder it's headed for (the `_para_bucket` /
  `_folder_slug` lines at the top), then save
- `okeef approve <id>` — files it for real

Turn `AUTO_COMMIT` back to `true` any time you want to go back to fully
automatic.

## If a file doesn't get processed

Check `D:\OKEEF\_quarantine\` — failed files land here with a
`<filename>.reason.txt` explaining what went wrong (common causes: a scanned
PDF with no selectable text, or an unsupported file type). Fix the issue (or
just re-save the file in a supported format) and drop it back into `_inbox`.

## Quick command reference

Run these from a PowerShell window (paths assume the default install):

```powershell
# Process one file right now, without waiting for the watcher
D:\OKEEF\.venv\Scripts\okeef.exe process-file "<path to file>"

# See what's waiting for review (only matters if AUTO_COMMIT=false)
D:\OKEEF\.venv\Scripts\okeef.exe list-staged

# Approve a staged file
D:\OKEEF\.venv\Scripts\okeef.exe approve <id>

# Start the chat UI
D:\OKEEF\scripts\start-openwebui.ps1

# Catch the chat UI up on anything it's missing (rarely needed)
D:\OKEEF\.venv\Scripts\okeef.exe resync
```

## Where everything actually lives

- Your notes: `D:\OKEEF\Projects`, `Areas`, `Resources`, `Archives`
- Drop zone: `D:\OKEEF\_inbox`
- Failed items: `D:\OKEEF\_quarantine`
- Pending review (if enabled): `D:\OKEEF\_staging`
- Full change history: `D:\OKEEF\log.md`, or `git log` in a terminal

Everything is backed by git, so nothing is ever silently lost — even a bad
auto-classification is just a commit that can be found and fixed.
