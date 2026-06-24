#!/usr/bin/env bash
# render.sh — regenerate every markdown CATALOGUE into both trees.
#
#   BUILD tree  = /workspace            (regenerable inputs: build/page_jsonl, pca_minutes.db, venv)
#   PUBLISH tree = /workspace/dist/pca-ga (this git repo; what GitHub Pages serves)
#   markdown/* is HARDLINKED between the two, so corpus text edits land in both automatically.
#
# This regenerates the catalogues (INDEX/OVERTURES/CASES/outlines, INQUIRIES + CCB advice, RPR) from
# the JSON index layers + the markdown corpus. It does NOT re-run the heavy corpus pipeline
# (01_extract … → page_jsonl); for that see PORTABLE.md "Provenance / regeneration".
#
# .md → .html is automatic: GitHub Pages (Jekyll) rebuilds on push (~3 min). After running this,
# review `git -C "$PUB" status`, then commit & push.
set -euo pipefail

BUILD="${BUILD:-/workspace}"
PUB="${PUB:-/workspace/dist/pca-ga}"
S="$BUILD/scripts"

# copy src -> dst, but skip if they're already the SAME file (some build-tree outputs are hardlinked
# into the published tree, so a plain cp would error "same file" and abort under `set -e`).
sync_file() {
  [ -e "$1" ] || return 0
  [ "$(stat -c %i "$1" 2>/dev/null)" = "$(stat -c %i "$2" 2>/dev/null)" ] && return 0
  cp -f "$1" "$2"
}

echo "[1/5] INDEX + OVERTURES + CASES + per-volume outlines (DB-backed; build tree only)…"
python3 "$S/20_markdown_index.py"                       # ROOT hardcoded /workspace (needs pca_minutes.db)
mkdir -p "$PUB/index/outlines"
for f in INDEX OVERTURES CASES; do sync_file "$BUILD/index/$f.md" "$PUB/index/$f.md"; done
for f in "$BUILD"/index/outlines/*.md; do sync_file "$f" "$PUB/index/outlines/$(basename "$f")"; done

echo "[2/5] Constitutional inquiries + CCB advice (both trees)…"
python3 "$S/30_inquiry_pages.py" "$BUILD"
python3 "$S/30_inquiry_pages.py" "$PUB"

# case/inquiry Source links: line numbers -> PDF page numbers + deep-link anchor
# (idempotent; maps via the markdown's own per-page anchors so the link lands on
# the cited page — runs AFTER the generators so a re-render never reverts it)
python3 "$S/41_source_pagelinks.py" "$BUILD"
python3 "$S/41_source_pagelinks.py" "$PUB"

echo "[3/5] RPR parse — GA31-52 (31) + scanned GA18-30 (32); writes index/rpr/*.json to both trees…"
python3 "$S/31_rpr_parse.py" "$BUILD"
python3 "$S/32_rpr_parse_scanned.py" "$BUILD"

echo "[4/5] RPR build — RPR.md, RPR-BY-PROVISION.md, per-presbytery + per-exception pages (both trees)…"
python3 "$S/33_rpr_build.py" "$BUILD"
python3 "$S/33_rpr_build.py" "$PUB"

# Per-overture extract pages (like cases/ + inquiries/), then link the GA53
# findings' bolded past-overture cites (**GA51 O26**) to them. 37 builds the pages
# + index/overture_pages_map.json on both trees; 38 rewrites the build-tree findings
# (GA53 source) using that map; then 36 renders the findings into the published pages.
python3 "$S/37_overture_pages.py" "$BUILD"
python3 "$S/37_overture_pages.py" "$PUB"
python3 "$S/38_link_overture_cites.py" "$BUILD"
# link the OVERTURES.md catalogue's number cells to those pages (both trees; the
# catalogue was already synced to PUB in step [1/5], so re-link both copies here,
# now that 37 has written index/overture_pages_map.json)
python3 "$S/42_link_overture_catalogue.py" "$BUILD"
python3 "$S/42_link_overture_catalogue.py" "$PUB"

echo "[5/7] GA53 (2026) overture analysis — per-overture pages + catalogue + combined doc (both trees)…"
# GA53 source (findings/, overtures_full.tsv, _header.md) lives in the BUILD tree (like 20's pca_minutes.db pin)
GA53_SRC="$BUILD/ga53" python3 "$S/36_ga53_overtures.py" "$BUILD"
GA53_SRC="$BUILD/ga53" python3 "$S/36_ga53_overtures.py" "$PUB"

echo "[6/7] Authority map — cases + inquiries + RPR + overtures (both trees)…"
python3 "$S/43_authority_index.py" "$BUILD"
python3 "$S/43_authority_index.py" "$PUB"

echo "[7/7] LLM pack — llms.txt, llms-full.txt, ASK.md (both trees)…"
python3 "$S/34_llm_pack.py" "$BUILD"
python3 "$S/34_llm_pack.py" "$PUB"

echo
echo "Done. Catalogues regenerated in $PUB."
echo "Review:  git -C \"$PUB\" status --short | head"
echo "Then:    git -C \"$PUB\" add -A && git -C \"$PUB\" commit && git -C \"$PUB\" push   (Pages rebuilds ~3 min)"
