#!/usr/bin/env python3
"""Run the render and post-processing stages for the Gradle site build."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile


WINDOWS_SHELL_TOOLS = {"bundle", "npx"}


def run_result(command: list[str], root: Path, *, check: bool = True) -> int:
    if os.name == "nt" and command[0].lower() in WINDOWS_SHELL_TOOLS:
        # Bundler and npm expose .bat/.cmd launchers on Windows.
        result = subprocess.run(
            subprocess.list2cmdline(command), cwd=root, shell=True, check=False
        )
    else:
        result = subprocess.run(command, cwd=root, check=False)
    if check and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)
    return result.returncode


def run(command: list[str], root: Path) -> None:
    run_result(command, root)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_inventory(root: Path) -> str:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    paths = sorted(set(item.decode("utf-8", "surrogateescape")
                       for item in result.stdout.split(b"\0") if item))
    return hashlib.sha256("\0".join(paths).encode("utf-8", "surrogateescape")).hexdigest()


def tracked_source_fingerprints(root: Path) -> dict[str, str]:
    staged = subprocess.run(
        ["git", "ls-files", "--stage", "-z"], cwd=root, check=True,
        stdout=subprocess.PIPE,
    ).stdout
    unstaged = subprocess.run(
        ["git", "diff", "--name-only", "-z"], cwd=root, check=True,
        stdout=subprocess.PIPE,
    ).stdout
    unstaged_paths = {
        item.decode("utf-8", "surrogateescape")
        for item in unstaged.split(b"\0") if item
    }
    fingerprints: dict[str, str] = {}
    for record in staged.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            continue
        relative = raw_path.decode("utf-8", "surrogateescape")
        path = root / Path(relative)
        if not path.is_file():
            continue
        if relative in unstaged_paths:
            fingerprints[relative] = "sha256:" + file_sha256(path)
        else:
            fingerprints[relative] = "git:" + object_id

    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root, check=True, stdout=subprocess.PIPE,
    ).stdout
    for raw_path in untracked.split(b"\0"):
        if not raw_path:
            continue
        relative = raw_path.decode("utf-8", "surrogateescape")
        path = root / Path(relative)
        if path.is_file():
            fingerprints[relative] = "sha256:" + file_sha256(path)
    return fingerprints


def prepare_incremental_source_mtimes(root: Path) -> None:
    """Restore stable source mtimes for unchanged files in cached CI checkouts.

    Jekyll's metadata is mtime-based. Fresh checkouts make every unchanged file
    appear newer than the cached metadata, so use Git object IDs to distinguish
    unchanged tracked files from actual edits and restore their prior mtimes.
    """
    state_path = root / ".gradle" / "build-state" / "jekyll-source-mtimes.json"
    prior: dict[str, dict[str, object]] = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("version") == 1:
                prior = state.get("files", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            prior = {}
    if not prior:
        return

    now_ns = time.time_ns()
    for relative, fingerprint in tracked_source_fingerprints(root).items():
        path = root / Path(relative)
        cached = prior.get(relative, {})
        matches = cached.get("fingerprint") == fingerprint
        old_fingerprint = str(cached.get("fingerprint", ""))
        if (not matches and fingerprint.startswith("git:")
                and old_fingerprint.startswith("sha256:")):
            matches = file_sha256(path) == old_fingerprint.removeprefix("sha256:")
        old_mtime = cached.get("mtime_ns")
        if matches and isinstance(old_mtime, int):
            mtime_ns = old_mtime
        else:
            mtime_ns = max(now_ns, old_mtime + 2_000_000_000) if isinstance(old_mtime, int) else now_ns
        stat = path.stat()
        if stat.st_mtime_ns != mtime_ns:
            os.utime(path, ns=(stat.st_atime_ns, mtime_ns))


def save_incremental_source_mtimes(root: Path) -> None:
    state_path = root / ".gradle" / "build-state" / "jekyll-source-mtimes.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    files = {}
    for relative, fingerprint in tracked_source_fingerprints(root).items():
        path = root / Path(relative)
        files[relative] = {"fingerprint": fingerprint, "mtime_ns": path.stat().st_mtime_ns}
    state_temp = state_path.with_suffix(state_path.suffix + ".tmp")
    state_temp.write_text(json.dumps({"version": 1, "files": files}, separators=(",", ":")),
                          encoding="utf-8")
    state_temp.replace(state_path)


def provision_input_fingerprint(root: Path) -> str:
    paths = [
        root / "scripts" / "46_provision_research.py",
        root / "scripts" / "provision_catalogue.py",
        root / "scripts" / "44_link_constitution_refs.py",
        root / "index" / "provision_catalogue.json",
    ]
    authority_dir = root / "authorities"
    if authority_dir.is_dir():
        paths.extend(authority_dir.glob("*.md"))

    digest = hashlib.sha256()
    for path in sorted((path for path in paths if path.is_file()),
                       key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def restore_or_generate_provision_pages(
    root: Path, site: Path, *, force: bool
) -> tuple[bool, str]:
    state_path = root / ".gradle" / "build-state" / "fast-preview-provisions.json"
    cache_path = root / ".gradle" / "build-state" / "fast-preview-provisions.zip"
    fingerprint = provision_input_fingerprint(root)
    prior: dict[str, object] = {}
    if state_path.is_file():
        try:
            prior = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = {}

    catalogue = json.loads(
        (root / "index" / "provision_catalogue.json").read_text(encoding="utf-8")
    )
    expected_names = {"index.html"}
    for unit in catalogue.get("provisions", []):
        expected_names.add(
            f"{unit['book']}/{unit['route_ref']}/index.html"
        )
    expected_pages = len(expected_names)
    cached_pages: list[str] = []
    if cache_path.is_file():
        try:
            with zipfile.ZipFile(cache_path) as archive:
                cached_pages = [name for name in archive.namelist()
                                if name.endswith(".html")]
        except (OSError, zipfile.BadZipFile):
            cached_pages = []

    can_restore = (
        not force
        and prior.get("fingerprint") == fingerprint
        and set(cached_pages) == expected_names
    )
    if can_restore:
        provision_root = site / "provisions"
        provision_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(cache_path) as archive:
            for name in cached_pages:
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError(f"Unsafe path in provision page cache: {name}")
                output = provision_root / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(archive.read(name))
        prune_stale_provision_pages(site, expected_names)
        print(f"Restored {expected_pages} linked provision pages from the local cache.")
        return False, fingerprint

    if force or prior.get("fingerprint") != fingerprint or set(cached_pages) != expected_names:
        run([sys.executable, "scripts/46_provision_research.py", "site",
             str(root), str(site), "--baseurl", "/pca-ga"], root)
        prune_stale_provision_pages(site, expected_names)
        return True, fingerprint
    raise RuntimeError("Provision page cache could not be restored or regenerated")


def prune_stale_provision_pages(site: Path, expected_names: set[str]) -> None:
    """Remove only obsolete generated HTML from the preserved provisions tree."""
    provision_root = site / "provisions"
    if not provision_root.is_dir():
        return
    for page in provision_root.rglob("*.html"):
        relative = page.relative_to(provision_root).as_posix()
        if relative not in expected_names:
            page.unlink()


def save_provision_pages(root: Path, site: Path, fingerprint: str) -> None:
    state_dir = root / ".gradle" / "build-state"
    cache_path = state_dir / "fast-preview-provisions.zip"
    cache_temp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    provision_root = site / "provisions"
    pages = sorted(provision_root.rglob("*.html"))
    if not pages:
        raise RuntimeError("Cannot cache provision pages because none were rendered")

    state_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cache_temp, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for page in pages:
            archive.write(page, page.relative_to(provision_root).as_posix())
    cache_temp.replace(cache_path)
    state_path = state_dir / "fast-preview-provisions.json"
    state_temp = state_path.with_suffix(state_path.suffix + ".tmp")
    state_temp.write_text(json.dumps({"version": 1, "fingerprint": fingerprint}),
                          encoding="utf-8")
    state_temp.replace(state_path)


def run_fast_preview(root: Path, site: Path, reader: Path,
                     refresh_search: bool) -> None:
    state = root / ".gradle" / "build-state" / "fast-preview-links.json"
    in_progress = root / ".gradle" / "build-state" / "render-in-progress"
    changed_manifest = root / ".gradle" / "build-state" / "fast-preview-changed-html.json"
    metadata = root / ".jekyll-metadata"
    current_inventory = source_inventory(root)
    prior_state: dict[str, object] = {}
    if state.is_file():
        try:
            prior_state = json.loads(state.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior_state = {}

    interrupted = in_progress.exists()
    full_render = (
        interrupted
        or prior_state.get("version") != 1
        or not metadata.is_file()
    )
    in_progress.parent.mkdir(parents=True, exist_ok=True)
    in_progress.write_text("Fast preview did not complete.\n", encoding="utf-8")
    if full_render and metadata.exists():
        metadata.unlink()

    prepare_incremental_source_mtimes(root)
    jekyll = ["bundle", "exec", "jekyll", "build", "--incremental",
              "--destination", str(site)]
    run(jekyll, root)
    save_incremental_source_mtimes(root)

    # Provision pages are generated HTML too. Create them before the normalizer
    # and linker so their contents participate in the per-page state and audit.
    refresh_provision_cache, provision_fingerprint = restore_or_generate_provision_pages(
        root, site, force=full_render
    )
    # Jekyll may regenerate an authority page while canonical provision pages
    # come from cache. Reapply the compatibility links before linking and audit.
    run([sys.executable, "scripts/46_provision_research.py", "link-authorities",
         str(root), str(site)], root)

    normalizer = [sys.executable, "scripts/44_normalize_bco_prefixes.py", str(site)]
    if not full_render:
        normalizer += ["--incremental-state", str(state),
                       "--files-manifest", str(changed_manifest)]
    run(normalizer, root)

    link_command = [
        sys.executable, "scripts/44_link_constitution_refs.py", str(site),
        str(reader / "bco.js"), str(reader / "wcf.js"), str(reader / "wlc.js"),
        str(reader / "wsc.js"), str(reader / "rao.js"),
        "--incremental-state", str(state),
        # The source inventory is recorded when the state is seeded. Content
        # additions/deletions are detected by Jekyll and the page manifest;
        # using the previous value avoids invalidating every page for an
        # unrelated new source filename.
        "--source-inventory", str(
            current_inventory if full_render
            else prior_state.get("source_inventory", current_inventory)
        ),
    ]
    if full_render:
        link_command.append("--reset-state")
    link_status = run_result(link_command, root, check=False)
    if link_status == 3:
        print("Link targets changed; forcing a complete Jekyll and link rebuild.")
        if metadata.exists():
            metadata.unlink()
        prepare_incremental_source_mtimes(root)
        run(jekyll, root)
        save_incremental_source_mtimes(root)
        refresh_provision_cache, provision_fingerprint = restore_or_generate_provision_pages(
            root, site, force=True
        )
        run([sys.executable, "scripts/46_provision_research.py", "link-authorities",
             str(root), str(site)], root)
        run([sys.executable, "scripts/44_normalize_bco_prefixes.py", str(site)], root)
        link_command.append("--reset-state")
        inventory_index = link_command.index("--source-inventory") + 1
        link_command[inventory_index] = current_inventory
        run(link_command, root)
        full_render = True
    elif link_status:
        raise subprocess.CalledProcessError(link_status, link_command)

    if refresh_provision_cache:
        save_provision_pages(root, site, provision_fingerprint)

    pagefind_index = site / "pagefind" / "pagefind.js"
    if full_render or refresh_search or not pagefind_index.is_file():
        run(["npx", "--yes", "pagefind@1.5.2", "--site", str(site)], root)
        search_state = "refreshed"
    else:
        search_state = "left at the last full-build version"

    required = [
        site / "index.html",
        site / "assets" / "scripture-audit.json",
        site / "assets" / "scripture-audit-summary.json",
        site / "assets" / "constitution" / "unresolved.json",
        site / "provisions" / "index.html",
        pagefind_index,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Fast preview is missing required outputs: " + ", ".join(missing))

    if full_render:
        changed_count = sum(1 for _ in site.rglob("*.html"))
    elif changed_manifest.is_file():
        changed_count = len(json.loads(changed_manifest.read_text(encoding="utf-8")))
    else:
        changed_count = 0
    print(f"Fast preview ready: {changed_count} HTML pages processed; search index {search_state}.")
    in_progress.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--reader", type=Path, required=True,
                        help="PCA Constitution Reader content directory")
    parser.add_argument("--incremental-jekyll", action="store_true",
                        help="Use Jekyll's experimental local incremental regeneration")
    parser.add_argument("--fast-preview", action="store_true",
                        help="Incrementally render changed pages and reuse citation audits")
    parser.add_argument("--refresh-search", action="store_true",
                        help="Rebuild Pagefind after an incremental render")
    args = parser.parse_args()

    root = args.root.resolve()
    site = args.site.resolve()
    reader = args.reader.resolve()
    required_reader_files = [reader / name for name in ("bco.js", "wcf.js", "wlc.js", "wsc.js", "rao.js")]
    missing = [path for path in required_reader_files if not path.is_file()]
    if missing:
        raise SystemExit("Missing Constitution Reader inputs: " + ", ".join(map(str, missing)))

    site.mkdir(parents=True, exist_ok=True)
    state = root / ".gradle" / "build-state" / "fast-preview-links.json"
    inventory = source_inventory(root)
    if args.fast_preview:
        run_fast_preview(root, site, reader, args.refresh_search)
        return 0

    in_progress = root / ".gradle" / "build-state" / "render-in-progress"
    in_progress.parent.mkdir(parents=True, exist_ok=True)
    in_progress.write_text("Full site build did not complete.\n", encoding="utf-8")
    metadata = root / ".jekyll-metadata"
    if metadata.exists():
        metadata.unlink()
    prepare_incremental_source_mtimes(root)
    jekyll = ["bundle", "exec", "jekyll", "build", "--incremental",
              "--destination", str(site)]
    if args.incremental_jekyll:
        jekyll.append("--incremental")
    run(jekyll, root)
    save_incremental_source_mtimes(root)

    python = sys.executable
    run([python, "scripts/build_bsb_assets.py", "--check"], root)
    _, provision_fingerprint = restore_or_generate_provision_pages(root, site, force=True)
    run([python, "scripts/44_normalize_bco_prefixes.py", str(site)], root)
    run([python, "scripts/44_link_constitution_refs.py", str(site),
         *(str(reader / name) for name in ("bco.js", "wcf.js", "wlc.js", "wsc.js", "rao.js")),
         "--incremental-state", str(state), "--source-inventory", inventory,
         "--reset-state"], root)
    save_provision_pages(root, site, provision_fingerprint)
    run(["npx", "--yes", "pagefind@1.5.2", "--site", str(site)], root)
    in_progress.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
