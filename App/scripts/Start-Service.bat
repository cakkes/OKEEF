@echo off
rem Starts the OKEEF ingestion service on demand: catch-up scan + continuous
rem _inbox watching + per-file classify/file/commit/sync. No console window is
rem left open (pythonw.exe has none). Deliberately does not start Open WebUI --
rem run start-openwebui.ps1 separately for that.
start "" "%~dp0..\.venv\Scripts\pythonw.exe" -m okeef.cli watch
