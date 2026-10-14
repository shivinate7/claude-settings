#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in decisions/, deferred/ and debts/. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

    python3 lint/check_record_slugs.py [--dir FOLDER] [file ...]
        # files given: check those, skip git
        # --dir: the one records folder, relative to the repo root, instead of the default
        # folders. A folder that is missing, misspelled, or a file is red, never green.
"""
import os
import subprocess
import sys

MAX = 32
DIRS = ("decisions/", "deferred/", "debts/")  # one line: hooks/guard.py reads it
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def added():
    cmd = ["git", "diff", "--name-only", "--diff-filter=A", "origin/main...HEAD"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print("check_record_slugs: UNKNOWN, git diff failed: " + r.stderr.strip())
        sys.exit(1 if os.environ.get("CI") else 0)  # CI exit code is a verdict: unknown is red there
    return r.stdout.split()


args = []
for a in sys.argv[1:]:  # --dir=VALUE is --dir VALUE; an empty VALUE then fails closed below
    args += ["--dir", a[6:]] if a.startswith("--dir=") else [a]
if args.count("--dir") > 1:  # a second --dir would stay in args and be read as file names
    print("check_record_slugs: FAIL: --dir given more than once")
    sys.exit(1)
if "--dir" in args:  # the records folder, for a repo that keeps its records elsewhere
    i = args.index("--dir")
    given = args[i + 1] if i + 1 < len(args) else ""
    DIRS = (os.path.normpath(given).replace("\\", "/").rstrip("/") + "/",)
    del args[i:i + 2]
    # Same fail-closed check as lint/check_ruling_kind.py (copied: each lint runs standalone).
    # Compare each name exactly against its parent's listing: isdir accepts a wrong case on
    # Windows and macOS. A listed name must also be a folder.
    here = ROOT
    for part in DIRS[0].rstrip("/").split("/"):
        try:
            ok = part not in ("", ".") and part in os.listdir(here)
        except OSError:
            ok = False
        here = os.path.join(here, part)
        if not ok or not os.path.isdir(here):
            print("check_record_slugs: FAIL: records folder '%s' is not a folder under %s" % (given, ROOT))
            sys.exit(1)
unknown = [a for a in args if a.startswith("-")]
if unknown:  # read as a file name, an unknown option would skip git and check nothing
    print("check_record_slugs: FAIL: unknown option: %s" % " ".join(unknown))
    sys.exit(1)
files = args or added()
# Same normpath as lint/check_ruling_kind.py, so ./decisions/x.md is judged like decisions/x.md.
bad = [f for f in files if os.path.normpath(f).replace("\\", "/").startswith(DIRS)
       and f.endswith(".md") and len(os.path.basename(f.replace("\\", "/"))[:-3]) > MAX]
for f in bad:
    print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
sys.exit(1 if bad else 0)
