# Build the site locally

Run the generation, validation, Jekyll, constitutional-linking, and Pagefind steps used by the GitHub Pages workflow before pushing:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build-local.ps1
```

The execution-policy command only applies to the current PowerShell process. If PowerShell already permits local scripts, run just the second command. To use an existing checkout of the [PCA Constitution Reader](https://github.com/raymond-rishty/pca-constitution-reader), pass its path:

```powershell
.\scripts\build-local.ps1 -ConstitutionPath C:\path\to\pca-constitution-reader
```

Without that option, the script reuses a checkout at `_constitution` if present; otherwise it clones the reader to a temporary directory and removes that directory when the build ends.

If you changed the curated overture-source files that trigger regeneration in CI, run:

```powershell
.\scripts\build-local.ps1 -RegenerateOvertures
```

## Prerequisites

- Git
- Python 3 and `openpyxl` (`python -m pip install openpyxl`)
- Node.js (including `npx`)
- Ruby 3.3 and Bundler (`gem install bundler`)

Install the Ruby dependencies once from the repository root:

```powershell
bundle install
```

The script runs the focused checks from CI and builds the Pagefind search index. It uses `_site/` by default, or a separate directory under `$env:PCA_GA_BUILD_TOOLS` when that variable is configured. To preview it locally after the build, run:

```powershell
python scripts/preview_local.py
```

Then open <http://127.0.0.1:8000/pca-ga/>. The preview serves the built files under the site's configured `/pca-ga` base URL, so its links and assets resolve as they do on GitHub Pages. Stop the server with `Ctrl+C`. Review generated file changes before committing. Overture regeneration is opt-in because its legacy extractor can overwrite curated overture data; CI only runs it when the overture-source artifacts change.
