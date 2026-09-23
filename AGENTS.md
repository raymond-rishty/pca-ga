# Repository guidance

## Local site builds and previews

- For changes that affect site rendering, frontend behavior, generated search assets, or GitHub Pages output, build and validate locally with `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build-local.ps1` before calling the work ready for push, pull request, or merge.
- Review the generated changes in `git status` and the affected pages in the local preview at `http://127.0.0.1:8000/pca-ga/`. Start it with `python scripts/preview_local.py` after a successful build; stop it with Ctrl+C.
- The local build needs the tools and packages listed in [docs/local-build.md](docs/local-build.md). If a required dependency is unavailable, report that and do not claim the build passed.
- If curated overture-source artifacts changed, include `-RegenerateOvertures` when running the local build. The extractor is deliberately opt-in because it can replace curated data.
- The build regenerates checked-in files. Preserve existing user changes and inspect every generated diff before staging or reverting anything.
