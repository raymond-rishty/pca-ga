#!/usr/bin/env python3
"""
22_dispositions.py — capture each overture's FINAL disposition, including the cross-GA
ratification chain for constitutional BCO amendments ("approved & ratified" needs the NEXT
year's minutes).

Three phases:
  prep  : (local) extract candidate disposition lines + ratification-declaration lines per GA
          into index/disp_candidates/<vol>.txt and index/ratif_candidates/<vol>.txt, so the
          workflow agents read compact focused input instead of whole volumes.
  link  : (local, run AFTER the workflow writes index/dispositions.json + index/ratifications.json)
          join year-N affirmative BCO-amendment overtures to year-N+1/N+2 ratification records by
          BCO section, and write the final disposition onto each catalogue overture
          (index/overture_dispositions.jsonl, folded into the DB by 19_export).

CLI:  22_dispositions.py prep
      22_dispositions.py link
"""
from __future__ import annotations
import collections, glob, json, os, re, sys

ROOT = "/workspace"
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")

# a committee-report DISPOSITION line: mentions an overture AND a verdict verb
_OVN = re.compile(r"(?i)\bovertures?\b")
_VERDICT = re.compile(r"(?i)(answered in the (affirmative|negative)|answered by reference|"
                      r"be answered|in the (affirmative|negative)|referred to|recommitted|"
                      r"\bwithdrawn\b|out of order|carried over|postponed)")
# a RATIFICATION-declaration line: a ratify/consent verb near a constitutional referent
_RAT = re.compile(r"(?i)(ratif|advice and consent|two-thirds of the presbyteries|declared adopted|"
                  r"now in effect|did not receive|failed to receive|was not ratified|"
                  r"presbyteries (have |having )?(approved|adopted|voted))")
_CONST = re.compile(r"(?i)(\bBCO\b|book of church order|amendment|constitution|chapter|paragraph)")


def _paragraphs(text):
    # reflow wrapped lines into blank-line-separated paragraphs, so a disposition split across
    # line wraps ("Overture 10 …\n be answered in the affirmative") is matched as one unit
    for block in re.split(r"\n\s*\n", text):
        s = re.sub(r"\s+", " ", block).strip()
        if s:
            yield s


def prep():
    for sub in ("disp_candidates", "ratif_candidates"):
        os.makedirs(os.path.join(IDX, sub), exist_ok=True)
    dn, rn = {}, {}
    for p in sorted(glob.glob(os.path.join(MD, "ga*_*.md"))):
        vol = os.path.basename(p).split(".")[0]
        disp, rat = [], []
        for s in _paragraphs(open(p).read()):
            if len(s) < 10:
                continue
            if _OVN.search(s) and _VERDICT.search(s):
                disp.append(s[:600])
            if _RAT.search(s) and _CONST.search(s):
                rat.append(s[:600])
        open(os.path.join(IDX, "disp_candidates", f"{vol}.txt"), "w").write("\n".join(disp) + "\n")
        open(os.path.join(IDX, "ratif_candidates", f"{vol}.txt"), "w").write("\n".join(rat) + "\n")
        dn[vol], rn[vol] = len(disp), len(rat)
    print("disposition-candidate lines per GA:", sum(dn.values()), "total")
    print("ratification-candidate lines per GA:", sum(rn.values()), "total")
    print("vols WITH ratification candidates:", sum(1 for v in rn.values() if v))
    # emit the JS array literals to paste into the workflow (args global is unreliable)
    print("\nDISP_VOLS =", json.dumps([v for v in sorted(dn) if dn[v]]))
    print("\nRAT_VOLS =", json.dumps([v for v in sorted(rn) if rn[v]]))


_DISP_LABEL = {"affirmative": "Approved", "affirmative_amended": "Approved (amended)",
               "negative": "Answered in the negative", "by_reference": "Answered by reference",
               "referred": "Referred", "recommitted": "Recommitted", "withdrawn": "Withdrawn",
               "carried_over": "Carried over", "out_of_order": "Out of order", "other": "Other"}
