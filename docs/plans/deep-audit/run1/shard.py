#!/usr/bin/env python3
"""Deep audit Run 1: split rows.json into claim shards (200 rows, whole files) and copy shards (40), and write args.json.

    python3 shard.py <dir> <paths.json>

paths.json maps each repo name to its local checkout. Pinned shas come from args.template.json.
"""
import collections, json, os, sys

d, paths = sys.argv[1], json.load(open(sys.argv[2]))
j = json.load(open(os.path.join(d, "rows.json")))
os.makedirs(os.path.join(d, "shards"), exist_ok=True)
by = collections.OrderedDict()
for r in j["claims"]:
    by.setdefault((r["repo"], r["file"]), []).append(r)
shards, cur = [], []
for rows in by.values():
    if cur and len(cur) + len(rows) > 200:
        shards.append(cur)
        cur = []
    cur += rows
shards.append(cur)
for i, s in enumerate(shards):
    with open(os.path.join(d, "shards", f"c{i:03d}.tsv"), "w") as f:
        for r in s:
            f.write(f"{r['repo']}\t{r['file']}\t{r['line']}\t{','.join(r['kinds'])}\t{r['text']}\n")
dups = j["dups"]
for i in range(0, len(dups), 40):
    json.dump(dups[i:i + 40], open(os.path.join(d, "shards", f"d{i // 40:03d}.json"), "w"), indent=0)
a = json.load(open(os.path.join(d, "args.template.json")))
a["dir"], a["paths"] = os.path.abspath(d), paths
a["claim_shards"] = sorted(f for f in os.listdir(os.path.join(d, "shards")) if f.startswith("c"))
a["dup_shards"] = sorted(f for f in os.listdir(os.path.join(d, "shards")) if f.startswith("d"))
json.dump(a, open(os.path.join(d, "args.json"), "w"), indent=1)
print(len(a["claim_shards"]), "claim shards;", len(a["dup_shards"]), "copy shards;", len(a["prs"]), "PRs")
