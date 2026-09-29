"""Load and validate the canonical constitutional inquiry JSONL."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_inquiry_records(root: Path) -> list[dict[str, Any]]:
    path = root / "index/inquiries.jsonl"
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: inquiry record must be an object")
        for key in ("id", "stem", "year", "ga_ordinal", "minute_para", "topic"):
            if row.get(key) in (None, ""):
                raise ValueError(f"{path}:{line_number}: missing required {key}")
        if not isinstance(row.get("locator"), dict):
            raise ValueError(f"{path}:{line_number}: locator must be an object")
        record_id = str(row["id"])
        if record_id in seen:
            raise ValueError(f"{path}:{line_number}: duplicate inquiry id {record_id}")
        seen.add(record_id)
        records.append(row)
    if not records:
        raise ValueError(f"{path}: no canonical inquiry records")
    return records
