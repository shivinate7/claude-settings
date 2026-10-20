#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in decisions/ and debts/. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git
"""
import os
import subprocess
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

MAX = 32
DIRS = ("decisions/", "debts/")  # one line: hooks/guard.py reads it
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def added():
    cmd = ["git", "diff", "--name-only", "--diff-filter=A", "origin/main...HEAD"]
    r = _nowindow.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print("check_record_slugs: UNKNOWN, git diff failed: " + r.stderr.strip())
        sys.exit(1 if os.environ.get("CI") else 0)  # CI exit code is a verdict: unknown is red there
    return r.stdout.split()


args = sys.argv[1:]
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
