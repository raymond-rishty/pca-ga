param(
    [ValidateSet('check', 'preflight', 'run', 'collect', 'status')]
    [string]$Action = 'status',
    [string]$Campaign = 'index/synopsis_workflow/sol-calibration-1',
    [ValidateRange(1, 100)][int]$MaxBatches = 1,
    [ValidateRange(1, 86400)][int]$TimeoutSeconds = 1200,
    [switch]$ConfirmWorkerStopped
)
$ErrorActionPreference = 'Stop'
$runnerRoot = Split-Path -Parent $PSScriptRoot
$runnerPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $runnerPython)) {
    $runnerPython = (Get-Command python -ErrorAction Stop).Source
}
$runnerArgs = @((Join-Path $PSScriptRoot 'run_synopses.py'), $Action,
    '--campaign', $Campaign, '--max-batches', $MaxBatches,
    '--timeout-seconds', $TimeoutSeconds)
if ($ConfirmWorkerStopped) { $runnerArgs += '--confirm-worker-stopped' }
Push-Location $runnerRoot
try {
    & $runnerPython @runnerArgs
    $runnerExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $runnerExitCode
