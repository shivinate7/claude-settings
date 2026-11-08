#!/usr/bin/env python3
"""Fails when a builder's report names a file that is not in its pushed branch head's diff. Stdlib and git only.

    python3 lint/check_report_in_head.py --branch <name> [--base <ref>] [--root <dir>] [--report <path>|-]
        # base: origin/main when no flag is given; root: the current directory; report: stdin when no flag or `-`

A builder's report lists the files it changed on one `Files:` line (`agents/builder.md`). A hook can refuse a
builder's edit and the builder still report it. The reviewer then reads a change that is not there. This check reads the pushed head, never the local tree: it fetches refs/heads/<branch> from origin and
diffs `--name-only --no-renames` from the merge base of <base> and that head to the head. A renamed file shows under
both names.

The report line: one line that starts, after any blockquote, bullet or bold marks, with `Files:`. It holds
comma-separated repo-relative paths, each with optional backticks, a leading `./`, and an optional `:<range>`
(`lint/a.py:10-20`). Other lines are not read.

Exit 0: every listed path is in the diff. Exit 1: each missing path is named. Exit 2: UNKNOWN, because the branch is
not on origin, git failed, the report has no `Files:` line, more than one, an empty one, or an absolute path entry.
Unknown is never 0 here: a green exit on an unread head would hide the gap.

Scope: reported but not in the diff. A changed file the report leaves out is not judged.

Cost: 3 git calls per run (fetch of one branch, rev-parse of the fetched head, one diff). It fetches objects into
the repo's object store and writes no other file. The lane runs it once per builder report, before it spawns the
reviewer (decision `builder-report-in-head`).
"""
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

TAG = "check_report_in_head"
FILES_LINE = re.compile(r"^[\s>*\-]*Files\**\s*:\**\s*(.*)$")
RANGE = re.compile(r":\d+(?:-\d+)?$")
ABSOLUTE = re.compile(r"^(?:/|\\|[A-Za-z]:[\\/])")
USAGE = "usage: check_report_in_head.py --branch <name> [--base <ref>] [--root <dir>] [--report <path>|-]"


class Unknown(Exception):
    """A read failed or the report cannot be read, so the verdict is not known."""


def git(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def reported_paths(report):
    """The repo-relative paths of the report's one Files line, in order, without repeats."""
    lines = [m.group(1) for m in map(FILES_LINE.match, report.splitlines()) if m]
    if not lines:
        raise Unknown("the report has no Files line")
    if len(lines) > 1:
        raise Unknown("the report has %d Files lines, want one" % len(lines))
    paths = []
    for entry in lines[0].split(","):
        entry = entry.strip().strip("`").strip()
        if not entry:
            continue
        if ABSOLUTE.match(entry):
            raise Unknown("the Files line holds an absolute path: " + entry)
        entry = RANGE.sub("", entry)
        while entry.startswith("./"):
            entry = entry[2:]
        if entry and entry not in paths:
            paths.append(entry)
    if not paths:
        raise Unknown("the Files line is empty")
    return paths


def pushed_diff(root, branch, base):
    """(head sha, set of paths changed from merge-base(base, head) to head), read from origin's refs/heads/<branch>."""
    try:
        git(root, "fetch", "--quiet", "--no-tags", "origin", "refs/heads/" + branch)
    except Unknown as err:
        raise Unknown("branch %s is not readable on origin: %s" % (branch, err))
    head = git(root, "rev-parse", "--verify", "FETCH_HEAD^{commit}").strip()
    out = git(root, "diff", "--name-only", "--no-renames", "-z", "%s...%s" % (base, head))
    return head, set(p for p in out.split("\0") if p)


def main(args):
    branch, base, root, report_path = "", "origin/main", os.getcwd(), "-"
    rest = list(args)
    while rest:
        flag = rest.pop(0)
        if flag not in ("--branch", "--base", "--root", "--report") or not rest:
            print("%s: UNKNOWN, %s" % (TAG, USAGE))
            return 2
        value = rest.pop(0)
        if flag == "--branch":
            branch = value
        elif flag == "--base":
            base = value
        elif flag == "--root":
            root = value
        else:
            report_path = value
    if not branch:
        print("%s: UNKNOWN, no branch: %s" % (TAG, USAGE))
        return 2
    try:
        if report_path == "-":
            report = sys.stdin.read()
        else:
            with open(report_path, encoding="utf-8", errors="replace") as f:
                report = f.read()
        paths = reported_paths(report)
        head, changed = pushed_diff(root, branch, base)
    except (Unknown, OSError) as err:
        print("%s: UNKNOWN, %s" % (TAG, err))
        return 2
    missing = [p for p in paths if p not in changed]
    for path in missing:
        print("%s: FAIL: %s is reported but not in the diff of %s at %s" % (TAG, path, branch, head[:9]))
    if missing:
        print("%s: the builder reported an edit the pushed head lacks. Send it back to apply and push." % TAG)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
