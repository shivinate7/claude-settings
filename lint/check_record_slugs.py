#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in the folders lint/layout.json marks as records. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git

The functions take a repo root, so lint/compliance_probes.py reads a child's records with them.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)

MAX = 32
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Unknown(Exception):
    """A git read failed, so the added files are not known."""


def record_dirs(root):
    """The record folders of `root` as path prefixes. Raises layout.LayoutError when the layout cannot be read."""
    return tuple(folder + "/" for folder in layout.folders(root, "record"))


def git_names(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return [name for name in r.stdout.split("\0") if name]


def added(root):
    """The files `root` adds against its origin/main. Raises Unknown when git cannot say."""
    return git_names(root, "diff", "--name-only", "-z", "--diff-filter=A", "origin/main...HEAD")


def tracked(root):
    return git_names(root, "ls-files", "-z")


def too_long(files, dirs):
    """The record files among `files` whose slug is over MAX characters. Same normpath as
    lint/check_ruling_kind.py, so ./decisions/x.md is judged like decisions/x.md."""
    return [f for f in files if os.path.normpath(f).replace("\\", "/").startswith(dirs)
            and f.endswith(".md") and len(os.path.basename(f.replace("\\", "/"))[:-3]) > MAX]


def main(args):
    unknown = [a for a in args if a.startswith("-")]
    if unknown:  # read as a file name, an unknown option would skip git and check nothing
        print("check_record_slugs: FAIL: unknown option: %s" % " ".join(unknown))
        return 1
    try:
        dirs = record_dirs(ROOT)
    except layout.LayoutError as err:  # a check that cannot read its folders is red, never green
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    try:
        files = args or added(ROOT)
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        return 1 if os.environ.get("CI") else 0  # CI exit code is a verdict: unknown is red there
    bad = too_long(files, dirs)
    for f in bad:
        print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
