[CmdletBinding()]
param(
    [string]$ConstitutionPath,
    [string]$SiteDirectory,
    [switch]$RegenerateOvertures,
    [switch]$Incremental,
    [switch]$RefreshSearch,
    [switch]$Scan
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$temporaryConstitutionPath = $null

if (-not $env:PCA_GA_BUILD_TOOLS) {
    $env:PCA_GA_BUILD_TOOLS = [Environment]::GetEnvironmentVariable('PCA_GA_BUILD_TOOLS', 'User')
}
if ($env:PCA_GA_BUILD_TOOLS) {
    $toolsRoot = $env:PCA_GA_BUILD_TOOLS
    $localJavaHome = Join-Path $toolsRoot 'jdk-17'
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $localToolPaths = @(
        (Join-Path $toolsRoot 'jdk-17\bin'),
        (Join-Path $toolsRoot 'node-v24.19.0-win-x64'),
        (Join-Path $toolsRoot 'Ruby33\bin'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python')
    )
    $env:Path = (($localToolPaths + @($userPath -split ';') + @($env:Path -split ';') | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique) -join ';')
    if (Test-Path -LiteralPath (Join-Path $localJavaHome 'bin\java.exe') -PathType Leaf) {
        $env:JAVA_HOME = $localJavaHome
    }
    $env:TEMP = Join-Path $toolsRoot 'tmp'
    $env:TMP = $env:TEMP
    $env:npm_config_cache = Join-Path $toolsRoot 'npm-cache'
    if (-not $env:BUNDLE_PATH) { $env:BUNDLE_PATH = Join-Path $toolsRoot 'bundle' }
    if (-not $env:BUNDLE_USER_HOME) { $env:BUNDLE_USER_HOME = Join-Path $toolsRoot 'bundle-home' }
    if (-not $SiteDirectory) { $SiteDirectory = Join-Path $toolsRoot 'site' }
}
if (-not $SiteDirectory) { $SiteDirectory = Join-Path $repoRoot '_site' }
if (-not [IO.Path]::IsPathRooted($SiteDirectory)) { $SiteDirectory = Join-Path $repoRoot $SiteDirectory }
$siteRoot = [IO.Path]::GetFullPath($SiteDirectory)

Push-Location $repoRoot
try {
    foreach ($command in @('java', 'python', 'node', 'ruby', 'bundle', 'npx', 'git')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Required command '$command' was not found. See docs/local-build.md for prerequisites."
        }
    }
    $env:PYTHON = (Get-Command python).Source
    $wrapperName = if ($IsWindows -or $env:OS -eq 'Windows_NT') { 'gradlew.bat' } else { 'gradlew' }
    $gradleWrapper = Join-Path $repoRoot $wrapperName
    if (-not (Test-Path -LiteralPath $gradleWrapper -PathType Leaf)) {
        throw 'The Gradle Wrapper is missing. Run the Gradle wrapper setup described in docs/local-build.md.'
    }

    if (-not $ConstitutionPath) {
        $repositoryConstitutionPath = Join-Path $repoRoot '_constitution'
        if (Test-Path -LiteralPath (Join-Path $repositoryConstitutionPath 'content/bco.js') -PathType Leaf) {
            $ConstitutionPath = $repositoryConstitutionPath
        } elseif ($toolsRoot) {
            $ConstitutionPath = Join-Path $toolsRoot 'pca-constitution-reader'
            if (-not (Test-Path -LiteralPath (Join-Path $ConstitutionPath 'content/bco.js') -PathType Leaf)) {
                if (Test-Path -LiteralPath $ConstitutionPath) {
                    throw "The cached Constitution Reader checkout exists but is incomplete: $ConstitutionPath"
                }
                Write-Host 'Fetching the PCA Constitution Reader source.' -ForegroundColor Cyan
                git -c http.sslBackend=schannel -c http.sslCAInfo= clone --depth 1 https://github.com/raymond-rishty/pca-constitution-reader.git $ConstitutionPath
                if ($LASTEXITCODE -ne 0) { throw "Constitution Reader checkout failed: $LASTEXITCODE" }
            }
        } else {
            $ConstitutionPath = $repositoryConstitutionPath
            if (Test-Path -LiteralPath $ConstitutionPath) {
                throw "The ignored Constitution Reader checkout exists but is incomplete: $ConstitutionPath"
            }
            Write-Host 'Fetching the PCA Constitution Reader source.' -ForegroundColor Cyan
            git -c http.sslBackend=schannel -c http.sslCAInfo= clone --depth 1 https://github.com/raymond-rishty/pca-constitution-reader.git $ConstitutionPath
            if ($LASTEXITCODE -ne 0) { throw "Constitution Reader checkout failed: $LASTEXITCODE" }
        }
    }
    $ConstitutionPath = (Resolve-Path -LiteralPath $ConstitutionPath).Path
    foreach ($file in @('bco.js', 'wcf.js', 'wlc.js', 'wsc.js', 'rao.js')) {
        if (-not (Test-Path -LiteralPath (Join-Path $ConstitutionPath "content/$file") -PathType Leaf)) {
            throw "Expected Constitution Reader input is missing: content/$file"
        }
    }

    $pythonVersion = (& python --version 2>&1 | Out-String).Trim()
    $rubyVersion = (& ruby --version 2>&1 | Out-String).Trim()
    $nodeVersion = (& node --version 2>&1 | Out-String).Trim()
    $buildTask = if ($Incremental) { 'fastPreview' } else { 'siteBuild' }
    $gradleArgs = @(
        '--build-cache',
        $buildTask,
        "-PsiteDir=$siteRoot",
        "-PconstitutionDir=$ConstitutionPath",
        '-PpythonCommand=python',
        "-PpythonVersion=$pythonVersion",
        "-PrubyVersion=$rubyVersion",
        "-PnodeVersion=$nodeVersion"
    )
    if ($RefreshSearch) {
        if (-not $Incremental) {
            throw 'RefreshSearch is only available with Incremental mode.'
        }
        $gradleArgs += '-PrefreshPreviewSearch=true'
    }
    if ($RegenerateOvertures) { $gradleArgs += '-PregenerateOvertures' }
    if ($Scan) { $gradleArgs += '--scan' }

    if ($wrapperName -eq 'gradlew.bat') {
        & $gradleWrapper @gradleArgs
    } else {
        & bash $gradleWrapper @gradleArgs
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Gradle site build failed with exit code ${LASTEXITCODE}."
    }
}
finally {
    Pop-Location
}
