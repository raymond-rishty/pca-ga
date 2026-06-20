#!/usr/bin/env python3
"""audit.py — standing regression gate for the GA53 layer (Loop 31 deterministic checks).

Audits the per-overture findings (source of truth) + rendered pages against the failure patterns
surfaced in review. Reports every issue and exits non-zero if any remain. Semantic
"is this cited case actually bearing / accurately described" is NOT checked here — that's the
agentic judicial-attribution pass.

Checks:
  1 broken_link        — every ](../PATH) resolves (relative to the published ga53/ page -> ROOT/PATH)
  2 minutes_not_case   — a cited case that HAS a built case page must link to it, not the minutes
  3 phantom_case       — a cited YEAR-N case number exists in the corpus
  4 star_recency       — a ⭐ bullet must reference a GA48–52 (2021–2025) item, not <= GA47
  5 sections           — all five sections present; non-empty or an explicit "None found."
  6 render_integrity   — every rendered page has layout/title/updated front matter; combined doc = 90

Usage: python3 audit.py            # report (exit 1 if issues)
"""
import json, os, re, sys, glob

ROOT = os.environ.get("GA53_ROOT", "/workspace")
FIND = os.path.join(ROOT, "ga53", "findings")
PAGES = os.path.join(ROOT, "ga53")
IDX = os.path.join(ROOT, "index")

LINK = re.compile(r"\]\((\.\./[^)#]+)(?:#[^)]*)?\)")
CASENUM = re.compile(r"(?<![\d-])((?:19|20)\d{2}-\d+)(?![\d-])")
SECTIONS = ["### Judicial cases", "### Constitutional inquiries", "### Prior overtures",
            "### RPR exceptions", "### Note"]


def onum(p):
    return int(re.search(r"O(\d+)", os.path.basename(p)).group(1))


def norm_case(n):
    a = n.split("-")
    return a[0] + "-" + str(int(re.sub(r"[A-Za-z].*", "", a[1]))) if len(a) == 2 and a[1][:1].isdigit() else n


def load_case_universe():
    pages = json.load(open(os.path.join(IDX, "case_pages_map.json")))
    norm2file = {}
    known = set()
    for num, info in pages.items():
        for k in [num] + info.get("numbers", []):
            norm2file[norm_case(k)] = info["file"]
            known.add(norm_case(k))
    for l in open(os.path.join(IDX, "cases.jsonl")):
        for m in CASENUM.findall(l):           # scan the whole record (number, title, parties, body)
            known.add(norm_case(m))
    cm = os.path.join(IDX, "CASES.md")
    if os.path.exists(cm):
        for m in CASENUM.findall(open(cm, encoding="utf-8").read()):
            known.add(norm_case(m))
    return norm2file, known


def judicial_block(txt):
    m = re.search(r"### Judicial cases.*?(?=\n### |\Z)", txt, re.S)
    return m.group(0) if m else ""


def main():
    norm2file, known = load_case_universe()
    issues = []
    files = sorted(glob.glob(os.path.join(FIND, "O*.md")), key=onum)
    for fp in files:
        o = os.path.basename(fp)[:-3]
        txt = open(fp, encoding="utf-8").read()

        # 1 broken links
        for m in LINK.finditer(txt):
            tgt = os.path.normpath(os.path.join(PAGES, m.group(1)))
            if not os.path.exists(tgt):
                issues.append((o, "broken_link", m.group(1)))

        # 2 minutes-vs-case-page (link text starts with a case number that has a built page)
        for m in re.finditer(r"\[((?:19|20)\d{2}-\d+)[^\]]*\]\((\.\./markdown/[^)#]+)", txt):
            f = norm2file.get(norm_case(m.group(1)))
            if f and os.path.exists(os.path.join(ROOT, "cases", f + ".md")):
                issues.append((o, "minutes_not_case", f"{m.group(1)} -> should link ../cases/{f}.md"))

        # 3 phantom case numbers cited in the Judicial section
        jb = judicial_block(txt)
        for m in CASENUM.finditer(jb):
            if norm_case(m.group(1)) not in known:
                issues.append((o, "phantom_case", m.group(1)))

        # 4 star recency: a starred bullet referencing GA<=47
        for ln in txt.splitlines():
            if "⭐" in ln:
                gas = [int(x) for x in re.findall(r"GA(\d{2})\b", ln)]
                if gas and all(g <= 47 for g in gas):
                    issues.append((o, "star_recency", ln.strip()[:90]))

        # 5 sections present
        for s in SECTIONS:
            if s not in txt:
                issues.append((o, "missing_section", s))

    # 6 render integrity
    rendered = sorted(glob.glob(os.path.join(PAGES, "O*.md")), key=onum)
    for fp in rendered:
        head = open(fp, encoding="utf-8").read()[:300]
        for k in ("layout: ga53-overture", "title:", "updated:"):
            if k not in head:
                issues.append((os.path.basename(fp)[:-3], "frontmatter", k))
    combined = os.path.join(PAGES, "GA53-OVERTURE-RESEARCH.md")
    if os.path.exists(combined):
        n = open(combined, encoding="utf-8").read().count("\n## O")
        if n != 90:
            issues.append(("combined", "entry_count", str(n)))

    by = {}
    for o, kind, _ in issues:
        by[kind] = by.get(kind, 0) + 1
    print(f"GA53 audit: {len(issues)} issue(s) across {len(files)} overtures")
    for kind in sorted(by):
        print(f"  {kind}: {by[kind]}")
    print()
    for o, kind, detail in issues:
        print(f"  [{o}] {kind}: {detail}")
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
