[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Preflight', 'Submit', 'Retry', 'Status', 'Download', 'Ingest')]
    [string]$Action = 'Preflight',

    [ValidateRange(1, 999)]
    [int]$Shard,

    [string]$PythonExe,

    [string]$Campaign = 'index/synopsis_workflow/openai-sol-deepseek-failures-1'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$batchCli = Join-Path $PSScriptRoot 'synopsis_batch_api.py'
$candidateIngestCli = Join-Path $PSScriptRoot 'synopsis_candidate_ingest.py'

function Resolve-PythonExecutable {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
            throw "Python executable not found: $ExplicitPath"
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    if ($env:PCA_GA_PYTHON -and
        (Test-Path -LiteralPath $env:PCA_GA_PYTHON -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $env:PCA_GA_PYTHON).Path
    }

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCommand) {
        $nodeDirectory = Split-Path -Parent $nodeCommand.Source
        $nodeRoot = Split-Path -Parent $nodeDirectory
        $dependenciesRoot = Split-Path -Parent $nodeRoot
        $bundledPython = Join-Path $dependenciesRoot 'python\python.exe'
        if (Test-Path -LiteralPath $bundledPython -PathType Leaf) {
            return (Resolve-Path -LiteralPath $bundledPython).Path
        }
    }

    $virtualEnvironmentPython = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $virtualEnvironmentPython -PathType Leaf) {
        return (Resolve-Path -LiteralPath $virtualEnvironmentPython).Path
    }

    foreach ($name in @('python3', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }

    throw 'Python 3 was not found. Set PCA_GA_PYTHON or pass -PythonExe with its full path.'
}

function Set-ProcessApiKeyIfNeeded {
    if ($env:OPENAI_API_KEY) {
        return $false
    }

    $secureKey = Read-Host 'OpenAI API key (used for this process only; not saved)' -AsSecureString
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
        if ([string]::IsNullOrWhiteSpace($plainKey)) {
            throw 'No API key was supplied.'
        }
        $env:OPENAI_API_KEY = $plainKey.Trim()
        return $true
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    }
}

$remoteActions = @('Submit', 'Retry', 'Status', 'Download')
if ($remoteActions -contains $Action -and -not $PSBoundParameters.ContainsKey('Shard')) {
    throw "$Action requires -Shard 1, -Shard 2, or -Shard 3."
}

$python = Resolve-PythonExecutable -ExplicitPath $PythonExe
$arguments = @($batchCli, '--campaign', $Campaign)
$keyWasPrompted = $false

switch ($Action) {
    'Preflight' { $arguments += 'preflight' }
    'Submit' {
        $keyWasPrompted = Set-ProcessApiKeyIfNeeded
        $arguments += @('submit', '--shard', $Shard)
    }
    'Retry' {
        $keyWasPrompted = Set-ProcessApiKeyIfNeeded
        $arguments += @('retry', '--shard', $Shard)
    }
    'Status' {
        $keyWasPrompted = Set-ProcessApiKeyIfNeeded
        $arguments += @('status', '--shard', $Shard)
    }
    'Download' {
        $keyWasPrompted = Set-ProcessApiKeyIfNeeded
        $arguments += @('download', '--shard', $Shard)
    }
    'Ingest' { $arguments += 'ingest' }
}

Push-Location $repositoryRoot
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Synopsis Batch API command failed with exit code $LASTEXITCODE."
    }
    if ($Action -eq 'Ingest') {
        & $python $candidateIngestCli
        if ($LASTEXITCODE -ne 0) {
            throw "Combined candidate intake failed with exit code $LASTEXITCODE."
        }
    }
}
finally {
    Pop-Location
    if ($keyWasPrompted) {
        Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    }
}