# pick a single disposition when an overture has several committee mentions: a definitive verdict
# wins over a procedural one
_PRIORITY = ["affirmative_amended", "affirmative", "negative", "by_reference", "recommitted",
             "referred", "withdrawn", "carried_over", "out_of_order", "other"]


def _year_ord(vol):
    m = re.match(r"ga(\d+)_(\d+)", vol)
    return int(m.group(1)), int(m.group(2))


def _bco_from_title(title):
    return set(re.findall(r"(?i)\bBCO[\s,]*(\d+-\d+(?:-\d+)?)", title or ""))


def _is_bco_amendment(title, bco):
    # constitutional BCO amendment (needs ratification) — has a BCO section AND the title is an
    # amendment, but NOT an RAO/Bylaws amendment
    if not bco:
        return False
    t = (title or "").lower()
    if re.search(r"\b(rao|bylaw|standing rule)\b", t):
        return False
    return bool(re.search(r"\bamend|\bbco\b|strike|delete|insert|substitute|add(ing)?\b", t)) or True


def _norm_sec(s):
    # canonicalize a BCO section: the changes-list uses dot sub-notation ("21-5.6", "14-1.12"),
    # titles use dashes/none ("21-5") — normalize both to dash-joined so "21-5" prefix-matches "21-5.6"
    return re.sub(r"[.\s]+", "-", str(s).strip()).strip("-")


def _sec_match(a, b):
    A = [_norm_sec(x) for x in a]
    B = [_norm_sec(y) for y in b]
    for x in A:
        for y in B:
            if x == y or x.startswith(y + "-") or y.startswith(x + "-"):
                return True
    return False


