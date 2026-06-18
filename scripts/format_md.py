#!/usr/bin/env python3
"""
format_md.py — render-time MARKDOWN structure for the SJC/CCB judicial decisions and
committee reports. PRESENTATION ONLY: it adds headings / lists / paragraph breaks; it NEVER
changes words (page_jsonl stays the verbatim source-of-truth used for search). Runs only at
`01_extract render` time.

Design rule learned from an adversarial review: NEVER merge content that should stay separate.
  - Section headings: a standalone line = (roman numeral, OCR variants) + a KNOWN section title
    -> '### <fixed-numeral>. <Title verbatim>'. Anchored on the closed title set, so prose never
    matches; only the numeral is corrected (e.g. "HI."->"III.", "n."->"II.").
  - "Specification N." / "Specification N:" -> own bolded paragraph (blank line before). It is
    NOT reflowed (reflow used to swallow following citations/analysis), and it REQUIRES a '.'/':'
    after the number so vote-tally lines ("Specification 1 4-12-0") and mid-sentence mentions
    ("...dismisses Specification 1 against...") are left alone.
  - Lettered sub-lists a) b) c) ... -> a real markdown list; each item's soft-wrapped tail is
    reflowed in, but bounded by blank lines, headings, other Specifications, the next lettered
    item, AND numbered items/paragraphs ("8.", "2)") so a list never absorbs a numbered sibling.
    A list must have >=2 SEQUENTIAL letters and prose content (no table/number/garbage rows).
"""
from __future__ import annotations
import re

SECTION_TITLES = [
    "Summary of the Facts", "Statement of the Facts", "Statement of the Issue",
    "Statement of the Issues", "Statement of the Issue(s)", "Statement of Major Issues Discussed",
    "Major Issues Discussed", "Reasoning and Opinion", "The Reasoning and Opinion of the Court",
    "Judgment", "The Judgment", "Judgment of the Case", "The Judgment of the Case",
    "Decision", "The Decision", "Order", "The Order", "Amends", "The Amends",
    "Recommendation", "Recommendations", "Business Referred to the Committee",
    "Voting on Proposed Decision", "Introduction", "Conclusion", "Findings of Fact",
    "Statement of the Case", "Reasoning", "Opinion",
]
_TITLES = {re.sub(r"[^a-z]", "", t.lower()) for t in SECTION_TITLES}

# numeral token (real romans + common OCR misreads: HI=III, n/ll=II, l/1=I) then '.' then title
_HEAD = re.compile(r"^\s*([ivxlcdmhn1]{1,5})\s*\.\s+(.{2,46}?)\s*$", re.I)
_NUMFIX = {"hi": "III", "ih": "III", "lll": "III", "ill": "III", "iii": "III",
           "h": "II", "ll": "II", "n": "II", "ii": "II", "l": "I", "1": "I", "i": "I",
           "iv": "IV", "v": "V", "vi": "VI", "vii": "VII", "viii": "VIII", "ix": "IX", "x": "X"}

_SPEC = re.compile(r"^\s*Specification\s+(\d+)\s*([.:])\s*(.*)$")     # REQUIRE '.' or ':'
# lettered item: optional leading bold, a letter, ')' or '.' (+ redundant '.'), content.
# Handles "a)", "a).", "a.", and born-digital "**d."
_LETTER = re.compile(r"^\s*(\*\*)?\s*([a-z])([).])\.?\s+(\S.*)$")
_NUMITEM = re.compile(r"^\s*\d+\s*[.)]\s+\S")                          # "8." / "2)" numbered item
# an Overture HEADER: line-start "Overture N" then a "." or ":" right after the number (a header
# label — "Overture 24. From Calvary", "Overture 7. Adopted by ..."), OR whitespace + "from"
# ("Overture 8 From the Presbytery"). Prose mentions ("Overture 12 of ... was referred",
# "the committee considered Overture 5") are skipped. Born-digital "**OVERTURE 1** from ..." too.
_OVERTURE = re.compile(
    r"^[#*_\s]*OVERTURE\s+\d+\b(?:\s*,[\s,A-Z]*?[A-Z]\.?)?\**"
    r"(?:\s*[.:]\s*(?:from\s+)?|\s+from\s+)", re.I)
# a lettered journal SECTION header: single uppercase letter + ALL-CAPS multi-word title
# ("A. COMMUNICATIONS TO THE ... ASSEMBLY", "B. OVERTURES ...", "C. BUSINESS CARRIED OVER ...").
# >=2 caps words avoids matching an all-caps roster name like "A. SMITH".
_LETTERSEC = re.compile(r"^[#*_\s]*([A-Z])\.\s+([A-Z][A-Z0-9&',./()-]*(?:\s+[A-Z0-9&',./()-]+)+)\s*$")
# a referral grouping ("TO THE COMMITTEE OF COMMISSIONERS ON ..."); case-sensitive caps => not prose
_REFERRAL = re.compile(r"^[#*_\s]*TO THE COMMITTEE\b")
# resolution clauses each want their own paragraph. "Strong" markers are always a clause start:
# (And) Whereas… / Be it [further] resolved|enacted|ordained… / Resolved, … / Now, therefore….
# A bare "Therefore" is a clause only INSIDE a resolution (after Whereas) OR when it carries
# "be it"/"resolv" — otherwise it is doctrinal prose ("Therefore we consider…") and is left alone.
# All require an UPPERCASE start (a lowercase wrapped "and / therefore," continuation is skipped).
_RES_STRONG = re.compile(
    r"(?:And,?\s+)?Whereas\b"
    r"|Be it\s+(?:further\s+|therefore\s+|hereby\s+)?(?:resolv|enacted|ordained)"
    r"|Resolved\s*[,:]"
    r"|Now,?\s+therefore\b", re.I)
