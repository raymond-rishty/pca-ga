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

echo "[3/5] RPR parse — GA31-52 (31) + scanned GA18-30 (32); writes index/rpr/*.json to both trees…"
python3 "$S/31_rpr_parse.py" "$BUILD"
python3 "$S/32_rpr_parse_scanned.py" "$BUILD"

echo "[4/5] RPR build — RPR.md, RPR-BY-PROVISION.md, per-presbytery + per-exception pages (both trees)…"
python3 "$S/33_rpr_build.py" "$BUILD"
python3 "$S/33_rpr_build.py" "$PUB"

echo "[5/5] LLM pack — llms.txt, llms-full.txt, ASK.md (both trees)…"
python3 "$S/34_llm_pack.py" "$BUILD"
python3 "$S/34_llm_pack.py" "$PUB"

echo
echo "Done. Catalogues regenerated in $PUB."
echo "Review:  git -C \"$PUB\" status --short | head"
echo "Then:    git -C \"$PUB\" add -A && git -C \"$PUB\" commit && git -C \"$PUB\" push   (Pages rebuilds ~3 min)"