def link():
    disp_data = json.load(open(os.path.join(IDX, "dispositions.json")))
    rat_data = json.load(open(os.path.join(IDX, "ratifications.json")))
    disp = {}
    for d in disp_data:
        for r in d["results"]:
            disp.setdefault((d["vol"], r["number"]), []).append(r)
    # AUTHORITATIVE ratification ledger: pcahistory.org BCO-changes page (index/bco_changes.jsonl),
    # year = the year a section was actually ADOPTED into the BCO (i.e. ratified). Keyed by year.
    official = {}
    for l in open(os.path.join(IDX, "bco_changes.jsonl")):
        d = json.loads(l)
        official[d["year"]] = set(str(s) for s in (d.get("bco_sections") or []))
    # NOTE: the Digest's "adopted" amendment labels are NOT used as a ratification source — they
    # are LLM-extracted and proved unreliable (e.g. it marked BCO 12-5 "adopted 2002", which is NOT
    # in the authoritative changes-list; the women-preaching amendment was sent down but not adopted).
    # Every TRUE adoption is already in bco_changes.jsonl, so ratification rests on it alone.
    # primary-source ratification verifications (ratification-verify workflow read the actual
    # ratifying-GA minutes), keyed (vol, number) — these override a bare "not located"
    verified = {}
    vp = os.path.join(IDX, "ratification_verified.jsonl")
    if os.path.exists(vp):
        for l in open(vp):
            d = json.loads(l)
            verified[(d["vol"], d["number"])] = d
    # FALLBACK disposition source: Digest dispositions, keyed (year, number)
    dig_disp = {}
    ddp = os.path.join(IDX, "digest_dispositions.jsonl")
    if os.path.exists(ddp):
        for l in open(ddp):
            d = json.loads(l)
            dig_disp.setdefault((d["year"], d["number"]), []).append({"disposition": d["disposition"]})
    # Phase B (minutes-extracted) used only for explicit FAILED-ratification signals, by year
    fail_by_year = {}
    for d in rat_data:
        _, yr = _year_ord(d["vol"])
        for r in d["results"]:
            if r.get("outcome") == "failed":
                fail_by_year.setdefault(yr, set()).update(r.get("bco") or [])
    titles = {}   # keyed per-page so reused numbers (early GAs) don't collide on their titles
    for l in open(os.path.join(IDX, "overture_titles.jsonl")):
        e = json.loads(l)
        titles[(e["vol"], e["number"], e.get("pdf_page"))] = e["title"]

    def choose(ds):
        present = {r["disposition"] for r in ds}
        for p in _PRIORITY:
            if p in present:
                return p
        return None

    def ratify_lookup(bco, year):
        # an approved constitutional amendment is ADOPTED at the next (or 2nd-next) GA, per the
        # official ledger; check those years' adopted sections for a match
        for ny in (year + 1, year + 2):
            if _sec_match(bco, official.get(ny, set())):
                return "adopted", ny
        for ny in (year + 1, year + 2):                 # else an explicit FAILED signal in minutes
            if _sec_match(bco, fail_by_year.get(ny, set())):
                return "failed", ny
        return None, None

    # how many distinct catalogue entries share each (vol, number) — early GAs reused numbers for
    # different overtures, so disposition/BCO keyed by number must NOT bleed across them
    n_entries = collections.Counter()
    structs = {}
    for p in sorted(glob.glob(os.path.join(IDX, "structure", "ga*.json"))):
        t = json.load(open(p)); structs[p] = t
        for ov in t["overtures"]:
            n_entries[(t["volume"], ov["number"])] += 1

    out = []
    for p, t in structs.items():
        vol = t["volume"]
        ordn, year = _year_ord(vol)
        for ov in t["overtures"]:
            num = ov["number"]
            ds = disp.get((vol, num), [])
            code = choose(ds)
            if code is None:                          # fall back to the Digest's disposition
                code = choose(dig_disp.get((year, num), []))
            pages = ov.get("pages") or [ov["pdf_page"]]
            title = next((titles[(vol, num, p)] for p in pages if (vol, num, p) in titles), "")
            bco = _bco_from_title(title)              # per-entry, reliable
            if n_entries[(vol, num)] == 1:            # borrow text-extracted BCO only when unambiguous
                for r in ds:
                    bco |= set(r.get("bco") or [])
            final = None
            ratified = None
            if code in ("affirmative", "affirmative_amended"):
                if _is_bco_amendment(title, bco):
                    outcome, ny = ratify_lookup(bco, year)
                    if outcome == "adopted":
                        final = f"Approved & ratified ({ny})"; ratified = True
                    elif outcome == "failed":
                        final = "Approved but not ratified"; ratified = False
                    else:
                        final = "Approved → sent to presbyteries; ratification not located"
                else:
                    final = "Adopted (final)"
            elif code:
                final = _DISP_LABEL[code]
            # primary-source verification overrides a bare "not located" (read from ratifying minutes)
            if (final or "").startswith("Approved → sent") and (vol, num) in verified:
                vo = verified[(vol, num)]
                if vo.get("outcome") == "ratified":
                    final = f"Approved & ratified ({vo.get('ratifying_year') or 'verified'})"; ratified = True
                elif vo.get("outcome") == "failed":
                    final = "Approved but not ratified"; ratified = False
            note = verified.get((vol, num), {}).get("evidence")
            out.append({"vol": vol, "number": num, "pdf_page": ov["pdf_page"],
                        "disposition": _DISP_LABEL.get(code),
                        "final_disposition": final, "ratified": ratified, "bco": sorted(bco),
                        "ratification_note": (note or "")[:400] or None})
    with open(os.path.join(IDX, "overture_dispositions.jsonl"), "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    fc = collections.Counter(r["final_disposition"] for r in out)
    print(f"wrote {len(out)} disposition records -> index/overture_dispositions.jsonl")
    for k, v in fc.most_common():
        print(f"  {v:5}  {k}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prep":
        prep()
    elif cmd == "link":
        link()
    else:
        print(__doc__)
