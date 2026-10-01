"""Fingerprint code and reader inputs that determine rendered link targets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preflight_linker_fingerprint(root: Path, reader_content: Path) -> str | None:
    """Return the stable linker-input hash without reading rendered HTML."""
    scripts = root / "scripts"
    inputs = {
        "linker": scripts / "44_link_constitution_refs.py",
        "normalizer": scripts / "44_normalize_bco_prefixes.py",
        "scriptureLinker": scripts / "scripture_linker.py",
        "minutesMarkup": scripts / "46_minutes_page_markup.py",
        "minutesLocators": scripts / "minutes_page_locators.py",
        "renderSite": scripts / "render_site.py",
        "script": scripts / "linker_fingerprint.py",
        "scriptureMetadata": root / "scripture" / "bible-books.json",
        "readerBco": reader_content / "bco.js",
        "readerWcf": reader_content / "wcf.js",
        "readerWlc": reader_content / "wlc.js",
        "readerWsc": reader_content / "wsc.js",
        "readerRao": reader_content / "rao.js",
    }
    if any(not path.is_file() for path in inputs.values()):
        return None
    values = {name: _sha256(path) for name, path in inputs.items()}
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
