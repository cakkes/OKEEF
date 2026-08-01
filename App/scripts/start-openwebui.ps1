<#
On-demand launcher for Open WebUI. Not auto-started at login (see
scripts\register-tasks.ps1 for the watcher, which is) -- Open WebUI is only needed
when actively chatting, so it's a manual run/shortcut rather than an always-on
background service.

Runs in the foreground; Ctrl+C (or close the window) to stop.
#>

$ErrorActionPreference = "Stop"
$appRoot = (Resolve-Path "$PSScriptRoot\..").Path

$envPath = Join-Path $appRoot ".env"
if (Test-Path $envPath) {
    foreach ($line in Get-Content $envPath) {
        if ($line -match '^([^#][^=]*)=(.*)$') {
            $value = $matches[2].Trim()
            # Strip one matching pair of wrapping quotes, mirroring python-dotenv's
            # behavior (used by config.py) -- otherwise a quoted value here (e.g. a
            # password with special characters) would keep its literal quote
            # characters while the pipeline's own .env loader strips them, and the
            # two would end up disagreeing on credentials.
            if ($value.Length -ge 2 -and (
                    ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                    ($value.StartsWith("'") -and $value.EndsWith("'"))
                )) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $value, "Process")
        }
    }
}

$env:DATA_DIR = Join-Path $appRoot "data\openwebui"
if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = "http://localhost:11434" }
if (-not $env:PORT) { $env:PORT = "8080" }
$env:ENABLE_SIGNUP = "false"
New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null

$openWebUiExe = Join-Path $appRoot ".venv-webui\Scripts\open-webui.exe"
if (-not (Test-Path $openWebUiExe)) {
    throw "Open WebUI is not installed at $openWebUiExe -- run setup.ps1 first."
}

Write-Output "Starting Open WebUI on http://localhost:$($env:PORT) -- Ctrl+C to stop."
& $openWebUiExe serve
