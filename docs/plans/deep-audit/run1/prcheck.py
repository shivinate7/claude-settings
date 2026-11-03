#!/usr/bin/env python3
"""Deep audit step 6c: recheck PR findings that quotecheck dropped, with a_quote read at origin/<ref> and b_quote at the pinned main sha.

    python3 prcheck.py <dir>

Reads <dir>/args.json, <dir>/run1-findings.json and <dir>/checked.json. Adds each PR finding that passes to checked.json, under its topic. Read-only on the repos.
"""
import json, os, re, subprocess, sys

d = sys.argv[1]
a = json.load(open(os.path.join(d, "args.json"), encoding="utf-8"))
run = json.load(open(os.path.join(d, "run1-findings.json"), encoding="utf-8"))["findings"]
checked = json.load(open(os.path.join(d, "checked.json"), encoding="utf-8"))
refs = {p["n"]: p["ref"] for p in a["prs"]}
cs = a["paths"]["claude-settings"]
norm = lambda s: re.sub(r"\s+", " ", s).strip().strip("`").lower()
cache = {}

def lines(rev, path):
    if (rev, path) not in cache:
        p = subprocess.run(["git", "-C", cs, "show", f"{rev}:{path}"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        cache[(rev, path)] = p.stdout.splitlines() if p.returncode == 0 else None
    return cache[(rev, path)]

def found(rev, path, line, quote):
    text = lines(rev, path) if quote and path else None
    if text is None:
        return False
    lo, hi = max(0, line - 3), min(len(text), line + 2)
    return norm(quote) in norm(" ".join(text[lo:hi]))

kept = {json.dumps(f, sort_keys=True) for v in checked.values() for f in v}
added = tried = 0
for f in run:
    m = re.match(r"PR #(\d+)", f["why"])
    if not m or json.dumps(f, sort_keys=True) in kept or int(m.group(1)) not in refs:
        continue
    tried += 1
    ref = f"origin/{refs[int(m.group(1))]}"
    ok = found(ref, f["a_file"], f["a_line"], f["a_quote"])
    if ok and f.get("b_quote"):
        ok = found(a["shas"]["claude-settings"], f.get("b_file", ""), f.get("b_line", 0), f["b_quote"]) or found(ref, f.get("b_file", ""), f.get("b_line", 0), f["b_quote"])
    if ok:
        checked.setdefault(f["topic"], []).append(f)
        added += 1
json.dump(checked, open(os.path.join(d, "checked.json"), "w", encoding="utf-8"), indent=1)
print(f"PR findings rechecked {tried}, added {added}")
