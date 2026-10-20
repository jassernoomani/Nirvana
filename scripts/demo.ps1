# Starts or stops the whole Nirvana demo on this PC: Ollama model, back-end, front-end, browser windows.
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Action start [-ResetData] [-NoBrowser]
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Action stop
# The .bat files in the repository root call this script, so a double-click is enough.
param(
    [ValidateSet('start', 'stop')] [string]$Action = 'start',
    [switch]$ResetData,  # rebuild the demo data so orders and reservations are dated around today
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$logs = Join-Path $PSScriptRoot 'logs'
$pidFile = Join-Path $logs 'demo-pids.txt'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$app = 'http://localhost:4200'
$ollamaUrl = 'http://127.0.0.1:11434'

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "   $text" -ForegroundColor Green }

function Test-Url($url) {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 $url | Out-Null; return $true } catch { return $false }
}

function Wait-Url($url, $seconds, $name) {
    $end = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $end) {
        if (Test-Url $url) { Ok "$name is up"; return }
        Start-Sleep -Seconds 2
    }
    throw "$name did not start within $seconds s. See the logs in $logs"
}

function Stop-Port($port) {
    $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($owner in $owners) { if ($owner -gt 0) { & taskkill /PID $owner /T /F 2>$null | Out-Null } }
}

# Windows PowerShell turns a tool's progress output on stderr into an error; judge native tools by exit code instead.
function Invoke-Native([scriptblock]$command, [string]$what) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $command 2>&1 | Out-Host } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

function Get-Model {
    $envFile = Join-Path $backend '.env'
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match '^\s*LLM_MODEL\s*=' } | Select-Object -First 1
        if ($line) { return ($line -split '=', 2)[1].Trim() }
    }
    return 'qwen2.5:3b'
}

function Stop-Demo {
    Step 'Stopping the Nirvana demo'
    if (Test-Path $pidFile) {
        foreach ($p in Get-Content $pidFile) { if ($p) { & taskkill /PID $p /T /F 2>$null | Out-Null } }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
    Stop-Port 8000
    Stop-Port 4200
    Ok 'Back-end (port 8000) and front-end (port 4200) stopped'
    if (Test-Url "$ollamaUrl/api/tags") {
        $body = @{ model = (Get-Model); keep_alive = 0 } | ConvertTo-Json
        try {
            Invoke-RestMethod -Method Post -Uri "$ollamaUrl/api/generate" -Body $body -ContentType 'application/json' -TimeoutSec 30 | Out-Null
            Ok 'Model unloaded from memory (Ollama itself keeps running)'
        } catch { Ok 'Model was not loaded' }
    }
}

if ($Action -eq 'stop') { Stop-Demo; exit 0 }

New-Item -ItemType Directory -Force $logs | Out-Null

# 1. Anything missing on a fresh PC is set up once.
Step 'Checking the installation'
if (-not (Test-Path $python)) {
    Write-Host '   Creating the Python environment (first run only)...'
    Push-Location $backend
    Invoke-Native { py -3 -m venv .venv } 'Creating the Python environment'
    Invoke-Native { & $python -m pip install -r requirements.txt } 'Installing the back-end packages'
    Pop-Location
}
if (-not (Test-Path (Join-Path $backend '.env'))) {
    Copy-Item (Join-Path $backend '.env.example') (Join-Path $backend '.env')
    Ok 'Created backend\.env from .env.example'
}
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host '   Installing front-end packages (first run only)...'
    Push-Location $frontend
    Invoke-Native { npm.cmd ci } 'Installing the front-end packages'
    Pop-Location
}
Ok 'Python environment, .env and front-end packages are present'

# 2. Ollama and the model.
Step 'Checking Ollama and the model'
$model = Get-Model
if (-not (Test-Url "$ollamaUrl/api/tags")) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) { throw 'Ollama is not installed. Install it from https://ollama.com/download, then run this again.' }
    Start-Process $ollama.Source -ArgumentList 'serve' -WindowStyle Hidden
    Wait-Url "$ollamaUrl/api/tags" 30 'Ollama'
}
$installed = (Invoke-RestMethod "$ollamaUrl/api/tags").models | ForEach-Object { $_.name }
if ($installed -notcontains $model) {
    Write-Host "   Downloading $model (about 2 GB, first run only)..."
    Invoke-Native { ollama pull $model } "Downloading $model"
}
Ok "Ollama is running with $model"

# 3. Clean start: a server left running from before would serve old code.
Step 'Stopping anything still running from before'
Stop-Port 8000
Stop-Port 4200
Ok 'Ports 8000 and 4200 are free'

# 4. Demo data.
$db = Join-Path $backend 'app\restaurant.db'
if ($ResetData -or -not (Test-Path $db)) {
    Step 'Rebuilding the demo data (90 days, dated around today)'
    Push-Location $backend
    Invoke-Native { & $python seed_data.py --reset } 'Rebuilding the demo data'
    Pop-Location
    Ok 'Demo data rebuilt'
}

# 5. Back-end and front-end, in the background, with their logs.
Step 'Starting the back-end and the front-end'
$api = Start-Process -FilePath $python -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs 'backend.log') -RedirectStandardError (Join-Path $logs 'backend-errors.log')
$web = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npm.cmd', 'start' `
    -WorkingDirectory $frontend -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs 'frontend.log') -RedirectStandardError (Join-Path $logs 'frontend-errors.log')
Set-Content $pidFile @($api.Id, $web.Id)
Wait-Url 'http://127.0.0.1:8000/api/menu/categories' 60 'Back-end'
Wait-Url $app 240 'Front-end'

# 6. Load the model into memory now, so the first analysis in front of the jury is fast.
Step "Warming up $model (up to a minute)"
$body = @{ model = $model; prompt = 'Bonjour'; stream = $false; keep_alive = '2h'; options = @{ num_predict = 1 } } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$ollamaUrl/api/generate" -Body $body -ContentType 'application/json' -TimeoutSec 180 | Out-Null
Ok 'Model loaded. It stays in memory 10 minutes after each use: warm it up again if you wait longer.'

# 7. One window per role: a normal one for the customer, a private one for the staff.
if (-not $NoBrowser) {
    $edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($edge) {
        Start-Process $edge -ArgumentList '--new-window', "$app/login"
        Start-Process $edge -ArgumentList '--inprivate', "$app/login"
        Ok 'Opened two Edge windows: sign in as the customer in one and as the manager in the private one'
    } else {
        Start-Process "$app/login"
    }
}

Step 'Nirvana is running'
Write-Host "   App:            $app"
Write-Host '   Customer:       demo@nirvana.test'
Write-Host '   Staff:          manager@nirvana.test   (password: see the README, "Demo accounts")'
Write-Host "   Logs:           $logs"
Write-Host '   To stop it all: double-click stop-demo.bat'
