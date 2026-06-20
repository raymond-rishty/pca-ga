#!/usr/bin/env python3
"""ga53_mark_amended.py — mark GA53 overture(s) as amended on a date.

Stamps a per-overture date into ga53/updated.json and re-renders both trees, so the local-notes
**staleness banner** fires for anyone whose note predates the amendment (see SPEC-GA53-NOTES.md §4).
Use it whenever an overture is amended in the Overtures Committee / on the floor. (For a *moot*
overture, also edit its findings text to say so — this helper only handles the date stamp.)

Usage:
  ga53_mark_amended.py O37 [O56 ...]            # mark amended today
  ga53_mark_amended.py O37 --date 2026-05-12    # mark amended on a specific date
  ga53_mark_amended.py --clear O37 [...]        # remove the override (revert to default date)
  ga53_mark_amended.py --list                   # show current overrides
  ga53_mark_amended.py O37 --no-render          # update updated.json only (render later)

After it runs: review `git -C /workspace/dist/pca-ga status`, then commit & push (Pages rebuilds ~3 min).
Bump the page SW cache (pca-ga53-pages-v*) when you want installed users to pick up the amended page.
"""
import json, os, re, sys, subprocess, datetime

SRC = os.environ.get("GA53_SRC", "/workspace/ga53")
UPD = os.path.join(SRC, "updated.json")
BUILD = "/workspace"
PUB = "/workspace/dist/pca-ga"
RENDER = os.path.join(BUILD, "scripts", "36_ga53_overtures.py")


def load():
    try:
        return json.load(open(UPD, encoding="utf-8"))
    except Exception:
        return {}


def save(d):
    ordered = dict(sorted(d.items(), key=lambda kv: int(kv[0][1:])))
    json.dump(ordered, open(UPD, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def norm(o):
    o = o.upper()
    if not o.startswith("O"):
        o = "O" + o
    if not re.fullmatch(r"O\d{1,2}", o) or not (1 <= int(o[1:]) <= 90):
        raise SystemExit(f"error: '{o}' is not a valid overture (O1–O90)")
    return o


def render():
    env = dict(os.environ, GA53_SRC=SRC)
    for root in (BUILD, PUB):
        if os.path.isdir(root):
            subprocess.run([sys.executable, RENDER, root], env=env, check=True)


def main():
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__); return
    if "--list" in args:
        d = load()
        if not d:
            print("No amendment overrides — all overtures use the default date.")
        else:
            print("Amended overrides (overture → date):")
            for k, v in sorted(d.items(), key=lambda kv: int(kv[0][1:])):
                print(f"  {k}: {v}")
        return

    do_render = "--no-render" not in args
    clear = "--clear" in args
    date = datetime.date.today().isoformat()
    if "--date" in args:
        i = args.index("--date")
        date = args[i + 1]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise SystemExit(f"error: --date must be YYYY-MM-DD, got '{date}'")

    skip = {"--clear", "--no-render", "--date", date}
    nums = [norm(a) for a in args if a not in skip and not a.startswith("--")]
    if not nums:
        raise SystemExit("error: name at least one overture, e.g. ga53_mark_amended.py O37")

    d = load()
    if clear:
        for o in nums:
            d.pop(o, None)
        action = "cleared"
    else:
        for o in nums:
            d[o] = date
        action = f"marked amended {date}"
    save(d)
    print(f"{action}: {', '.join(nums)}  ->  {UPD}")
    if do_render:
        render()
        print("re-rendered both trees. Review, then commit & push the GA53 pages.")
    else:
        print("updated.json written; skipped render (--no-render).")


if __name__ == "__main__":
    main()
