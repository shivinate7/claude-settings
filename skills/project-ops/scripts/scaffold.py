#!/usr/bin/env python3
"""Writes the record-branch skeleton of the project-ops skill into a checkout.

    python3 scaffold.py --dest <dir> --repo <owner>/<name> [--branch roadmap]

Each file under templates/record-branch/ lands at the same path under <dest>, with its `.tmpl`
suffix dropped and `{{repo}}` and `{{branch}}` filled. Each folder in FOLDERS gets an empty
`.gitkeep`, so git keeps it. It prints each path it writes. When any target path exists, it prints
each one, writes nothing, and exits 1. A write that fails midway removes the files this run wrote,
and exits 1. A bad argument exits 2.

The templates carry the `.tmpl` suffix so that Claude Code does not load the template CLAUDE.md as
an instruction file in sessions on claude-settings.
"""
import argparse
import contextlib
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "record-branch")
FOLDERS = ("roadmap/data/steps", "roadmap/data/topics", "roadmap/data/meta", "briefs", "handoffs")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


def plan(repo, branch):
    """Returns (relative path, text) for each file to write, in a fixed order."""
    out = []
    for base, _, files in sorted(os.walk(ROOT)):
        for name in sorted(files):
            src = os.path.join(base, name)
            rel = os.path.relpath(src, ROOT).replace(os.sep, "/")
            if rel.endswith(".tmpl"):
                rel = rel[: -len(".tmpl")]
            with open(src, encoding="utf-8") as f:
                text = f.read().replace("{{repo}}", repo).replace("{{branch}}", branch)
            out.append((rel, text))
    out.extend((f"{d}/.gitkeep", "") for d in FOLDERS)
    return out


def main(argv):
    ap = argparse.ArgumentParser(description="Write the project-ops record-branch skeleton.")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--branch", default="roadmap")
    a = ap.parse_args(argv)
    if not REPO_RE.match(a.repo) or not BRANCH_RE.match(a.branch):
        print("scaffold: --repo must be owner/name, and --branch a plain branch name", file=sys.stderr)
        return 2
    if not os.path.isdir(a.dest):
        print(f"scaffold: no such folder: {a.dest}", file=sys.stderr)
        return 2
    files = plan(a.repo, a.branch)
    taken = [rel for rel, _ in files if os.path.lexists(os.path.join(a.dest, *rel.split("/")))]
    if taken:
        for rel in taken:
            print(f"scaffold: exists, nothing written: {rel}", file=sys.stderr)
        return 1
    written = []
    try:
        for rel, text in files:
            path = os.path.join(a.dest, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "x", encoding="utf-8", newline="\n") as f:
                written.append(path)
                f.write(text)
    except OSError as e:
        # Remove this run's files, so a fixed rerun does not refuse over a half skeleton.
        for path in written:
            with contextlib.suppress(OSError):
                os.remove(path)
        print(f"scaffold: write failed, files removed: {e}", file=sys.stderr)
        return 1
    for rel, _ in files:
        print(rel)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
