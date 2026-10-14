#!/usr/bin/env python3
"""Fails when a plugin folder changed against origin/main and its plugin.json version did not rise.

`claude plugin update` keeps the installed copy when the version is the same, so a changed mod with
no bump never reaches an install (incident 2026-10-14, PR 430). Plugin folders: every folder under
mods/ with a plugin.json, and every folder .claude-plugin/marketplace.json lists as a "./" source.
The diff is origin/main...HEAD (the merge base), so a main that moved ahead does not flag a plugin
this branch never touched. A folder with no plugin.json at the merge base is new and passes. A folder
deleted whole is not gated. A version is MAJOR.MINOR.PATCH, numbers only: a prerelease is refused.
An unreadable diff, plugin.json or marketplace.json exits 1, also outside CI.

    python3 lint/check_mod_versions.py        # no arguments
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = ".claude-plugin/plugin.json"
MARKET = ".claude-plugin/marketplace.json"
FAIL = "check_mod_versions: FAIL: "


def git(*args):
    r = subprocess.run(("git",) + args, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print("check_mod_versions: UNKNOWN, git %s failed: %s" % (args[0], r.stderr.strip()))
        sys.exit(1)
    return r.stdout


def blob(rev, path):
    """File text at rev, or None when the path is absent there."""
    if not git("ls-tree", "--name-only", rev, "--", path).strip():
        return None
    return git("show", "%s:%s" % (rev, path))


def version(text, folder, where):
    """(text, (major, minor, patch)) from plugin.json text, or exit 1 naming the folder."""
    try:
        v = json.loads(text).get("version")
    except (ValueError, AttributeError):
        v = None
    if not isinstance(v, str) or not re.fullmatch(r"\d+\.\d+\.\d+", v):
        print(FAIL + "%s has no readable MAJOR.MINOR.PATCH version in %s plugin.json" % (folder, where))
        sys.exit(1)
    return v, tuple(map(int, v.split(".")))


if len(sys.argv) > 1:
    print(FAIL + "takes no arguments")
    sys.exit(1)

base = git("merge-base", "origin/main", "HEAD").strip()
changed = [p for p in git("diff", "--name-only", "--no-renames", "-z", "origin/main...HEAD").split("\0") if p]

try:
    with open(os.path.join(ROOT, *MARKET.split("/")), encoding="utf-8") as f:
        sources = [p.get("source") for p in json.load(f)["plugins"]]
except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
    print(FAIL + "%s is unreadable: %s" % (MARKET, e))
    sys.exit(1)
listed = {s[2:].rstrip("/") for s in sources if isinstance(s, str) and s.startswith("./")}

touched = {"/".join(p.split("/")[:2]) for p in changed if p.startswith("mods/") and p.count("/") >= 2}
bad = False
for folder in sorted(touched | listed):
    if not any(p.startswith(folder + "/") for p in changed):
        continue
    if not git("ls-tree", "--name-only", "HEAD", "--", folder).strip():
        continue  # the folder is gone: nothing ships from it
    old, new = blob(base, folder + "/" + PLUGIN), blob("HEAD", folder + "/" + PLUGIN)
    if old is None and (new is not None or folder not in listed):
        continue  # a new plugin, or a mods/ folder that is not a plugin
    if new is None:
        print(FAIL + "%s has no plugin.json at HEAD" % folder)
        bad = True
        continue
    (ov, oldn), (nv, newn) = version(old, folder, "base"), version(new, folder, "HEAD")
    if newn <= oldn:
        print(FAIL + "%s %s -> %s" % (folder, ov, nv))
        bad = True
sys.exit(1 if bad else 0)
