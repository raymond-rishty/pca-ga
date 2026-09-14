"""Executed inside the same workspace sandbox before a model is launched."""
import argparse
import json
from pathlib import Path
import tempfile


def probe(root, target):
    root, target = root.resolve(), target.resolve()
    if not target.is_relative_to(root) or not target.is_dir():
        raise ValueError('Output directory must exist within repository')
    paths = [target / 'sources.txt', target / 'prompt.txt',
             root / '.agents/skills/pca-ga-case-synopses/SKILL.md',
             root / 'docs/JUDICIAL-CASE-TAXONOMY.md',
             root / 'docs/JUDICIAL-SYNOPSIS-BENCHMARKS.md']
    for path in paths:
        if not path.read_bytes():
            raise ValueError('Empty required input: ' + str(path))
    # Only this newly created, uniquely named probe is removed. Never touch output drafts.
    with tempfile.NamedTemporaryFile(dir=target, prefix='.synopsis-probe-', delete=False) as stream:
        path = Path(stream.name)
        stream.write(b'synopsis-preflight')
    try:
        if path.read_bytes() != b'synopsis-preflight':
            raise ValueError('Read-after-write failed')
    finally:
        path.unlink()
    return {'status': 'passed', 'read_files': len(paths), 'write_read_delete': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.root, args.target)))
