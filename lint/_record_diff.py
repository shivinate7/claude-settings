"""What the record link checks share. Stdlib only. Read by lint/check_cite_gloss.py and lint/check_debt_decision.py.

It holds three things: which files are records, the lines a change adds to them, and the run of a check.
A record is a .md file in a record folder of lint/layout.json (decisions, debts).
The folder's README.md and the debt notes file are not records.
The record test is check_record_slugs.debt_file.
The line reader is stale_cites.added_markdown_lines, the one reader of the markdown lines a -U0 patch adds.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
sys.path.insert(0, HERE)
import check_record_slugs as slugs  # noqa: E402  Unknown, git_names, changes, debt_file
import layout  # noqa: E402  the one home of where records live (lint/layout.json)
import stale_cites  # noqa: E402  added_markdown_lines

ROOT = os.path.dirname(HERE)
Unknown = slugs.Unknown
LayoutError = layout.LayoutError


def is_record(root, kind):
    """A test of a path: is it a record file of folder kind `kind` (decisions or debts) in `root`?"""
    return slugs.debt_file(root, kind)


def slug_of(path):
    return os.path.basename(path)[:-3]


def tree_slugs(root, kind, ref="HEAD"):
    """The slug of each record file of kind `kind` at `ref`, from one git read. Raises Unknown when git cannot say."""
    keep = is_record(root, kind)
    return {slug_of(f) for f in slugs.git_names(root, "ls-tree", "-r", "-z", "--name-only", ref) if keep(f)}


def head_lines(root, path):
    """The lines of `path` at HEAD. Git numbers lines by \\n alone, so this splits at \\n alone."""
    r = _nowindow.run(["git", "show", "HEAD:" + path], cwd=root, capture_output=True, encoding="utf-8",
                      errors="replace")
    if r.returncode:
        raise Unknown("git show failed: %s" % r.stderr.strip())
    return r.stdout.split("\n")


def changes(root, base, kind):
    """(added, lines) for the record files of kind `kind` the change adds or edits against `base`.
    `added` holds the paths the change adds. A rename in from outside the folder counts as an add.
    `lines` is {path: [(number, text)]} for the lines the change adds.
    Raises Unknown when git cannot say."""
    keep = is_record(root, kind)
    adds, moved = slugs.changes(root, base)
    added = [f for f in adds if keep(f)] + [new for status, old, new in moved
                                            if status in "RC" and keep(new) and not keep(old)]
    r = _nowindow.run(["git", "-c", "core.quotepath=off", "diff", "-U0", "-M", "--no-color", "--no-ext-diff",
                       "--src-prefix=a/", "--dst-prefix=b/", base + "...HEAD", "--", *layout.candidates(root, kind)],
                      cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git diff failed: %s" % r.stderr.strip())
    lines = {path: rows for path, rows in stale_cites.added_markdown_lines(r.stdout).items() if keep(path)}
    return added, lines


def run_check(name, doc, find, argv):
    """Run one check: `find(root, base)` returns its failures as text. Print each as `<name>: FAIL: <text>`.
    A failed git read prints UNKNOWN. It exits 1 only under CI (decision ci-unknown-is-red)."""
    import argparse
    ap = argparse.ArgumentParser(description=doc.split("\n")[0])
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args(argv)
    try:
        found = find(ROOT, args.base)
    except LayoutError as err:  # a check that cannot read its folders is red, never green
        print("%s: FAIL: %s" % (name, err))
        return 1
    except Unknown as err:
        print("%s: UNKNOWN, %s" % (name, err))
        return 1 if os.environ.get("CI") else 0
    for text in found:
        print("%s: FAIL: %s" % (name, text))
    return 1 if found else 0
