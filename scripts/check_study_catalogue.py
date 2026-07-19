#!/usr/bin/env python3
"""Fast integrity check for the published study catalogue.

This validates the committed publication artifacts only. It deliberately does
not extract reports, regenerate pages, or scan the corpus, so it is safe to run
before every Pages build and on relevant pull requests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_json(path: Path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"ERROR: cannot read {path}: {error}") from error
    if not isinstance(value, list):
        raise SystemExit(f"ERROR: {path} must contain a JSON array")
    return value


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    manifest = load_json(root / "index" / "studies_pages.json")
    search = load_json(root / "app" / "search_index.json")
    errors: list[str] = []

    manifest_urls: set[str] = set()
    for position, record in enumerate(manifest, start=1):
        filename = record.get("file") if isinstance(record, dict) else None
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            errors.append(f"manifest record {position}: missing or unsafe file name {filename!r}")
            continue
        url = f"studies/{filename}"
        if url in manifest_urls:
            errors.append(f"manifest: duplicate study file {url}")
            continue
        manifest_urls.add(url)
        if not (root / url).is_file():
            errors.append(f"manifest: missing study page {url}")

    study_cards = [record for record in search
                   if isinstance(record, dict) and record.get("type") == "Position paper"]
    card_urls: set[str] = set()
    for position, record in enumerate(study_cards, start=1):
        url = record.get("url")
        if not isinstance(url, str) or not url.startswith("studies/") or not url.endswith(".md"):
            errors.append(f"study search card {position}: invalid URL {url!r}")
            continue
        if url in card_urls:
            errors.append(f"study search cards: duplicate target {url}")
            continue
        card_urls.add(url)
        if url not in manifest_urls:
            errors.append(f"study search card {position}: target is absent from manifest: {url}")

    for url in sorted(manifest_urls - card_urls):
        errors.append(f"manifest study is absent from search: {url}")

    if errors:
        print("Study catalogue integrity check failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1

    print(f"Study catalogue OK: {len(manifest_urls)} manifest records, "
          f"{len(study_cards)} search cards, all local targets present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
