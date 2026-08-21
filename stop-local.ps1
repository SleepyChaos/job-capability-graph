[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$statePath = Join-Path $repoRoot '.runtime\local-services.json'
if (-not (Test-Path -LiteralPath $statePath)) {
  Write-Host 'No services recorded by start-local.ps1 were found.'
  exit 0
}

$state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
foreach ($serviceName in @('frontend', 'backend')) {
  $service = $state.$serviceName
  if (-not $service.managed) {
    Write-Host "$serviceName was not created by start-local.ps1 and will remain running."
    continue
  }
  $process = Get-Process -Id ([int]$service.pid) -ErrorAction SilentlyContinue
  if ($process) {
    Stop-Process -Id $process.Id
    Write-Host "$serviceName stopped (PID $($process.Id))."
  }
}

Remove-Item -LiteralPath $statePath -Force
