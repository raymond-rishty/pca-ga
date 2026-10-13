"""Helpers for safely replacing generated files on disk."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Replace a generated file atomically without truncating its old version."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Encode and atomically replace a generated text file."""
    write_bytes_atomic(path, text.encode(encoding))
