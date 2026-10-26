#!/usr/bin/env python3
"""List the copies a child repo holds of claude-settings things. Read-only. Standard library only.

    python3 lint/find_copies.py <child> [--parent <dir>] [--json] [--threshold 0.8]

Rule building-one-home-per-capability: a shared thing has one home, and a child extends it,
never copies it. Shared skills are pinned, never vendored. This tool reports copies. It fixes
none, and it writes nothing.

It reports two kinds of copy:
- skill: a child folder with a SKILL.md whose folder name or frontmatter `name` is a parent
  skill under skills/. State `same` or `drifted`, with the files that differ.
- file: a child file byte-equal or near-equal to a parent file. Near-equal compares the sets
  of significant lines as plain text: the share of the parent's lines that the child holds, so
  a header added on top still reads as a copy. It never parses code,
  so a comment opener or a quote inside a string cannot change a result.

Blind spots, by design: a file under MIN_LINES significant lines or MIN_BYTES is boilerplate
and never a copy; a child file with over CHILD_GROWTH times the parent's lines only quotes it.
A skill matches on its folder name or its `name`, so a renamed skill with a new `name` shows only
through its files.

Files inside a reported skill copy are not reported again. License and lock files, parent
files under an examples/ or templates/ folder, small files and files over MAX_BYTES are skipped. Exit 0: no copies. Exit 1: copies found.
Exit 2: the child or parent cannot be read, so the result is unknown.
Cost: one `git ls-files` per tree and one read of each listed file. No process stays running.
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

MAX_BYTES = 1_000_000
MIN_BYTES = 200  # a byte-equal file smaller than this is boilerplate, not a copy
MIN_LINES = 12  # a near-equal file needs this many significant lines on the parent side
CHILD_GROWTH = 2  # a child with more than this many times the parent's lines only quotes it
COMMON = 20  # a line in more parent files than this picks no candidate
SKIP_NAMES = re.compile(r"^(LICENSE|LICENCE|NOTICE|COPYING)(\..*)?$|^\.git(ignore|attributes|keep)$|"
                        r"^(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|Cargo\.lock|poetry\.lock)$",
                        re.IGNORECASE)
TEMPLATE_DIRS = {"examples", "templates"}  # a parent file here is meant to be copied, so it is no copy
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
DEFAULT_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def list_files(root):
    """Tracked files when root is a git tree, else every file outside SKIP_DIRS."""
    if os.path.exists(os.path.join(root, ".git")):
        proc = _nowindow.run(["git", "-C", root, "ls-files", "-z"], capture_output=True)
        if proc.returncode != 0:
            return None  # a walk would add untracked files, so the result is unknown
        return sorted(p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return sorted(out)


def read(root, rel):
    path = os.path.join(root, rel)
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def significant_lines(data):
    if b"\0" in data[:8192]:
        return None
    lines = set()
    for line in data.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if len(line) >= 8 and re.search(r"\w", line):
            lines.add(line)
    return lines


def skill_name(data):
    m = re.match(rb"---\r?\n(.*?)\r?\n---", data or b"", re.DOTALL)
    if m:
        n = re.search(rb"^name:\s*['\"]?([\w.-]+)", m.group(1), re.MULTILINE)
        if n:
            return n.group(1).decode()
    return None


def under(rel, folder):
    return rel.startswith(folder + "/")


def find_skill_copies(parent, pfiles, child, cfiles):
    pskills = {}
    for rel in pfiles:
        parts = rel.split("/")
        if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
            pskills[parts[1]] = "skills/" + parts[1]
    found = []
    for rel in cfiles:
        if rel.split("/")[-1] != "SKILL.md":
            continue
        if "/" not in rel:
            continue  # a child whose root is a skill is that skill's own repo, not a copy
        folder = rel.rsplit("/", 1)[0]
        dirname = folder.split("/")[-1]
        name = dirname if dirname in pskills else skill_name(read(child, rel))
        if name not in pskills:
            continue
        pdir = pskills[name]
        pset = {r[len(pdir) + 1:] for r in pfiles if r.startswith(pdir + "/")}
        cset = {r[len(folder) + 1:] for r in cfiles if under(r, folder)}
        differ = sorted(r for r in pset & cset if read(parent, pdir + "/" + r) != read(child, folder + "/" + r))
        only_p, only_c = sorted(pset - cset), sorted(cset - pset)
        state = "same" if not (differ or only_p or only_c) else "drifted"
        found.append({"skill": name, "child_path": folder, "state": state, "differ": differ,
                      "only_in_parent": only_p, "only_in_child": only_c})
    return found


def find_file_copies(parent, pfiles, child, cfiles, skip_folders, threshold):
    by_hash, lines_of, index = {}, {}, {}
    for rel in pfiles:
        if SKIP_NAMES.match(rel.split("/")[-1]) or TEMPLATE_DIRS & set(rel.split("/")[:-1]):
            continue
        data = read(parent, rel)
        if data is None:
            continue
        if len(data) >= MIN_BYTES:
            by_hash.setdefault(hashlib.sha256(data).hexdigest(), []).append(rel)
        lines = significant_lines(data)
        if lines and len(lines) >= MIN_LINES:
            lines_of[rel] = lines
            for line in lines:
                index.setdefault(line, []).append(rel)
    found = []
    for rel in cfiles:
        base = rel.split("/")[-1]
        if SKIP_NAMES.match(base) or any(under(rel, f) for f in skip_folders):
            continue
        data = read(child, rel)
        if data is None:
            continue

        def rank(p):
            return (p.split("/")[-1] != base, p)

        same = by_hash.get(hashlib.sha256(data).hexdigest()) if len(data) >= MIN_BYTES else None
        if same:
            found.append({"child": rel, "parent": min(same, key=rank), "kind": "byte-equal", "score": 1.0})
            continue
        clines = significant_lines(data)
        if not clines:
            continue
        counts = {}
        for line in clines:
            hits = index.get(line, ())
            if len(hits) <= COMMON:
                for p in hits:
                    counts[p] = counts.get(p, 0) + 1
        best = None
        for p in counts:
            plines = lines_of[p]
            if len(clines) > CHILD_GROWTH * len(plines):
                continue
            score = len(plines & clines) / len(plines)
            if score >= threshold and (best is None or (-score, rank(p)) < (-best[1], rank(best[0]))):
                best = (p, score)
        if best:
            found.append({"child": rel, "parent": best[0], "kind": "near-equal", "score": round(best[1], 2)})
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("child", help="the child repo root")
    ap.add_argument("--parent", default=DEFAULT_PARENT, help="the claude-settings root (default: this clone)")
    ap.add_argument("--json", action="store_true", help="print one JSON object")
    ap.add_argument("--threshold", type=float, default=0.8, help="near-equal floor, 0 to 1 (default 0.8)")
    args = ap.parse_args(argv)
    child, parent = os.path.abspath(args.child), os.path.abspath(args.parent)
    for label, root in (("child", child), ("parent", parent)):
        if not os.path.isdir(root):
            print(f"unknown: the {label} folder {root} cannot be read")
            return 2
    if not os.path.isdir(os.path.join(parent, "skills")):
        print(f"unknown: {parent} has no skills/ folder, so it is not a claude-settings tree")
        return 2
    pfiles, cfiles = list_files(parent), list_files(child)
    for label, root, files in (("parent", parent, pfiles), ("child", child, cfiles)):
        if files is None:
            print(f"unknown: git ls-files failed in the {label} {root}")
            return 2
    skills = find_skill_copies(parent, pfiles, child, cfiles)
    files = find_file_copies(parent, pfiles, child, cfiles, [s["child_path"] for s in skills], args.threshold)
    if args.json:
        print(json.dumps({"child": child, "skills": skills, "files": files}, indent=1))
    else:
        for s in skills:
            detail = ""
            if s["state"] == "drifted":
                detail = (f": {len(s['differ'])} differ, {len(s['only_in_parent'])} only in parent, "
                          f"{len(s['only_in_child'])} only in child")
            print(f"skill {s['skill']} copied at {s['child_path']} ({s['state']}{detail})")
        for f in files:
            print(f"file {f['child']} copies {f['parent']} ({f['kind']}, {f['score']})")
        n = len(skills) + len(files)
        print(f"{n} copies of claude-settings things" if n else "no copies of claude-settings things")
    return 1 if skills or files else 0


if __name__ == "__main__":
    sys.exit(main())
