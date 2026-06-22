#!/usr/bin/env python3
"""Link bolded past-overture cites (**GA<ord> O<num>**) in GA53 findings to their
individual overture pages, when one exists. Idempotent: skips already-linked
(**[GA.. O..](...)**). Leaves the bullet's existing minutes deep-link intact."""
import json, re, glob, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
pmap = json.load(open(f"{ROOT}/index/overture_pages_map.json"))

# **GA51 O26** but NOT **[GA51 O26](...) — negative lookahead on the '[' after **
PAT = re.compile(r"\*\*(GA(\d+) O(\d+))\*\*")

def main():
    linked = files = 0
    for fp in sorted(glob.glob(f"{ROOT}/ga53/findings/O*.md")):
        txt = open(fp).read()
        cnt = [0]
        def repl(m):
            key = f"GA{int(m.group(2))} O{m.group(3)}"
            page = pmap.get(key)
            if not page:
                return m.group(0)
            cnt[0] += 1
            return f"**[{m.group(1)}](../{page})**"
        out = PAT.sub(repl, txt)
        if out != txt:
            open(fp, "w").write(out)
            files += 1; linked += cnt[0]
    print(f"linked {linked} overture cites across {files} findings")

if __name__ == "__main__":
    main()
