#!/usr/bin/env python3
"""Compatibility entry point for build-time extracted-page enrichment."""
from __future__ import annotations

from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from source_links import run


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=SCRIPTS.parent)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.root, args.check))
