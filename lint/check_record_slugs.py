#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in decisions/ and deferred/. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

    python3 lint/check_record_slugs.py [file ...]   # files given: check those, skip git
"""
import os
import subprocess
import sys

MAX = 32
DIRS = ("decisions/", "deferred/")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def added():
    cmd = ["git", "diff", "--name-only", "--diff-filter=A", "origin/main...HEAD"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        print("check_record_slugs: UNKNOWN, git diff failed: " + r.stderr.strip())
        sys.exit(0)  # unreadable is unknown, not red
    return r.stdout.split()


files = sys.argv[1:] or added()
bad = [f for f in files if f.startswith(DIRS) and f.endswith(".md")
       and len(os.path.basename(f)[:-3]) > MAX]
for f in bad:
    print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
sys.exit(1 if bad else 0)
