[CmdletBinding()]
param(
    [string]$PythonExe,
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$server = Join-Path $PSScriptRoot 'synopsis_review_server.py'
$prioritizer = Join-Path $PSScriptRoot '79_prioritize_synopsis_review.py'

function Resolve-PythonExecutable {
    param([string]$ExplicitPath)
    if ($ExplicitPath) { return (Resolve-Path -LiteralPath $ExplicitPath).Path }
    if ($env:PCA_GA_PYTHON -and (Test-Path -LiteralPath $env:PCA_GA_PYTHON)) {
        return (Resolve-Path -LiteralPath $env:PCA_GA_PYTHON).Path
    }
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCommand) {
        $nodeRoot = Split-Path -Parent (Split-Path -Parent $nodeCommand.Source)
        $bundled = Join-Path (Split-Path -Parent $nodeRoot) 'python\python.exe'
        if (Test-Path -LiteralPath $bundled) { return (Resolve-Path -LiteralPath $bundled).Path }
    }
    foreach ($name in @('python3', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    throw 'Python 3 was not found. Set PCA_GA_PYTHON or pass -PythonExe.'
}

$python = Resolve-PythonExecutable -ExplicitPath $PythonExe
$arguments = @($server, '--port', $Port)
if (-not $NoBrowser) { $arguments += '--open' }

Push-Location $repositoryRoot
try {
    & $python $prioritizer
    if ($LASTEXITCODE -ne 0) {
        throw "Synopsis review prioritization failed with exit code $LASTEXITCODE."
    }
    & $python @arguments
}
finally {
    Pop-Location
}
