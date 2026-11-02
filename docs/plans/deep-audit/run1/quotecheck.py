#!/usr/bin/env python3
"""Deep audit step 3: keep a finding only when each quote is found at its file and line (within 2 lines) at the pinned sha.

    python3 quotecheck.py <dir>

Reads <dir>/args.json and <dir>/run1-findings.json. Writes <dir>/checked.json, grouped by topic. Read-only on the repos.
"""
import collections, json, os, re, subprocess, sys

d = sys.argv[1]
a = json.load(open(os.path.join(d, "args.json")))
run = json.load(open(os.path.join(d, "run1-findings.json")))
cache = {}

def lines(repo, path):
    key = (repo, path)
    if key not in cache:
        p = subprocess.run(["git", "-C", a["paths"][repo], "show", f"{a['shas'][repo]}:{path}"], capture_output=True, text=True, errors="replace")
        cache[key] = p.stdout.splitlines() if p.returncode == 0 else None
    return cache[key]

norm = lambda s: re.sub(r"\s+", " ", s).strip().strip("`").lower()

def found(repo, path, line, quote):
    if not quote or repo not in a["paths"]:
        return False
    text = lines(repo, path)
    if text is None:
        return False
    q = norm(quote)
    lo, hi = max(0, line - 3), min(len(text), line + 2)
    return q in norm(" ".join(text[lo:hi]))

kept, dropped = collections.defaultdict(list), 0
for f in run["findings"]:
    ok = found(f["a_repo"], f["a_file"], f["a_line"], f["a_quote"])
    if ok and f.get("b_quote"):
        ok = found(f.get("b_repo") or f["a_repo"], f.get("b_file", ""), f.get("b_line", 0), f["b_quote"])
    if ok:
        kept[f["topic"]].append(f)
    else:
        dropped += 1
json.dump(kept, open(os.path.join(d, "checked.json"), "w"), indent=1)
print(f"kept {sum(map(len, kept.values()))}, dropped {dropped}:", {k: len(v) for k, v in kept.items()})
