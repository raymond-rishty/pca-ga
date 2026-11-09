#!/usr/bin/env python3
"""Build the portable all-in-one Minutes SQLite database."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(os.environ.get("PCA_GA_ROOT", Path(__file__).resolve().parent.parent))


def main() -> None:
    commands = [
        [sys.executable, "scripts/05_index.py", "build", "--force"],
        [sys.executable, "scripts/08_index_cases.py", "build"],
        [sys.executable, "scripts/19_export.py"],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True, env=os.environ.copy())


if __name__ == "__main__":
    main()
