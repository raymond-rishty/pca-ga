"""Migrate generated Markdown footnotes to page-local HTML anchors.

CommonMarkGhPages renders native Markdown footnotes in a document-level
section.  The published corpus uses PAGE comments as hard source boundaries,
so generated ``fn-gaNN-pN-nN`` footnotes must use the inline HTML form already
used for table footnotes.

The migration is deliberately markup-only: it does not inspect scan reports,
re-identify markers, or create new footnotes.  It is safe to run repeatedly.
The default is a dry run; pass ``--apply`` to rewrite the selected files.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORIES = ("markdown", "cases", "cases-rebuilt", "inquiries", "studies")


MODULE_SPEC = importlib.util.spec_from_file_location(
    "footnote_application", ROOT / "scripts" / "79_apply_footnotes.py"
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError("could not load footnote application module")
FOOTNOTES = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = FOOTNOTES
MODULE_SPEC.loader.exec_module(FOOTNOTES)


def markdown_files(directories: list[Path]) -> list[Path]:
    files: list[Path] = []
    for directory in directories:
        if directory.is_dir():
            files.extend(directory.rglob("*.md"))
    return sorted(set(files))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        action="append",
        help="Markdown directory; defaults to all published document roots.",
    )
    parser.add_argument("--apply", action="store_true", help="Rewrite native generated footnotes as HTML.")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "footnote_html_migration.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    directories = args.directory or [ROOT / name for name in DEFAULT_DIRECTORIES]
    results: list[dict[str, object]] = []
    for path in markdown_files(directories):
        original = path.read_text(encoding="utf-8")
        updated, references, definitions = FOOTNOTES.migrate_native_footnotes(original)
        if args.apply and updated != original:
            path.write_text(updated, encoding="utf-8")
        results.append({
            "file": str(path.relative_to(ROOT)),
            "changed": updated != original,
            "migrated_references": references,
            "migrated_definitions": definitions,
            "applied": bool(args.apply and updated != original),
        })

    payload = {
        "schema": "pca-ga.footnote-html-migration.v1",
        "directories": [str(path) for path in directories],
        "apply": args.apply,
        "files_scanned": len(results),
        "files_changed": sum(bool(row["changed"]) for row in results),
        "migrated_references": sum(int(row["migrated_references"]) for row in results),
        "migrated_definitions": sum(int(row["migrated_definitions"]) for row in results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in (
        "apply", "files_scanned", "files_changed", "migrated_references", "migrated_definitions"
    )}, indent=2))


if __name__ == "__main__":
    main()
