# Build the site locally

Run the Gradle task graph used by the GitHub Pages workflow before pushing:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build-local.ps1
```

The execution-policy command only applies to the current PowerShell process. If PowerShell already permits local scripts, run just the second command. To use an existing checkout of the [PCA Constitution Reader](https://github.com/raymond-rishty/pca-constitution-reader), pass its path:

```powershell
.\scripts\build-local.ps1 -ConstitutionPath C:\path\to\pca-constitution-reader
```

Without that option, the script reuses a checkout at `_constitution` if present. If `PCA_GA_BUILD_TOOLS` is set, it otherwise uses a persistent checkout at `$PCA_GA_BUILD_TOOLS/pca-constitution-reader`; without that setting, it clones the reader at `_constitution`. These stable paths keep Gradle task arguments consistent between builds. The `_constitution` checkout is ignored by Git.

Gradle's input/output tracking reuses unchanged generated-data tasks and skips the render pipeline when its inputs and output files are unchanged. Validation tasks still run on each invocation. The final site is not stored in Gradle's task-output cache. GitHub Actions keeps a separate rendered-site cache so later CI runs can reuse Jekyll output and per-page link results.

For a quick local edit/preview cycle, use the incremental task:

```powershell
.\scripts\build-local.ps1 -Incremental
```

This refreshes the generated data needed by the site, then keeps Jekyll's incremental metadata, provision pages, and per-page citation results between runs. Gradle skips data generators whose inputs and outputs are unchanged. The fast task omits the full validation chain, which the default build still runs. It updates stale pages and their citation audits, then leaves the existing Pagefind index in place so the edit loop does not re-index the whole site. Search results therefore reflect the last full build; pass `-RefreshSearch` when you need a fresh index.

Jekyll's incremental regeneration is experimental and cannot see every cross-page dependency. Changes to layouts, includes, Sass, plugins, configuration, dependencies, or global citation targets force a full render. Use the default command before pushing. CI restores a rendered-site cache, incrementally renders stale pages, rebuilds Pagefind, and runs the full site validator. A cold CI cache takes the full bootstrap build; later runs reuse the previous site's output.

If you changed the curated overture-source files that trigger regeneration in CI, run:

```powershell
.\scripts\build-local.ps1 -RegenerateOvertures
```

## Prerequisites

- Git
- Java 17 or newer (the Gradle Wrapper downloads the pinned Gradle distribution on first use)
- Python 3 and `openpyxl` (`python -m pip install openpyxl`)
- Node.js (including `npx`)
- Ruby 3.3 and Bundler (`gem install bundler`)

Install the Ruby dependencies once from the repository root:

```powershell
bundle install
```

Gradle caches deterministic, isolated generator outputs in its local build cache. GitHub Actions also preserves Gradle's cache and a separate rendered-site cache between CI runs; no Develocity account is required. Checking in generated files alone does not transfer a developer's local cache to CI. GitHub's Actions cache has repository storage and retention limits, so the rendered-site cache is separate from Gradle's build cache.

The local wrapper runs the focused checks from CI and builds the Pagefind search index. It uses `_site/` by default, or a separate directory under `$env:PCA_GA_BUILD_TOOLS` when that variable is configured. To preview it locally after the build, run:

```powershell
python scripts/preview_local.py
```

Then open <http://127.0.0.1:8000/pca-ga/>. The preview serves the built files under the site's configured `/pca-ga` base URL, so its links and assets resolve as they do on GitHub Pages. Stop the server with `Ctrl+C`. Review generated file changes before committing. Overture regeneration is opt-in because its legacy extractor can overwrite curated overture data; CI only runs it when the overture-source artifacts change.
