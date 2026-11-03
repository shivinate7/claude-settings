#!/usr/bin/env python3
"""Deep audit step 6b: split checked.json into judge chunks of up to 40 findings per topic, and write run2-args.json.

    python3 split.py <dir>

Reads <dir>/args.json and <dir>/checked.json. Writes <dir>/run2/<topic>-<n>.json and <dir>/run2-args.json.
"""
import json, os, sys

d = sys.argv[1]
a = json.load(open(os.path.join(d, "args.json"), encoding="utf-8"))
topics = json.load(open(os.path.join(d, "checked.json"), encoding="utf-8"))
os.makedirs(os.path.join(d, "run2"), exist_ok=True)
chunks = []
for t, fs in sorted(topics.items()):
    for i in range(0, len(fs), 40):
        name = f"{t}-{i // 40:02d}.json"
        json.dump(fs[i:i + 40], open(os.path.join(d, "run2", name), "w", encoding="utf-8"), indent=1)
        chunks.append({"topic": t, "file": name, "n": len(fs[i:i + 40])})
out = {"dir": a["dir"], "shas": a["shas"], "paths": a["paths"], "chunks": chunks}
json.dump(out, open(os.path.join(d, "run2-args.json"), "w", encoding="utf-8"), indent=1)
print(len(chunks), "chunks;", sum(c["n"] for c in chunks), "findings")
