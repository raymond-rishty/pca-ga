"""Apply PP-Structure-informed rendering only to minutes pages with cached layout evidence.

The renderer is run into a temporary directory for each requested GA.  Only
successful layout pages replace their corresponding page chunks in markdown/;
all non-layout pages and the document front matter remain unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BAKEOFF = ROOT / "ocr-bakeoff"
PAGE = re.compile(r"<!-- PAGE ga=(\d+) pdf_page=(\d+)\b[^>]*-->")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ga", default="3-52", help="Assemblies, e.g. 3-18,20.")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python for the renderer.")
    parser.add_argument("--apply", action="store_true", help="Write updated minutes Markdown (default is report-only).")
    parser.add_argument("--report", type=Path, default=ROOT / "build" / "layout_minutes_apply_report.json")
    return parser.parse_args()


def numbers(spec: str) -> set[int]:
    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            first, last = map(int, part.split("-", 1))
            result.update(range(first, last + 1))
        elif part:
            result.add(int(part))
    return result


def chunks(text: str) -> tuple[str, dict[int, str]]:
    markers = list(PAGE.finditer(text))
    if not markers:
        raise ValueError("Minutes Markdown has no PAGE markers")
    prefix = text[: markers[0].start()]
    pages: dict[int, str] = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        pages[int(marker.group(2))] = text[markers[index].start() : end]
    return prefix, pages


def successful_layout_pages(directory: Path) -> set[int]:
    pages = set()
    for path in directory.glob("page_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("status") == "success":
            pages.add(int(re.search(r"(\d+)", path.stem).group(1)))
    return pages


def main() -> None:
    args = parse_args()
    interpreter = args.python.resolve()
    if not interpreter.exists():
        raise FileNotFoundError(interpreter)
    results = []
    with tempfile.TemporaryDirectory(prefix="pca-ga-layout-render-") as temporary:
        temporary_root = Path(temporary)
        for ga in sorted(numbers(args.ga)):
            corpus = BAKEOFF / "corpus" / f"ga{ga:02d}"
            source = next((ROOT / "markdown").glob(f"ga{ga:02d}_*.md"), None)
            if not source or not corpus.exists():
                continue
            layout_pages = successful_layout_pages(corpus / "paddle_layout_json")
            if not layout_pages:
                continue
            year = int(re.search(r"_(\d{4})\.md$", source.name).group(1))
            pdf = next((ROOT / "minutes").glob(f"{ga}*_*{year}.pdf"), None)
            if not pdf:
                raise FileNotFoundError(f"Minutes PDF for GA {ga}, {year}")
            rendered = temporary_root / f"ga{ga:02d}"
            command = [
                str(interpreter), str(BAKEOFF / "scripts" / "render_paddle_corpus.py"),
                "--assembly", f"ga{ga:02d}", "--year", str(year), "--pdf", str(pdf),
                "--base", str(corpus / "paddle_ocr_json"), "--routes", str(corpus / "routes.json"),
                "--output", str(rendered), "--layout", str(corpus / "paddle_layout_json"),
                "--layout-oriented", str(corpus / "paddle_layout_oriented_json"), "--existing", str(source),
                "--use-available-layout",
            ]
            subprocess.run(command, cwd=ROOT, check=True)
            prefix, current = chunks(source.read_text(encoding="utf-8"))
            _rendered_prefix, proposed = chunks((rendered / f"ga{ga:02d}_{year}.md").read_text(encoding="utf-8"))
            replace = sorted(layout_pages & current.keys() & proposed.keys())
            if args.apply:
                source.write_text(prefix + "".join(proposed.get(page, current[page]) for page in current), encoding="utf-8")
            results.append({"assembly": f"ga{ga:02d}", "minutes": str(source.relative_to(ROOT)), "layout_pages": len(layout_pages), "replaced_pages": len(replace)})
            print(f"GA {ga:02d}: layout={len(layout_pages)} replace={len(replace)}", flush=True)
    report = {"apply": args.apply, "assemblies": results, "replaced_pages": sum(item["replaced_pages"] for item in results)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"assemblies": len(results), "replaced_pages": report["replaced_pages"]}, indent=2))


if __name__ == "__main__":
    main()
