#!/usr/bin/env python3
"""Fails when a changed plugin's plugin.json version did not rise against origin/main.

`claude plugin update` keeps the installed copy when the version is the same, so a changed mod with
no bump never reaches an install. Plugin folders: every folder under
mods/ with a plugin.json, and every folder .claude-plugin/marketplace.json lists as a "./" source.
The diff is origin/main...HEAD (the merge base), so a main that moved ahead does not flag a plugin
this branch never touched. Plugins are matched by plugin.json "name", not by folder: the install
cache keys by name, so a folder move that keeps name and version fails. A name with no match at the
merge base is new and passes if its version is valid. A folder deleted whole is not checked. A version
is MAJOR.MINOR.PATCH, numbers only: a prerelease is refused. A leading BOM is ignored. An unreadable
diff, plugin.json or marketplace.json exits 1, also outside CI.

    python3 lint/check_mod_versions.py        # no arguments
"""
import json
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = ".claude-plugin/plugin.json"
MARKET = ".claude-plugin/marketplace.json"
FAIL = "check_mod_versions: FAIL: "


def git(*args):
    r = _nowindow.run(("git",) + args, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print("check_mod_versions: UNKNOWN, git %s failed: %s" % (args[0], r.stderr.strip()))
        sys.exit(1)
    return r.stdout


def blob(rev, path):
    """File text at rev, or None when the path is absent there."""
    if not git("ls-tree", "--name-only", rev, "--", path).strip():
        return None
    return git("show", "%s:%s" % (rev, path))


def read(text):
    """(name, version text, (major, minor, patch)) from plugin.json text, or None when unreadable."""
    try:
        d = json.loads(text.lstrip("﻿"))
        n, v = d.get("name"), d.get("version")
    except (ValueError, AttributeError):
        return None
    if not isinstance(n, str) or not isinstance(v, str) or not re.fullmatch(r"\d+\.\d+\.\d+", v):
        return None
    return n, v, tuple(map(int, v.split(".")))


def sources(text):
    """The "./" folders a marketplace.json lists. Raises on an unreadable file."""
    got = [p.get("source") for p in json.loads(text.lstrip("﻿"))["plugins"]]
    return {s[2:].rstrip("/") for s in got if isinstance(s, str) and s.startswith("./")}


if len(sys.argv) > 1:
    print(FAIL + "takes no arguments")
    sys.exit(1)

base = git("merge-base", "origin/main", "HEAD").strip()
changed = [p for p in git("diff", "--name-only", "--no-renames", "-z", "origin/main...HEAD").split("\0") if p]


def hit(folder):
    return any(p.startswith(folder + "/") for p in changed)


try:
    with open(os.path.join(ROOT, *MARKET.split("/")), encoding="utf-8") as f:
        listed = sources(f.read())
    old_market = blob(base, MARKET)
    old_listed = sources(old_market) if old_market else set()
except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
    print(FAIL + "%s is unreadable: %s" % (MARKET, e))
    sys.exit(1)

# Plugins at the merge base, by name. An unreadable base plugin.json fails only when its folder changed.
bad = False
old_by_name = {}
mods = [e for e in git("ls-tree", "--name-only", base, "mods/").split("\n") if e]
for folder in sorted(set(mods) | old_listed):
    text = blob(base, folder + "/" + PLUGIN)
    if text is None:
        continue
    got = read(text)
    if got:
        old_by_name[got[0]] = (folder, got[1], got[2])
    elif hit(folder):
        print(FAIL + "%s has no readable name and MAJOR.MINOR.PATCH version in base plugin.json" % folder)
        bad = True

touched = {"/".join(p.split("/")[:2]) for p in changed if p.startswith("mods/") and p.count("/") >= 2}
for folder in sorted(touched | listed):
    if not hit(folder) or not git("ls-tree", "--name-only", "HEAD", "--", folder).strip():
        continue  # unchanged, or the folder is gone: nothing ships from it
    text = blob("HEAD", folder + "/" + PLUGIN)
    if text is None:
        if folder in listed or blob(base, folder + "/" + PLUGIN) is not None:
            print(FAIL + "%s has no plugin.json at HEAD" % folder)
            bad = True
        continue  # else a mods/ folder that is not a plugin
    got = read(text)
    if not got:
        print(FAIL + "%s has no readable name and MAJOR.MINOR.PATCH version in HEAD plugin.json" % folder)
        bad = True
        continue
    old = old_by_name.get(got[0])
    if old and got[2] <= old[2]:
        moved = "" if old[0] == folder else " (was %s)" % old[0]
        print(FAIL + "%s %s -> %s%s" % (folder, old[1], got[1], moved))
        bad = True
sys.exit(1 if bad else 0)
