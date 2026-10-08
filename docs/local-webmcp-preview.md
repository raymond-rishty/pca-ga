# Preview the WebMCP pull requests

The Pages workflow builds pull requests but only deploys pushes to `main`, so a PR does not get a public preview URL. To preview both WebMCP changes together, build the Assembly site and serve it alongside the Reader branch from your own computer.

## Check out the pull requests

Run these commands from a directory where you want the two repositories:

```bash
git clone https://github.com/raymond-rishty/pca-ga.git
git -C pca-ga fetch origin pull/223/head:preview-webmcp
git -C pca-ga switch preview-webmcp

git clone https://github.com/raymond-rishty/pca-constitution-reader.git
git -C pca-constitution-reader fetch origin pull/20/head:preview-webmcp
git -C pca-constitution-reader switch preview-webmcp
```

## Build and serve them together

Install the prerequisites in [the local build guide](local-build.md), then build the Assembly site:

```bash
cd pca-ga
pwsh ./scripts/build-local.ps1 -Incremental
cd ..
```

Combine the built Assembly site and the Reader PR in a temporary directory, then serve it:

```bash
preview_dir="$(mktemp -d)"
mkdir -p "$preview_dir/pca-ga"
cp -a pca-ga/_site/. "$preview_dir/pca-ga/"
git -C pca-constitution-reader archive preview-webmcp | tar -x -C "$preview_dir"
python3 -m http.server 8000 --directory "$preview_dir"
```

Open <http://localhost:8000/> for the Constitution Reader or <http://localhost:8000/pca-ga/ask.html> for the Ask page. The Reader detects localhost and fetches the prompt from the locally served Assembly build. Use a browser that implements WebMCP to inspect the registered tools. Stop the server with `Ctrl+C`.
