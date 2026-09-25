[CmdletBinding()]
param(
    [string]$ConstitutionPath,
    [string]$SiteDirectory,
    [switch]$RegenerateOvertures
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
$temporaryConstitutionPath = $null

if (-not $env:PCA_GA_BUILD_TOOLS) {
    $env:PCA_GA_BUILD_TOOLS = [Environment]::GetEnvironmentVariable('PCA_GA_BUILD_TOOLS', 'User')
}
if ($env:PCA_GA_BUILD_TOOLS) {
    $toolsRoot = $env:PCA_GA_BUILD_TOOLS
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $localToolPaths = @(
        (Join-Path $toolsRoot 'node-v24.19.0-win-x64'),
        (Join-Path $toolsRoot 'Ruby33\bin'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python')
    )
    $env:Path = (($localToolPaths + @($userPath -split ';') + @($env:Path -split ';') | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique) -join ';')
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

function Invoke-BuildStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    Write-Host "`n==> $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Build step failed with exit code ${LASTEXITCODE}: $Name"
    }
}

function Assert-File {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Expected build output was not created: $Path"
    }
}

try {
    foreach ($command in @('python', 'node', 'bundle', 'npx', 'git')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Required command '$command' was not found. See docs/local-build.md for prerequisites."
        }
    }
    $env:PYTHON = (Get-Command python).Source

    if (-not $ConstitutionPath) {
        $ConstitutionPath = Join-Path $repoRoot '_constitution'
        if (-not (Test-Path -LiteralPath (Join-Path $ConstitutionPath 'content'))) {
            $temporaryConstitutionPath = Join-Path ([IO.Path]::GetTempPath()) ("pca-ga-constitution-" + [guid]::NewGuid().ToString('N'))
            Invoke-BuildStep 'Fetch the PCA Constitution Reader source' {
                git -c http.sslBackend=schannel -c http.sslCAInfo= clone --depth 1 https://github.com/raymond-rishty/pca-constitution-reader.git $temporaryConstitutionPath
            }
            $ConstitutionPath = $temporaryConstitutionPath
        }
    }
    $ConstitutionPath = (Resolve-Path -LiteralPath $ConstitutionPath).Path
    foreach ($file in @('bco.js', 'wcf.js', 'wlc.js', 'wsc.js', 'rao.js')) {
        Assert-File (Join-Path $ConstitutionPath "content/$file")
    }

    Invoke-BuildStep 'Check Python build dependencies' {
        python -c "import openpyxl"
    }
    Invoke-BuildStep 'Check Ruby dependencies' {
        bundle check
    }

    # Match the deterministic generation and validation steps in .github/workflows/pages.yml.
    # The legacy overture extractor is opt-in because it can overwrite curated overture data.
    if ($RegenerateOvertures) {
        Invoke-BuildStep 'Regenerate overture pages from Minutes source' {
            python scripts/21_overture_titles.py extract .
            if ($LASTEXITCODE -ne 0) { throw "Overture title extraction failed: $LASTEXITCODE" }
            python scripts/37_overture_pages.py .
        }
    }
    Invoke-BuildStep 'Reconcile judicial case artifacts' {
        python scripts/27_case_index_reconcile.py
    }
    Invoke-BuildStep 'Synchronize case-page cards' {
        python scripts/84_sync_case_page_metadata.py .
    }
    Invoke-BuildStep 'Regenerate judicial case catalogue' {
        python scripts/13_judicial_taxonomy_index.py .
    }
    Invoke-BuildStep 'Regenerate auditable judicial provision evidence' {
        python scripts/44_case_provision_index.py .
    }
    Invoke-BuildStep 'Build the shared provision catalogue' {
        python scripts/build_provision_catalogue.py . (Join-Path $ConstitutionPath 'content')
        if ($LASTEXITCODE -ne 0) { throw "Provision catalogue build failed: $LASTEXITCODE" }
        Assert-File 'index/provision_catalogue.json'
    }
    Invoke-BuildStep 'Project the authority index from the provision catalogue' {
        python scripts/43_authority_index.py .
        if ($LASTEXITCODE -ne 0) { throw "Authority projection failed: $LASTEXITCODE" }
    }
    Invoke-BuildStep 'Write the authority-index audit report' {
        python scripts/47_authority_index_audit.py .
        if ($LASTEXITCODE -ne 0) { throw "Authority-index audit failed: $LASTEXITCODE" }
        Assert-File 'index/authority_index_audit.json'
        Assert-File 'index/AUTHORITY-INDEX-AUDIT.md'
    }
    Invoke-BuildStep 'Rebuild catalogue search index' {
        python scripts/35_search_index.py .
    }
    Invoke-BuildStep 'Generate BCO provision manifests' {
        python scripts/45_bco_manifests.py . --out api/bco
    }
    Invoke-BuildStep 'Regenerate LLM distribution' {
        python scripts/34_llm_pack.py .
    }
    Invoke-BuildStep 'Validate study catalogue' {
        python scripts/check_study_catalogue.py .
    }
    Invoke-BuildStep 'Restore Minutes source PDF provenance' {
        python scripts/ensure_minutes_source_pdf_metadata.py
        if ($LASTEXITCODE -ne 0) { throw "Minutes PDF metadata restore failed: $LASTEXITCODE" }
        python scripts/ensure_minutes_source_pdf_metadata.py --check
    }
    Invoke-BuildStep 'Run source PDF metadata checks' {
        python tests/test_minutes_source_pdf_metadata.py
        if ($LASTEXITCODE -ne 0) { throw "Minutes PDF metadata check failed: $LASTEXITCODE" }
        python tests/test_extracted_source_pdf_metadata.py
    }
    Invoke-BuildStep 'Rebuild and validate extracted source registry' {
        python scripts/build_source_registry.py . --write
        if ($LASTEXITCODE -ne 0) { throw "Source registry build failed: $LASTEXITCODE" }
        python scripts/build_source_registry.py . --check
    }
    Invoke-BuildStep 'Run source registry checks' {
        python tests/test_source_registry.py
    }
    Invoke-BuildStep 'Test provision research generator' {
        python tests/test_provision_research.py
    }
    Invoke-BuildStep 'Test provision catalogue projections' {
        python tests/test_provision_catalogue.py
    }
    Invoke-BuildStep 'Test authority-index feedback regressions' {
        python tests/test_authority_index_feedback.py
    }
    Invoke-BuildStep 'Run focused Node regression checks' {
        node --test tests/source-pdf-links.test.js tests/minutes-back-to-top.test.js tests/minutes-page-source-pdf.test.js tests/search-engine.test.js tests/search-record.test.js tests/search-index-overtures.test.js tests/pagefind-search.test.js
    }
    Invoke-BuildStep 'Add source PDF metadata to extracted documents' {
        python scripts/add_extracted_source_pdf_metadata.py .
    }
    Invoke-BuildStep 'Validate footnote pairing' {
        python scripts/81_validate_footnote_integrity.py
    }
    Invoke-BuildStep 'Build the Jekyll site' {
        bundle exec jekyll build --destination $siteRoot
    }

    Invoke-BuildStep 'Validate generated BCO manifests' {
        Assert-File (Join-Path $siteRoot 'api/bco/index.json')
        Assert-File (Join-Path $siteRoot 'api/bco/38-1.json')
        Assert-File (Join-Path $siteRoot 'api/provisions/index.json')
        Assert-File (Join-Path $siteRoot 'api/provisions/bco/38-1.json')
        $manifest = Get-Content (Join-Path $siteRoot 'api/bco/38-1.json') -Raw
        $canonical = Get-Content (Join-Path $siteRoot 'api/provisions/bco/38-1.json') -Raw
        $bcoIndex = Get-Content (Join-Path $siteRoot 'api/bco/index.json') -Raw
        $llms = Get-Content (Join-Path $siteRoot 'llms.txt') -Raw
        if ($manifest -cne $canonical -or $manifest -notmatch '"schema_version"\s*:\s*3' -or
            $bcoIndex -notmatch '"schema_version"\s*:\s*3' -or $llms -notmatch '/api/provisions/index.json') {
            throw 'The generated schema-v3 provision API, BCO compatibility copy, or llms.txt reference is missing.'
        }
    }
    Invoke-BuildStep 'Validate rendered extracted source PDF links' {
        $extractedPages = @(
            Get-ChildItem (Join-Path $siteRoot 'cases'), (Join-Path $siteRoot 'inquiries'), (Join-Path $siteRoot 'overtures'), (Join-Path $siteRoot 'rpr/exc'), (Join-Path $siteRoot 'studies') -Filter '*.html' -File -Recurse -ErrorAction SilentlyContinue
        )
        $linkedPages = @($extractedPages | Where-Object { (Get-Content $_.FullName -Raw) -match 'class="source-pdf-link"' })
        if ($linkedPages.Count -lt 1) { throw 'No rendered extracted page exposes a source PDF link.' }
        $casePages = Get-ChildItem (Join-Path $siteRoot 'cases') -Filter '*.html' -File -Recurse -ErrorAction SilentlyContinue
        $studyPages = Get-ChildItem (Join-Path $siteRoot 'studies') -Filter '*.html' -File -Recurse -ErrorAction SilentlyContinue
        if (-not (Select-String -Path $casePages.FullName -Pattern '51st_pcaga_2024.pdf#page=749' -Quiet)) {
            throw 'Expected GA51 case source PDF page link was not rendered.'
        }
        foreach ($directory in @('cases', 'inquiries', 'overtures', 'rpr', 'studies')) {
            $htmlFiles = Get-ChildItem (Join-Path $siteRoot $directory) -Filter '*.html' -File -Recurse -ErrorAction SilentlyContinue
            if (-not (Select-String -Path $htmlFiles.FullName -Pattern 'data-source-pdf-actions' -Quiet)) {
                throw "No source-PDF page action rendered for $directory."
            }
        }
        if (-not (Select-String -Path $casePages.FullName -Pattern 'data-source-id="case-pdf:' -Quiet)) { throw 'No dedicated judicial source PDF was rendered.' }
        if (-not (Select-String -Path $studyPages.FullName -Pattern 'data-source-id="study-pdf:' -Quiet)) { throw 'No dedicated study source PDF was rendered.' }
        if (Select-String -Path $extractedPages.FullName -Pattern 'class="source-pdf-link" href=""' -Quiet) { throw 'An extracted source PDF link has an empty href.' }
    }
    Invoke-BuildStep 'Validate all rendered Minutes source PDF links' {
        $volumePages = @(Get-ChildItem (Join-Path $siteRoot 'markdown') -Filter 'ga??_????.html' -File -ErrorAction SilentlyContinue)
        if ($volumePages.Count -ne 52) { throw "Expected 52 rendered Minutes volumes, found $($volumePages.Count)." }
        foreach ($page in $volumePages) {
            if (-not (Select-String -LiteralPath $page.FullName -Pattern 'class="source-pdf-link" href="https://www\.pcahistory\.org/pca/ga/[0-9]+(st|nd|rd|th)_pcaga_[0-9]{4}\.pdf"' -Quiet)) {
                throw "Missing canonical source PDF link in $($page.Name)."
            }
        }
    }

    Invoke-BuildStep 'Link constitutional references' {
        python scripts/build_bsb_assets.py --check
        if ($LASTEXITCODE -ne 0) { throw "BSB asset check failed: $LASTEXITCODE" }
        python scripts/44_normalize_bco_prefixes.py $siteRoot
        if ($LASTEXITCODE -ne 0) { throw "BCO prefix normalization failed: $LASTEXITCODE" }
        python scripts/44_link_constitution_refs.py $siteRoot `
            (Join-Path $ConstitutionPath 'content/bco.js') `
            (Join-Path $ConstitutionPath 'content/wcf.js') `
            (Join-Path $ConstitutionPath 'content/wlc.js') `
            (Join-Path $ConstitutionPath 'content/wsc.js') `
            (Join-Path $ConstitutionPath 'content/rao.js')
    }
    Invoke-BuildStep 'Validate constitutional reference output' {
        foreach ($path in @(
            'assets/constitution/bco-index.json',
            'assets/constitution/standards/wcf.json',
            'assets/constitution/standards/wlc.json',
            'assets/constitution/standards/wsc.json',
            'assets/constitution/packs/rao.json',
            'assets/minutes-pages.json',
            'assets/scripture-audit.json',
            'assets/scripture-audit-summary.json',
            'assets/scripture/bsb/John/3.json'
        )) { Assert-File (Join-Path $siteRoot $path) }
        $allPages = Get-ChildItem $siteRoot -Filter '*.html' -File -Recurse
        if (-not (Select-String -Path $allPages.FullName -Pattern 'data-bco-ref=' -Quiet)) { throw 'No linked BCO references were rendered.' }
        if (-not (Select-String -Path $allPages.FullName -Pattern 'class="constitution-ref"' -Quiet)) { throw 'No constitution reference previews were rendered.' }
        if (-not (Select-String -Path $allPages.FullName -Pattern 'data-constitution-book="rao"' -Quiet)) { throw 'No RAO reference was rendered.' }
        if (-not (Select-String -Path $allPages.FullName -Pattern 'class="minutes-ref"' -Quiet)) { throw 'No Minutes reference was rendered.' }
        if (-not (Select-String -Path $allPages.FullName -Pattern 'class="scripture-ref"' -Quiet)) { throw 'No scripture reference was rendered.' }
    }
    Invoke-BuildStep 'Generate canonical provision research pages' {
        python scripts/46_provision_research.py site . $siteRoot --baseurl /pca-ga
        if ($LASTEXITCODE -ne 0) { throw "Provision research pages failed: $LASTEXITCODE" }
        Assert-File (Join-Path $siteRoot 'provisions/index.html')
        Assert-File (Join-Path $siteRoot 'provisions/bco/40-1/index.html')
        Assert-File (Join-Path $siteRoot 'provisions/wlc/q-62/index.html')
        Assert-File (Join-Path $siteRoot 'provisions/rao/1-1/index.html')
        Assert-File (Join-Path $siteRoot 'app/provision_search.json')
    }
    Invoke-BuildStep 'Build Pagefind full-text index' {
        npx --yes pagefind@1.5.2 --site $siteRoot
    }
    Invoke-BuildStep 'Validate Pagefind index' {
        if (-not (Select-String -Path (Join-Path $siteRoot 'markdown/*.html') -Pattern 'data-pagefind-body' -Quiet)) { throw 'The rendered Minutes pages have no Pagefind body markers.' }
        if (-not (Select-String -Path (Join-Path $siteRoot 'markdown/*.html') -Pattern 'content="General Assembly minutes"' -Quiet)) { throw 'The rendered Minutes pages have no Pagefind title metadata.' }
        Assert-File (Join-Path $siteRoot 'pagefind/pagefind.js')
        $pagefindFiles = @(Get-ChildItem (Join-Path $siteRoot 'pagefind') -File -Recurse)
        if ($pagefindFiles.Count -le 5) { throw "Pagefind produced only $($pagefindFiles.Count) files." }
    }

    Write-Host "`nLocal site build complete. Preview files from $siteRoot" -ForegroundColor Green
}
finally {
    Pop-Location
    if ($temporaryConstitutionPath -and (Test-Path -LiteralPath $temporaryConstitutionPath)) {
        Remove-Item -LiteralPath $temporaryConstitutionPath -Recurse -Force
    }
}
