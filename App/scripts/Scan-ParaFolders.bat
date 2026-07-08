@echo off
rem One-shot scan of the PARA folders for hand-added files never run through the
rem pipeline. OKF-ifies each one in place (same bucket/folder you filed it in),
rem then commits (+ attempts sync). Console stays open so you can read the results.
"%~dp0..\.venv\Scripts\okeef.exe" scan-para
echo.
pause
