"""Publish the structural outline against the stationary targets of each rendered volume."""
import json
import re
from collections import Counter
from pathlib import Path

MARKER = re.compile(r'<div class="page-marker" data-ga="\d+" data-pdf-page="(\d+)" data-printed-page="([^"]*)"[^>]*>\s*<a href="#([^"]+)"')
ANCHOR = re.compile(r'<span id="([^"]+)" class="minutes-page__anchor">')


def make_outline(volume, structure, html):
    if structure.get("volume", volume) != volume:
        raise ValueError(f"{volume}: incorrect structure identity")
    anchors = Counter(ANCHOR.findall(html))
    pages = {}
    for pdf, folio, target in MARKER.findall(html):
        if int(pdf) < 1 or int(pdf) in pages or anchors[target] != 1:
            raise ValueError(f"{volume}: invalid marker at PDF page {pdf}")
        pages[int(pdf)] = (None if folio.lower() == "null" else folio, target)
    if not pages or any(count != 1 for count in anchors.values()):
        raise ValueError(f"{volume}: missing or duplicate page targets")
    discrepancies = 0

    def nodes(rows, prefix):
        nonlocal discrepancies
        result = []
        for index, row in enumerate(rows):
            key = f"{prefix}{index}"
            pdf = row.get("pdf_page")
            if isinstance(pdf, str) and pdf.isdigit():
                pdf = int(pdf)
            folio, target = pages.get(pdf, (None, None))
            if target and row.get("printed_page") is not None and str(row["printed_page"]) != folio:
                discrepancies += 1
            label = " ".join(str(row[field]) for field in ("label", "title") if row.get(field))
            if row.get("type") == "overture" and row.get("number"):
                label = f"Overture {row['number']} — {row.get('source') or ''}".rstrip(" —")
            result.append(dict(key=key, label=label or row.get("type", "Section"),
                               pdf=pdf if target else None, folio=folio, target=target,
                               children=nodes(row.get("children", []), key + ".")))
        return result

    outline = dict(version=1, volume=volume, nodes=nodes(structure.get("parts", []), ""))
    if discrepancies:
        print(f"{volume}: used page-marker labels for {discrepancies} differing outline folios")
    return outline


def publish_outlines(site, volumes):
    directory = site / "assets" / "volume-outlines"
    directory.mkdir(parents=True, exist_ok=True)
    structures = Path(__file__).resolve().parents[1] / "index" / "structure"
    expected = set()
    for volume in volumes:
        source = structures / (volume.stem + ".json")
        tree = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {}
        data = make_outline(volume.stem, tree, volume.read_text(encoding="utf-8"))
        destination = directory / source.name
        expected.add(destination)
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
        if not destination.exists() or destination.read_text(encoding="utf-8") != content:
            destination.write_text(content, encoding="utf-8", newline="\n")
    for obsolete in directory.glob("ga*_*.json"):
        if obsolete not in expected:
            obsolete.unlink()