_RES_THEREFORE = re.compile(r"(?:Now,?\s+)?Therefore\b", re.I)
# a signature/attestation line ("R. NORMAN EVANS, STATED CLERK") — NOT a lettered section heading
_SIGNATURE = re.compile(r",\s*(?:STATED CLERK|ASSISTANT CLERK|MODERATOR|CHAIR(?:MAN|PERSON)?|"
                        r"SECRETARY|CLERK|PRESIDENT|TREASURER)\.?\s*$")


def _res_kind(ln):
    """'strong' (always a clause start), 'therefore' (clause only in a resolution context), or None."""
    s = re.sub(r"^[#*_\s]+", "", ln)
    if not s or not s[:1].isupper():
        return None
    if _RES_STRONG.match(s):
        return "strong"
    if _RES_THEREFORE.match(s):
        return "strong" if re.search(r"\b(?:be it|resolv)\b", s, re.I) else "therefore"
    return None
_DISPOS = re.compile(r"\s*((?:Not\s+)?Sustained\s+\d+\s*[-–]\s*\d+(?:\s*[-–]\s*\d+)?)\s*$")
_ITEM_END = re.compile(r"[.!?)’”\"']\s*$")    # a list item is complete once a line ends a sentence


def _norm(t):
    return re.sub(r"[^a-z]", "", t.lower())


def _fix_numeral(n):
    return _NUMFIX.get(n.lower(), n.upper())


def _is_heading(ln):
    m = _HEAD.match(ln)
    if not m or _norm(m.group(2)) not in _TITLES:     # known section title? (recognition only)
        return None
    title = m.group(2).strip().strip("*").strip()     # preserve verbatim; drop redundant bold
    # h4: these are sub-sections WITHIN a paragraph-level item (e.g. "### 11-48 Report of the
    # Committee..."), so they nest one level below the existing ### paragraph headings
    return f"#### {_fix_numeral(m.group(1))}. {title}"


def _prose(s):
    words = re.findall(r"[A-Za-z]{2,}", s)
    letters = sum(c.isalpha() for c in s)
    nonspace = sum(not c.isspace() for c in s)
    return len(words) >= 2 and (nonspace == 0 or letters / nonspace >= 0.5)


def _split_dispos(block):
    m = _DISPOS.search(block)
    if m and m.start() > 0:
        return block[:m.start()].rstrip(), m.group(1).strip()
    return block, None


def _bare(s):
    """Item text with trailing bold/space stripped — for end-of-item / mid-phrase tests."""
    return re.sub(r"\*+\s*$", "", s.rstrip()).rstrip()


def _clean_item(block, bold_lead):
    block = re.sub(r"\*\*\s+\*\*", " ", block)        # merge bold spans split by a spurious break
    if bold_lead and block.rstrip().endswith("**"):   # marker+text were wrapped in one bold span
        block = block.rstrip()[:-2].rstrip()
    return re.sub(r"\s{2,}", " ", block).strip()


# Only "Exception:" nests as a sub-bullet (reviewers agree Response/Rationale/General are
# structurally distinct prose, not list children — and "General" collides with "General Assembly").
# CASE-SENSITIVE + (?![a-z]) so "Exceptions" (plural prose) and lowercase "exception." don't match;
# tolerate struck-through ~~ / bold **.
_SUBLABEL = re.compile(r"^\s*(?:~~|\*\*)*\s*Exception(?![a-z])")
_ADOPTED = re.compile(r"^\s*[_*]{0,2}Adopted[_*.]{0,3}\s*$")     # standalone vote disposition
# ANY "Capitalized Label ... :" line — used ONLY as a boundary so one labeled block never swallows
# the next (Exception must not eat a following Response/Rationale, etc.).
_LABEL = re.compile(r"^\s*(?:~~|\*\*|_)*\s*[A-Z][A-Za-z]+(?:\s+[\w\[\](),.-]+){0,3}\s*:")


def _region_end(ln):
    """Lines that terminate the whole lettered-list REGION (a higher-level structure)."""
    return bool(_is_heading(ln) or _SPEC.match(ln) or _NUMITEM.match(ln))


