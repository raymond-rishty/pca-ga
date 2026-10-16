"""Shared parsing and identity rules for the reconciled overture catalogue.

The page-linked ``index/OVERTURES.md`` catalogue is the scope authority. A record
is identified by its Assembly, overture number, and originating minutes page; a
bare Assembly/number pair is not unique in this corpus.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_HEADING = re.compile(r"^## .*\((\d{4})\).*`(ga\d+_\d{4})`$")
_NUMBER = re.compile(r"\d+")
_PAGE_LINK = re.compile(
    r"\[p\.(?P<label>\d+)\]\(\.\./markdown/(?P<volume>[^)#]+)#"
    r"(?P<anchor>ga\d+-p(?P<page>\d+))\)"
)


def _cells(line: str) -> list[str]:
    cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return [cell.replace(r"\|", "|").strip() for cell in cells]


def load_reconciled_overture_records(index_dir: Path) -> list[dict[str, Any]]:
    """Read the exact record roster and metadata from the reconciled Markdown index."""
    path = index_dir / "OVERTURES.md"
    if not path.exists():
        raise FileNotFoundError(f"missing reconciled overture catalogue: {path}")

    records: list[dict[str, Any]] = []
    volume: str | None = None
    year: int | None = None
    ga: int | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _HEADING.match(line)
        if heading:
            year, volume = int(heading.group(1)), heading.group(2)
            ga = int(re.match(r"ga(\d+)", volume).group(1))
            continue
        if not volume or not line.startswith("|") or line.startswith(("|---", "| Overture |")):
            continue
        cells = _cells(line)
        if len(cells) < 5:
            continue
        number_match = _NUMBER.search(cells[0])
        page_matches = list(_PAGE_LINK.finditer(cells[4]))
        if not number_match or not page_matches:
            continue

        number = int(number_match.group())
        # A later Assembly's errata may be the only surviving printed source
        # for an earlier overture. The catalogue number link carries the
        # overture's Assembly identity; the page link identifies the source
        # witness, which can therefore belong to a different minutes volume.
        # Prefer a source page in the Assembly volume when one exists (some
        # catalogue rows also link later actions); otherwise use the first
        # cross-volume source witness.
        own_volume_matches = [
            match for match in page_matches
            if Path(match.group("volume")).stem == volume
        ]
        source_match = own_volume_matches[0] if own_volume_matches else page_matches[0]
        source_volume = Path(source_match.group("volume")).stem
        source_page = int(source_match.group("page"))
        source_ordinal_match = re.match(r"ga(?P<ordinal>\d+)-p", source_match.group("anchor"))
        source_ordinal = int(source_ordinal_match.group("ordinal")) if source_ordinal_match else ga
        catalogue_pages = list(dict.fromkeys(
            int(match.group("page")) for match in page_matches
            if Path(match.group("volume")).stem == source_volume
        ))
        record = {
            "record_id": f"overture:{volume}:{number}:p{source_page}",
            "vol": volume,
            "ga_ordinal": ga,
            "year": year,
            "number": number,
            "source_page": source_page,
            "catalogue_pages": catalogue_pages,
            "title": cells[1],
            "disposition": cells[2],
            "source": cells[3],
        }
        if source_volume != volume:
            record["source_page_vol"] = source_volume
            record["source_page_ga_ordinal"] = source_ordinal
        records.append(record)

    ids = [row["record_id"] for row in records]
    duplicates = sorted({record_id for record_id in ids if ids.count(record_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate source-page overture identities: {duplicates[:12]}")
    return records
