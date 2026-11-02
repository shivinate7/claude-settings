#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in the folders lint/layout.json marks as records. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

Also fails when a debt file DELETED against origin/main was a feel-fix (a line starting `**Feel.**`) and had no
device check (a line starting `**Device check.**`): a fix CI passes can still feel wrong on a device.

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


def changes(root):
    """(added, deleted) files of `root` against its origin/main, from one process. Raises Unknown when git cannot say."""
    names = git_names(root, "diff", "--name-status", "-z", "origin/main...HEAD")
    added, deleted, i = [], [], 0
    while i < len(names):
        status = names[i]
        i += 1
        if status[0] in "RC":  # a rename or copy names two paths and is neither an add nor a delete
            i += 2
            continue
        if status == "A":
            added.append(names[i])
        elif status == "D":
            deleted.append(names[i])
        i += 1
    return added, deleted


def added(root):
    """The files `root` adds against its origin/main. Raises Unknown when git cannot say."""
    return changes(root)[0]


def unchecked_feel_debts(root, deleted):
    """The deleted debt files whose origin/main text has a line starting `**Feel.**` and none starting
    `**Device check.**`. Raises Unknown when git cannot show a file."""
    dirs = tuple(p + "/" for p in layout.candidates(root, "debts"))
    out = []
    for f in deleted:
        if not (f.startswith(dirs) and f.endswith(".md")):
            continue
        r = _nowindow.run(["git", "show", "origin/main:" + f], cwd=root, capture_output=True, encoding="utf-8",
                          errors="replace")
        if r.returncode:
            raise Unknown("git show failed: %s" % r.stderr.strip())
        lines = r.stdout.splitlines()
        if any(l.startswith("**Feel.**") for l in lines) and not any(l.startswith("**Device check.**") for l in lines):
            out.append(f)
    return out


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
        if args:  # files given: git is not read, so the feel-fix check does not run
            files, feel = args, []
        else:
            files, deleted = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, deleted)
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        return 1 if os.environ.get("CI") else 0  # CI exit code is a verdict: unknown is red there
    bad = too_long(files, dirs)
    for f in bad:
        print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
    for f in feel:
        print("check_record_slugs: FAIL: feel-fix debt deleted with no device check: " + f)
    return 1 if bad or feel else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
