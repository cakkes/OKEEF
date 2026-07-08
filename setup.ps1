<#
One-shot bootstrap for a new OKEEF checkout: installs prerequisites (git, Python 3.11,
Ollama) if missing, creates the two venvs, installs dependencies, pulls the required
Ollama models, sets up Open WebUI (admin account, embeddings, Knowledge collection),
backfills any existing content, and registers the inbox watcher as a Scheduled Task.

Safe to re-run: every step checks whether it's already done before acting.

Usage: run from a PowerShell prompt in the repo root:
    .\setup.ps1
#>

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$appRoot = Join-Path $repoRoot "App"
$knowledgebaseRoot = Join-Path $repoRoot "Knowledgebase"

function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Output "== OKEEF setup =="

# 1. Prerequisites ------------------------------------------------------------
Refresh-Path
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Output "Installing Git..."
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    Refresh-Path
}

$hasPy311 = $false
try { if (py -3.11 --version 2>$null) { $hasPy311 = $true } } catch {}
if (-not $hasPy311) {
    Write-Output "Installing Python 3.11..."
    winget install --id Python.Python.3.11 -e --source winget --accept-package-agreements --accept-source-agreements
    Refresh-Path
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Output "Installing Ollama..."
    winget install --id Ollama.Ollama -e --source winget --accept-package-agreements --accept-source-agreements
    Refresh-Path
    Start-Sleep -Seconds 5
}

# 2. Ingestion pipeline venv ---------------------------------------------------
New-Item -ItemType Directory -Force -Path $appRoot | Out-Null
$venv = Join-Path $appRoot ".venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Output "Creating ingestion pipeline venv..."
    py -3.11 -m venv $venv
}
& "$venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$venv\Scripts\pip.exe" install -e "$appRoot[dev]" --quiet

# 3. Ollama models --------------------------------------------------------------
Refresh-Path
$models = & ollama list 2>$null | Out-String
if ($models -notmatch "qwen2\.5:3b-instruct") {
    Write-Output "Pulling qwen2.5:3b-instruct (~1.9GB)..."
    ollama pull qwen2.5:3b-instruct
}
if ($models -notmatch "nomic-embed-text") {
    Write-Output "Pulling nomic-embed-text (~275MB)..."
    ollama pull nomic-embed-text
}

# 4. Bundle skeleton (in case this is a partial checkout without content yet) --
foreach ($bucket in @("Projects", "Areas", "Resources", "Archives")) {
    $dir = Join-Path $knowledgebaseRoot $bucket
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $idx = Join-Path $dir "index.md"
    if (-not (Test-Path $idx)) {
        "# $bucket`n`n<!-- OKEEF:AUTO-INDEX:START -->`n<!-- OKEEF:AUTO-INDEX:END -->`n" |
            Set-Content -Path $idx -Encoding utf8
    }
}
foreach ($d in @("_inbox", "_staging", "_quarantine", "logs")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $appRoot $d) | Out-Null
}

# 5. .env ------------------------------------------------------------------
$envPath = Join-Path $appRoot ".env"
if (-not (Test-Path $envPath)) {
    Write-Output ""
    Write-Output "No .env found -- Open WebUI needs an admin account (created headlessly, no browser signup)."
    $adminEmail = Read-Host "Admin email for Open WebUI"
    $adminName = Read-Host "Admin display name"
    Add-Type -AssemblyName System.Web
    $generated = [System.Web.Security.Membership]::GeneratePassword(20, 4)
    $envContent = "WEBUI_ADMIN_EMAIL=$adminEmail`nWEBUI_ADMIN_PASSWORD=$generated`nWEBUI_ADMIN_NAME=$adminName`n"
    # Windows PowerShell 5.1's `Set-Content -Encoding utf8` writes a BOM, which
    # silently corrupts the first key's name for python-dotenv/os.environ readers.
    # Write plain BOM-free UTF-8 instead.
    [System.IO.File]::WriteAllText($envPath, $envContent, [System.Text.UTF8Encoding]::new($false))
    Write-Output "Generated a random admin password and saved it to .env (gitignored, never printed)."
    Write-Output "Run 'Get-Content .env' yourself later if you need to see it."
}

# 6. Open WebUI venv ------------------------------------------------------------
$webuiVenv = Join-Path $appRoot ".venv-webui"
if (-not (Test-Path "$webuiVenv\Scripts\open-webui.exe")) {
    Write-Output "Creating Open WebUI venv (large dependency set -- several minutes)..."
    py -3.11 -m venv $webuiVenv
    & "$webuiVenv\Scripts\python.exe" -m pip install --upgrade pip --quiet
    & "$webuiVenv\Scripts\pip.exe" install open-webui --quiet
}

# 7. Open WebUI first-run config (embeddings, chunking, Knowledge collection) --
# Sync auth uses the admin account's own email/password (session sign-in), not a
# generated API key -- API keys were found not to reliably survive an Open WebUI
# restart in the installed version, so there's nothing to generate/store here.
$envMap = @{}
foreach ($line in Get-Content $envPath) {
    if ($line -match '^([^=]+)=(.*)$') { $envMap[$matches[1]] = $matches[2] }
}
$needsOpenWebUiConfig = -not $envMap.ContainsKey("OPENWEBUI_KNOWLEDGE_ID")

