#!/usr/bin/env python3
"""Generate index/provision_catalogue.json from curated corpus sources and Reader text."""
from __future__ import annotations

import argparse
from pathlib import Path

from provision_catalogue import build_catalogue, write_catalogue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path.cwd(), type=Path)
    parser.add_argument("reader", nargs="?", type=Path,
                        help="Constitution Reader content directory (default: ROOT/_constitution/content)")
    parser.add_argument("--out", type=Path, help="catalogue output path (default: ROOT/index/provision_catalogue.json)")
    args = parser.parse_args()
    root = args.root.resolve()
    reader_dir = (args.reader or (root / "_constitution" / "content")).resolve()
    output = (args.out or (root / "index" / "provision_catalogue.json")).resolve()
    if not reader_dir.is_dir():
        parser.error(f"Reader content directory does not exist: {reader_dir}")
    catalogue = build_catalogue(root, reader_dir)
    write_catalogue(output, catalogue)
    print(f"Wrote {len(catalogue['provisions'])} provisions and "
          f"{catalogue['relationship_count']} relationships to {output}")
    print(f"Input fingerprint: {catalogue['input_fingerprint']}")
    print(f"Unmatched source references: {len(catalogue['unmatched_relationships'])}")


if __name__ == "__main__":
    main()