def _gather_stop(ln):
    """Boundaries that end one item's / one sub-element's reflowed content. Includes ANY labeled
    block and 'Adopted' so a sub-element NEVER swallows a sibling Exception/Response/Rationale/vote."""
    return (not ln.strip()) or _region_end(ln) or bool(
        _LETTER.match(ln) or _SUBLABEL.match(ln) or _ADOPTED.match(ln) or _LABEL.match(ln))


def _gather_item(lines, j, first, bold_lead):
    """Reflow a lettered item's soft-wrapped tail; STOP at a sentence end so it never swallows a
    following separate sentence. Cross ONE spurious blank only when clearly mid-phrase (, or ;)."""
    buf, k = [first.strip()], j + 1
    while k < len(lines):
        bare = _bare(" ".join(buf))
        if _ITEM_END.search(bare):
            break
        nxt = lines[k]
        if not nxt.strip():
            if bare.endswith((",", ";")) and k + 1 < len(lines) \
                    and lines[k + 1].strip() and not _gather_stop(lines[k + 1]):
                k += 1
                continue
            break
        if _gather_stop(nxt):
            break
        if not (bare.endswith((",", ";")) or re.match(r"\s*\*{0,2}_?[a-z]", nxt)):
            break
        buf.append(nxt.strip())
        k += 1
    return _clean_item(" ".join(x for x in buf if x), bold_lead), k


def _try_letter_list(lines, i):
    """Format a run of CONSECUTIVE lettered items (a) b) c) / a. / **d.) as a markdown list.
    Returns (output_lines, next_i) only if >=2 SEQUENTIAL prose items. Each item reflows its own
    soft-wrapped tail but `_gather_item` stops at any structural marker (next letter, Exception/
    Response/other Label, numbered item, disposition, heading) so an item never absorbs a following
    sub-element or a separate sentence.

    NOTE: Exception/Response/etc. sub-elements are deliberately LEFT AS FLUSH PROSE, not nested.
    Robustly nesting them needs a real structural parse, not line patterns: a `Label:` line may be a
    sub-element's OWN description (e.g. an Exception's 'General:' detail — keep) or a SIBLING block
    (e.g. a 'Response:' answering it — don't merge), and regex cannot tell the two apart. Attempting
    it (4 adversarial-review rounds) only traded merging siblings for orphaning descriptions."""
    items, j = [], i
    while j < len(lines):
        m = _LETTER.match(lines[j])
        if not m:
            break
        bold_lead, letter, sep = bool(m.group(1)), m.group(2), m.group(3)
        block, j = _gather_item(lines, j, m.group(4), bold_lead)
        block, disp = _split_dispos(block)
        items.append((letter, sep, block, disp))
    if len(items) < 2:
        return None
    letters = [it[0] for it in items]
    if any(ord(letters[x + 1]) != ord(letters[x]) + 1 for x in range(len(letters) - 1)):
        return None
    if not all(_prose(it[2]) for it in items):
        return None
    res, tail = [""], None
    for letter, sep, block, disp in items:
        res.append(f"- **{letter}{sep}** {block}".rstrip())
        tail = disp or tail
    if tail:
        res += ["", f"*{tail}*"]
    res.append("")
    return res, j


def format_text(text):
    if not text or not text.strip():
        return text
    lines = text.split("\n")
    out, i = [], 0
    in_res = False                            # are we inside a resolution (saw a Whereas)?

    def para_break():
        if out and out[-1].strip():
            out.append("")

    while i < len(lines):
        ln = lines[i]
        h = _is_heading(ln)
        if h:
            para_break()
            out += [h, ""]
            i += 1
            in_res = False
            continue
        # journal section hierarchy: lettered section (###) > referral grouping (####) > overture (#####)
        lvl = ("### " if _LETTERSEC.match(ln) and not _SIGNATURE.search(ln)
               else "#### " if _REFERRAL.match(ln) else "##### " if _OVERTURE.match(ln) else None)
        if lvl:
            core = re.sub(r"\s+", " ", re.sub(r"[#*_]+", "", ln)).strip()
            para_break()
            out += [lvl + core, ""]
            i += 1
            in_res = False
            continue
        ms = _SPEC.match(ln)
        if ms:                                # bold label + paragraph break; NO reflow (never merge)
            para_break()
            out.append(f"**Specification {ms.group(1)}{ms.group(2)}** {ms.group(3)}".rstrip())
            i += 1
            in_res = False
            continue
        if _LETTER.match(ln):
            r = _try_letter_list(lines, i)
            if r:
                block_lines, i = r
                para_break()
                out.extend(block_lines)
                in_res = False
                continue
        kind = _res_kind(ln)                  # each Whereas/Therefore/Resolved clause = its own paragraph
        if kind == "strong" or (kind == "therefore" and in_res):
            para_break()
            out.append(ln)
            i += 1
            in_res = True
            continue
        out.append(ln)
        i += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n")


if __name__ == "__main__":
    import json, sys
    vol, pg = sys.argv[1], int(sys.argv[2])
    for l in open(f"build/page_jsonl/{vol}.pages.jsonl"):
        r = json.loads(l)
        if r.get("pdf_page") == pg:
            print(format_text(r.get("text", "")))
            break
