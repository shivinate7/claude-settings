#!/usr/bin/env python3
"""Deep audit Run 1 step 1: list claims and second copies from pinned shas. Read-only (git show / ls-tree)."""
import ast, collections, json, re, subprocess, sys

REPOS = json.loads(sys.argv[1])  # {name: [path, sha]}
OUT = sys.argv[2]

def git(path, *a):
    return subprocess.run(["git", "-C", path, *a], capture_output=True, text=True, errors="replace").stdout

PROSE = re.compile(r"(^|/)(CLAUDE\.md|AGENTS\.md|GLOSSARY\.md|README\.md)$|^docs/(decisions|rules|debts)/|^\.claude/rules/|^skills/[^/]+/SKILL\.md$|^agents/[^/]+\.md$|^output-styles/|^invariants/")
SKIP = re.compile(r"(^|/)(node_modules|vendor|fixtures|dist|build|\.git)/|\.min\.|/handoffs/|^docs/debts/notes\.md$")
CLAIM = [
    ("rule", re.compile(r"<!-- rule:([\w-]+) -->")),
    ("check", re.compile(r"\bCheck:|\benforce[sd]?\b|\bholds it\b|\brefuses?\b|\bguard\b", re.I)),
    ("absolute", re.compile(r"\b(never|always|every|all|only|no)\b", re.I)),
    ("owner", re.compile(r"\(owner,? 20\d\d-\d\d-\d\d")),
]
SENT = re.compile(r"(?<=[.!?])\s+")

claims, copies = [], collections.defaultdict(list)
sent_seen = collections.defaultdict(list)
for name, (path, sha) in REPOS.items():
    files = [f for f in git(path, "ls-tree", "-r", "--name-only", sha).splitlines() if not SKIP.search(f)]
    for f in files:
        if PROSE.search(f) and f.endswith(".md"):
            text = git(path, "show", f"{sha}:{f}")
            for i, line in enumerate(text.splitlines(), 1):
                kinds = [k for k, rx in CLAIM if rx.search(line)]
                if kinds and len(line.split()) >= 5 and ("rule" in kinds or "check" in kinds or "owner" in kinds or ("absolute" in kinds and f.startswith(("docs/decisions", "docs/rules", ".claude/rules")) or f.endswith("CLAUDE.md"))):
                    claims.append({"repo": name, "file": f, "line": i, "kinds": kinds, "text": line.strip()[:400]})
                for s in SENT.split(line):
                    w = re.sub(r"[^a-z0-9 ]", "", s.lower()).split()
                    if len(w) >= 12:
                        sent_seen[" ".join(w)].append((name, f, i))
        elif f.endswith(".py"):
            text = git(path, "show", f"{sha}:{f}")
            try:
                tree = ast.parse(text)
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and len(node.elts) >= 3 and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
                    key = tuple(sorted(e.value for e in node.elts))
                    copies[key].append((name, f, node.lineno))

dups = []
for key, where in copies.items():
    files = {(r, f) for r, f, _ in where}
    if len(files) >= 2 and not all("test" in f for _, f in files):
        dups.append({"kind": "list", "value": list(key)[:20], "where": [{"repo": r, "file": f, "line": l} for r, f, l in where]})
for s, where in sent_seen.items():
    files = {(r, f) for r, f, _ in where}
    if len(files) >= 2:
        dups.append({"kind": "sentence", "value": s[:300], "where": [{"repo": r, "file": f, "line": l} for r, f, l in where]})
json.dump({"claims": claims, "dups": dups}, open(OUT, "w"))
print(f"claims {len(claims)} dups {len(dups)}", collections.Counter(c['repo'] for c in claims))
