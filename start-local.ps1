[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $repoRoot '.runtime'
$statePath = Join-Path $runtimeDir 'local-services.json'
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
$viteEntry = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $pythonExe)) {
  throw "Backend virtual environment was not found: $pythonExe"
}
if (-not $nodeCommand) {
  throw 'Node.js was not found. Install Node.js or add it to PATH.'
}
if (-not (Test-Path -LiteralPath $viteEntry)) {
  throw "Frontend dependencies were not found: $viteEntry. Install dependencies in frontend first."
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

function Test-Endpoint([string]$Uri) {
  try {
    $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
  } catch {
    return $false
  }
}

function Get-ListenerPid([int]$Port) {
  $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) { return [int]$listener.OwningProcess }
  return $null
}

function Wait-Endpoint([string]$Name, [string]$Uri, [int]$Attempts = 40) {
  for ($attempt = 1; $attempt -le $Attempts; $attempt += 1) {
    if (Test-Endpoint $Uri) { return }
    Start-Sleep -Milliseconds 500
  }
  throw "$Name did not become ready in time: $Uri"
}

$previousState = $null
if (Test-Path -LiteralPath $statePath) {
  try { $previousState = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json } catch { $previousState = $null }
}

$backendPid = Get-ListenerPid 8000
$backendManaged = $false
if (Test-Endpoint 'http://127.0.0.1:8000/api/v1/health') {
  if ($previousState -and $previousState.backend.pid -eq $backendPid) { $backendManaged = [bool]$previousState.backend.managed }
  Write-Host 'Backend is healthy; reusing the running service.'
} else {
  if ($backendPid) { throw "Port 8000 is occupied by process $backendPid, but its health check failed." }
  $backendProcess = Start-Process -FilePath $pythonExe `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
    -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeDir 'backend.out.log') `
    -RedirectStandardError (Join-Path $runtimeDir 'backend.err.log')
  $backendPid = $backendProcess.Id
  $backendManaged = $true
  Wait-Endpoint 'Backend' 'http://127.0.0.1:8000/api/v1/health'
  $backendPid = Get-ListenerPid 8000
  if (-not $backendPid) { throw 'Backend became healthy, but no listener was found on port 8000.' }
  Write-Host "Backend started with PID $backendPid."
}

$frontendPid = Get-ListenerPid 8080
$frontendManaged = $false
if (Test-Endpoint 'http://127.0.0.1:8080/') {
  if ($previousState -and $previousState.frontend.pid -eq $frontendPid) { $frontendManaged = [bool]$previousState.frontend.managed }
  Write-Host 'Frontend is healthy; reusing the running service.'
} else {
  if ($frontendPid) { throw "Port 8080 is occupied by process $frontendPid, but the page check failed." }
  $frontendProcess = Start-Process -FilePath $nodeCommand.Source `
    -ArgumentList @($viteEntry, '--host', '127.0.0.1', '--port', '8080', '--strictPort') `
    -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeDir 'frontend.out.log') `
    -RedirectStandardError (Join-Path $runtimeDir 'frontend.err.log')
  $frontendPid = $frontendProcess.Id
  $frontendManaged = $true
  Wait-Endpoint 'Frontend' 'http://127.0.0.1:8080/'
  $frontendPid = Get-ListenerPid 8080
  if (-not $frontendPid) { throw 'Frontend became healthy, but no listener was found on port 8080.' }
  Write-Host "Frontend started with PID $frontendPid."
}

@{
  started_at = (Get-Date).ToString('o')
  backend = @{ pid = $backendPid; managed = $backendManaged; url = 'http://127.0.0.1:8000' }
  frontend = @{ pid = $frontendPid; managed = $frontendManaged; url = 'http://127.0.0.1:8080' }
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host ''
Write-Host 'Job graph services are ready:'
Write-Host '  Frontend: http://127.0.0.1:8080/'
Write-Host '  Health:   http://127.0.0.1:8000/api/v1/health'
Write-Host "  Logs:     $runtimeDir"