if ($needsOpenWebUiConfig) {
    Write-Output "Starting Open WebUI once to complete first-run setup..."
    foreach ($kv in $envMap.GetEnumerator()) { [System.Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, "Process") }
    $env:DATA_DIR = Join-Path $appRoot "data\openwebui"
    $env:OLLAMA_BASE_URL = "http://localhost:11434"
    $env:ENABLE_SIGNUP = "false"
    $env:PORT = "8080"
    New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null

    $proc = Start-Process -FilePath "$webuiVenv\Scripts\open-webui.exe" -ArgumentList "serve" -WorkingDirectory $appRoot `
        -RedirectStandardOutput (Join-Path $appRoot "logs\openwebui-stdout.log") `
        -RedirectStandardError (Join-Path $appRoot "logs\openwebui-stderr.log") -PassThru
    $proc.Id | Out-File -FilePath (Join-Path $appRoot "logs\openwebui.pid") -Encoding ascii

    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 3
        try {
            if ((Invoke-WebRequest -Uri "http://localhost:8080/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) {
                $ready = $true; break
            }
        } catch {}
    }
    if (-not $ready) { throw "Open WebUI didn't become ready in time -- check logs\openwebui-stderr.log" }

    $signinBody = @{ email = $envMap["WEBUI_ADMIN_EMAIL"]; password = $envMap["WEBUI_ADMIN_PASSWORD"] } | ConvertTo-Json
    $auth = Invoke-RestMethod -Uri "http://localhost:8080/api/v1/auths/signin" -Method Post -Body $signinBody -ContentType "application/json"
    $headers = @{ Authorization = "Bearer $($auth.token)" }

    $embBody = @{
        RAG_EMBEDDING_ENGINE     = "ollama"
        RAG_EMBEDDING_MODEL      = "nomic-embed-text"
        RAG_EMBEDDING_BATCH_SIZE = 1
        ollama_config            = @{ url = "http://localhost:11434"; key = "" }
    } | ConvertTo-Json -Depth 5
    Invoke-RestMethod -Uri "http://localhost:8080/api/v1/retrieval/embedding/update" -Headers $headers -Method Post `
        -Body $embBody -ContentType "application/json" | Out-Null

    $ragCfg = Invoke-RestMethod -Uri "http://localhost:8080/api/v1/retrieval/config" -Headers $headers -Method Get
    $ragCfg.CHUNK_SIZE = 800
    $ragCfg.CHUNK_OVERLAP = 150
    $ragCfg.ENABLE_RAG_HYBRID_SEARCH = $true
    Invoke-RestMethod -Uri "http://localhost:8080/api/v1/retrieval/config/update" -Headers $headers -Method Post `
        -Body ($ragCfg | ConvertTo-Json -Depth 10) -ContentType "application/json" | Out-Null

    if (-not $envMap.ContainsKey("OPENWEBUI_KNOWLEDGE_ID")) {
        $kBody = @{ name = "OKEEF Bundle"; description = "Personal OKF/PARA knowledgebase ($knowledgebaseRoot)" } | ConvertTo-Json
        $knowledge = Invoke-RestMethod -Uri "http://localhost:8080/api/v1/knowledge/create" -Headers $headers -Method Post `
            -Body $kBody -ContentType "application/json"
        Add-Content -Path $envPath -Value "OPENWEBUI_KNOWLEDGE_ID=$($knowledge.id)" -Encoding ascii
    }

    Write-Output "Open WebUI first-run setup complete. Stopping the temporary instance."
    Write-Output "(use App\scripts\start-openwebui.ps1 to run it normally, on demand)"
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# 8. Backfill any existing content into Open WebUI --------------------------
# Only on first-run (right after creating a fresh Knowledge collection): resync
# isn't safe to blindly re-run against a collection that already has content --
# Open WebUI correctly rejects re-uploading unchanged content as a duplicate. On
# later setup.ps1 runs, this step is a no-op; run 'okeef resync' by hand if you
# ever need to catch up a collection (e.g. after recreating one, see README).
if ($needsOpenWebUiConfig) {
    Write-Output "Backfilling existing content into Open WebUI..."
    try {
        foreach ($kv in $envMap.GetEnumerator()) { [System.Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, "Process") }
        $env:DATA_DIR = Join-Path $appRoot "data\openwebui"
        if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = "http://localhost:11434" }
        $env:ENABLE_SIGNUP = "false"
        $proc = Start-Process -FilePath "$webuiVenv\Scripts\open-webui.exe" -ArgumentList "serve" -WorkingDirectory $appRoot `
            -RedirectStandardOutput (Join-Path $appRoot "logs\openwebui-stdout.log") `
            -RedirectStandardError (Join-Path $appRoot "logs\openwebui-stderr.log") -PassThru
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 2
            try {
                if ((Invoke-WebRequest -Uri "http://localhost:8080/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { break }
            } catch {}
        }
        & "$venv\Scripts\okeef.exe" resync
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Output "Resync skipped or failed ($($_.Exception.Message)) -- run 'okeef resync' manually later."
    }
} else {
    Write-Output "Skipping backfill (Knowledge collection already configured) -- run 'okeef resync' manually if you need to catch it up."
}

# 9. Register the watcher as a Scheduled Task --------------------------------
& (Join-Path $appRoot "scripts\register-tasks.ps1")

Write-Output ""
Write-Output "== Setup complete =="
Write-Output "- Watcher: registered to run at logon (drop a file into App\_inbox\ to test)."
Write-Output "- Chat UI: run App\scripts\start-openwebui.ps1, then browse to http://localhost:8080"
Write-Output "- Smoke test: 'okeef process-file <path>', or drop a file into App\_inbox\ and check Knowledgebase\log.md"
