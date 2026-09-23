#!/usr/bin/env python3
"""Serve the generated Jekyll site locally under its configured /pca-ga baseurl."""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


BASE_URL = "/pca-ga"


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/":
            self.send_response(302)
            self.send_header("Location", f"{BASE_URL}/")
            self.end_headers()
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        parsed = urlsplit(path)
        request_path = parsed.path
        if request_path == BASE_URL:
            request_path = "/"
        elif request_path.startswith(BASE_URL + "/"):
            request_path = request_path[len(BASE_URL) :]
        local_url = urlunsplit(("", "", request_path, parsed.query, parsed.fragment))
        return super().translate_path(local_url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_site = Path("_site")
    tools_root = Path(os.environ.get("PCA_GA_BUILD_TOOLS", ""))
    if tools_root and (tools_root / "site" / "index.html").is_file():
        default_site = tools_root / "site"
    parser.add_argument("--site", type=Path, default=default_site, help="Jekyll output directory")
    parser.add_argument("--port", type=int, default=8000, help="Local preview port (default: 8000)")
    args = parser.parse_args()

    site = args.site.resolve()
    if not (site / "index.html").is_file():
        parser.error(f"{site} has no index.html; run scripts/build-local.ps1 first")

    handler = partial(PreviewHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Previewing {site} at http://127.0.0.1:{args.port}{BASE_URL}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPreview stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
