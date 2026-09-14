param(
    [ValidateSet('run', 'payload')][string]$Action = 'run',
    [string]$Campaign = 'index/synopsis_workflow/sol-calibration-1',
    [ValidateRange(1, 100)][int]$MaxCases = 1,
    [ValidateRange(1, 86400)][int]$TimeoutSeconds = 900,
    [string]$Case
)
$ErrorActionPreference = 'Stop'
$compactRoot = Split-Path -Parent $PSScriptRoot
$compactPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $compactPython)) {
    $compactPython = (Get-Command python -ErrorAction Stop).Source
}
$compactArgs = @((Join-Path $PSScriptRoot 'run_synopses_compact.py'), $Action,
    '--campaign', $Campaign, '--max-cases', $MaxCases,
    '--timeout-seconds', $TimeoutSeconds)
if ($Case) { $compactArgs += @('--case', $Case) }
Push-Location $compactRoot
try {
    & $compactPython @compactArgs
    $compactExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $compactExitCode
