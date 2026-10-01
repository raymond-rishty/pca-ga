#!/usr/bin/env python3
"""Run one stateful stage of the full Gradle site build."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import render_site


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_signature(path: Path) -> dict[str, int]:
    """Return a cheap freshness signature for generated, tool-owned assets."""
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def html_signature_snapshot(site: Path) -> dict[str, dict[str, int]]:
    if not site.is_dir():
        return {}
    return {
        path.relative_to(site).as_posix(): file_signature(path)
        for path in sorted(site.rglob("*.html")) if path.is_file()
    }


def html_snapshot(site: Path, prefix: str | None = None) -> dict[str, str]:
    root = site / prefix if prefix else site
    if not root.is_dir():
        return {}
    return {
        path.relative_to(site).as_posix(): sha256(path)
        for path in sorted(root.rglob("*.html"))
        if path.is_file()
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def changed(before: dict[str, str], after: dict[str, str]) -> dict[str, str | None]:
    return {
        name: after.get(name)
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    }


def changed_html_signatures(
    site: Path,
    before: dict[str, dict[str, int]],
    after: dict[str, dict[str, int]],
) -> dict[str, str | None]:
    return {
        name: sha256(site / name) if name in after else None
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    }


def read_changes(path: Path) -> dict[str, str | None]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return {str(item): None for item in value}
    return {str(key): item for key, item in value.items()}


def combine_changes(paths: list[Path]) -> dict[str, str | None]:
    combined: dict[str, str | None] = {}
    for path in paths:
        combined.update(read_changes(path))
    return combined


def linked_site_matches(root: Path, site: Path) -> bool:
    state_path = root / ".gradle" / "build-state" / "fast-preview-links.json"
    if not state_path.is_file():
        return False
    try:
        expected = json.loads(state_path.read_text(encoding="utf-8")).get("pages", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return False
    signature_path = root / ".gradle" / "build-state" / "fast-preview-html-signatures.json"
    if signature_path.is_file():
        try:
            expected_signatures = json.loads(signature_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, AttributeError):
            return False
        actual_signatures = html_signature_snapshot(site)
        return expected_signatures == actual_signatures
    # One-time migration path for existing link state without signatures.
    actual = html_snapshot(site)
    return (set(expected) == set(actual)
            and all(expected[name].get("sha256") == digest
                    for name, digest in actual.items()))


def stage_jekyll(root: Path, site: Path, state_dir: Path) -> None:
    metadata = root / ".jekyll-metadata"
    in_progress = root / ".gradle" / "build-state" / "render-in-progress"
    recovering = in_progress.exists() or not linked_site_matches(root, site)
    before = html_signature_snapshot(site)
    if recovering and metadata.exists():
        metadata.unlink()
    in_progress.parent.mkdir(parents=True, exist_ok=True)
    in_progress.write_text("Full site build did not complete.\n", encoding="utf-8")

    render_site.prepare_incremental_source_mtimes(root)
    render_site.run(
        ["bundle", "exec", "jekyll", "build", "--incremental", "--destination", str(site)],
        root,
    )
    render_site.save_incremental_source_mtimes(root)
    after = html_signature_snapshot(site)
    jekyll_changes = changed_html_signatures(site, before, after)
    if recovering:
        # A prior build may have stopped between Jekyll and a post-processing
        # task. Revisit every current page so all later stages repair the site.
        jekyll_changes.update({name: sha256(site / name) for name in after})
    write_json(state_dir / "jekyll-html-changes.json", jekyll_changes)


def stage_provisions(root: Path, site: Path, state_dir: Path) -> None:
    before = html_snapshot(site, "provisions")
    before.update(html_snapshot(site, "authorities"))
    refresh_cache, fingerprint = render_site.restore_or_generate_provision_pages(root, site, force=False)
    if refresh_cache:
        render_site.save_provision_pages(root, site, fingerprint)
    after = html_snapshot(site, "provisions")
    after.update(html_snapshot(site, "authorities"))
    write_json(state_dir / "provision-html-changes.json", changed(before, after))


def stage_authority_links(root: Path, site: Path, state_dir: Path) -> None:
    before = html_snapshot(site, "authorities")
    render_site.run(
        [sys.executable, "scripts/46_provision_research.py", "link-authorities", str(root), str(site)],
        root,
    )
    after = html_snapshot(site, "authorities")
    write_json(state_dir / "authority-html-changes.json", changed(before, after))


def stage_minutes_markup(root: Path, site: Path, state_dir: Path) -> None:
    code_paths = [
        root / "scripts" / "46_minutes_page_markup.py",
        root / "scripts" / "minutes_page_locators.py",
    ]
    code_fingerprint = hashlib.sha256(b"\0".join(
        path.read_bytes() for path in code_paths
    )).hexdigest()
    code_path = state_dir / "minutes-markup-code.json"
    previous = json.loads(code_path.read_text(encoding="utf-8")) if code_path.is_file() else {}
    force_all = bool(previous) and previous.get("sha256") != code_fingerprint

    candidates_path = state_dir / "minutes-markup-candidates.json"
    if not force_all:
        changed_paths = read_changes(state_dir / "jekyll-html-changes.json")
        candidates = sorted(
            name for name in changed_paths
            if re.fullmatch(r"markdown/ga\d+_\d{4}\.html", name)
        )
        write_json(candidates_path, candidates)

    path_list = state_dir / "minutes-html-changed-paths.json"
    command = [
        sys.executable, "scripts/46_minutes_page_markup.py", str(site),
        "--changed-files-output", str(path_list),
    ]
    if not force_all:
        command.extend(["--files-manifest", str(candidates_path)])
    try:
        render_site.run(command, root)
    finally:
        candidates_path.unlink(missing_ok=True)
    try:
        relative_paths = json.loads(path_list.read_text(encoding="utf-8"))
        changes = {
            str(relative): sha256(site / str(relative))
            for relative in relative_paths
            if (site / str(relative)).is_file()
        }
    finally:
      path_list.unlink(missing_ok=True)
    write_json(state_dir / "minutes-html-changes.json", changes)
    write_json(code_path, {"sha256": code_fingerprint})


def stage_normalize(root: Path, site: Path, state_dir: Path) -> None:
    candidates = combine_changes([
        state_dir / "jekyll-html-changes.json",
        state_dir / "provision-html-changes.json",
        state_dir / "authority-html-changes.json",
        state_dir / "minutes-html-changes.json",
    ])
    code_paths = [root / "scripts" / "44_normalize_bco_prefixes.py"]
    code_fingerprint = hashlib.sha256(b"\0".join(
        path.read_bytes() for path in code_paths
    )).hexdigest()
    code_path = state_dir / "normalizer-code.json"
    previous = json.loads(code_path.read_text(encoding="utf-8")) if code_path.is_file() else {}
    if previous.get("sha256") != code_fingerprint:
        candidates = {name: None for name in html_snapshot(site)}

    candidate_path = state_dir / "normalize-candidates.json"
    output_path = state_dir / "normalized-html-changes.json"
    write_json(candidate_path, candidates)
    render_site.run([
        sys.executable, "scripts/44_normalize_bco_prefixes.py", str(site),
        "--changed-files", str(candidate_path), "--files-manifest", str(output_path),
    ], root)
    write_json(code_path, {"sha256": code_fingerprint})


def stage_link(root: Path, site: Path, reader: Path, state_dir: Path) -> None:
    link_state = root / ".gradle" / "build-state" / "fast-preview-links.json"
    signature_state = root / ".gradle" / "build-state" / "fast-preview-html-signatures.json"
    code_state = state_dir / "linker-code.json"
    code_paths = [root / "scripts" / name for name in (
        "44_link_constitution_refs.py", "44_normalize_bco_prefixes.py",
        "46_minutes_page_markup.py", "minutes_page_locators.py",
        "scripture_linker.py", "linker_fingerprint.py",
    )]
    code_fingerprint = hashlib.sha256(b"\0".join(
        path.read_bytes() for path in code_paths
    )).hexdigest()
    previous_code = json.loads(code_state.read_text(encoding="utf-8")) if code_state.is_file() else {}
    reset = not link_state.is_file() or (
        "sha256" in previous_code and previous_code.get("sha256") != code_fingerprint
    )
    command = [
        sys.executable, "scripts/44_link_constitution_refs.py", str(site),
        *(str(reader / name) for name in ("bco.js", "wcf.js", "wlc.js", "wsc.js", "rao.js")),
        "--incremental-state", str(link_state),
        "--source-inventory", render_site.source_inventory(root),
    ]
    change_paths = [
        state_dir / name for name in (
            "jekyll-html-changes.json",
            "provision-html-changes.json",
            "authority-html-changes.json",
            "minutes-html-changes.json",
            "normalized-html-changes.json",
        )
    ]
    candidates_path = state_dir / "link-candidates.json"
    write_json(candidates_path, combine_changes(change_paths))
    if reset:
        command.append("--reset-state")
    else:
        command.extend(["--files-manifest", str(candidates_path)])
    try:
        status = render_site.run_result(command, root, check=False)
        if status == 3:
            command = [part for part in command
                       if part not in ("--files-manifest", str(candidates_path))]
            command.append("--reset-state")
            status = render_site.run_result(command, root, check=False)
    finally:
        candidates_path.unlink(missing_ok=True)
    if status:
        raise subprocess.CalledProcessError(status, command)
    state = json.loads(link_state.read_text(encoding="utf-8"))
    signatures = {
        relative: file_signature(site / relative)
        for relative in state.get("pages", {})
        if (site / relative).is_file()
    }
    write_json(signature_state, signatures)
    write_json(code_state, {"sha256": code_fingerprint})


def stage_pagefind(root: Path, site: Path, state_dir: Path) -> None:
    render_site.run(["npx", "--yes", "pagefind@1.5.2", "--site", str(site)], root)
    pagefind = site / "pagefind"
    manifest = {
        path.relative_to(pagefind).as_posix(): file_signature(path)
        for path in sorted(pagefind.rglob("*")) if path.is_file()
    }
    write_json(state_dir / "pagefind-output.json", manifest)
    in_progress = root / ".gradle" / "build-state" / "render-in-progress"
    in_progress.unlink(missing_ok=True)


def verify_site(root: Path, site: Path, state_dir: Path) -> None:
    state_path = root / ".gradle" / "build-state" / "fast-preview-links.json"
    if not state_path.is_file():
        raise RuntimeError(f"Missing constitution-link state: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    expected = state.get("pages", {})
    actual = html_snapshot(site)
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    changed_pages = sorted(
        name for name in set(expected) & set(actual)
        if expected[name].get("sha256") != actual[name]
    )
    if missing or unexpected or changed_pages:
        details = []
        if missing:
            details.append(f"missing linked HTML: {missing[:10]}")
        if unexpected:
            details.append(f"untracked HTML: {unexpected[:10]}")
        if changed_pages:
            details.append(f"HTML changed after linking: {changed_pages[:10]}")
        raise RuntimeError("Site stage state does not match rendered output: " + "; ".join(details))
    print(f"Site stage state verified: {len(actual)} linked HTML files match the final output.")
    pagefind_state = state_dir / "pagefind-output.json"
    expected_pagefind = json.loads(pagefind_state.read_text(encoding="utf-8"))
    pagefind_root = site / "pagefind"
    actual_pagefind = {
        path.relative_to(pagefind_root).as_posix(): file_signature(path)
        for path in sorted(pagefind_root.rglob("*")) if path.is_file()
    }
    if expected_pagefind != actual_pagefind:
        raise RuntimeError("Pagefind output differs from its completed build-stage manifest")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("jekyll", "provisions", "authority-links", "minutes-markup", "normalize", "link", "pagefind", "verify"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--site", required=True, type=Path)
    parser.add_argument("--reader", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    root, site, reader, state_dir = (path.resolve() for path in
                                     (args.root, args.site, args.reader, args.state_dir))
    state_dir.mkdir(parents=True, exist_ok=True)
    stages = {
        "jekyll": lambda: stage_jekyll(root, site, state_dir),
        "provisions": lambda: stage_provisions(root, site, state_dir),
        "authority-links": lambda: stage_authority_links(root, site, state_dir),
        "minutes-markup": lambda: stage_minutes_markup(root, site, state_dir),
        "normalize": lambda: stage_normalize(root, site, state_dir),
        "link": lambda: stage_link(root, site, reader, state_dir),
        "pagefind": lambda: stage_pagefind(root, site, state_dir),
        "verify": lambda: verify_site(root, site, state_dir),
    }
    stages[args.stage]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
