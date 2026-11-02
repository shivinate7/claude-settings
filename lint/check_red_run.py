#!/usr/bin/env python3
"""Fails when a commit adds lines to a test path and carries no red-run trailer. Stdlib and git only.

    python3 lint/check_red_run.py [--base <sha>] [--root <dir>]
        # the base is env BASE_SHA when no flag is given; the repo is the current directory unless --root names one

A new test is seen red on the old code before it is trusted (`roles-each-layer-proves-once`). The test-author
records that run as a trailer on the commit that adds the test:

    Red-run: <command> -> <N> failed on <sha>       N is 1 or more, sha is 7 or more hex digits
    Red-run: none: <reason>                         a change that adds no new claim, such as a re-pointed fixture

The check reads each non-merge commit in <base>..HEAD. When HEAD's tree holds lint/check_red_run.py (this repo),
it judges a commit only when that commit's parent tree holds the file too, so a commit from before the check landed
is not judged. In a repo whose HEAD lacks the file, it judges each commit in the range. A revert commit (git's `This reverts commit <sha>.`
line) is not judged: its lines were judged once already. A test path is one that `is_test_rel` in hooks/guard.py
judges (the one home), read from the install of this script, never from the repo it reads. A commit that only deletes test lines needs no trailer. A merge is not judged;
the commits it brings in are.

Limits: a pure rename of a test file reads as a delete and an add, so it needs `Red-run: none: <reason>`. A
branch that merged a newer main carries main's commits in the range, and each is judged like the rest.

Exit 0: clean. Exit 1: a commit is named with its short sha, subject and test path. Exit 2: UNKNOWN, because git
could not read the range or no base was given. Unknown is never 0 here: a green exit on an unread range would hide a gap.
"""
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import guard  # noqa: E402  is_test_rel is the one home of what a test path is (hooks/guard.py)

SELF_REL = "lint/check_red_run.py"
RED = re.compile(r"^Red-run: \S.*? -> (\d+) failed on [0-9a-fA-F]{7,64}\s*$")
REVERT = re.compile(r"^This reverts commit [0-9a-fA-F]{7,64}\.?\s*$", re.MULTILINE)
NONE = re.compile(r"^Red-run: none: \s*\S.*$")
FIELD = "\x1f"
MAX_PATHS = 5


class Unknown(Exception):
    """A git read failed, so the range is not known."""


def git(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def has_trailer(message):
    """True when a line of the message is a valid Red-run line: a red run of 1 or more failures, or none with a reason."""
    for line in message.splitlines():
        red = RED.match(line)
        if (red and int(red.group(1)) >= 1) or NONE.match(line.rstrip()):
            return True
    return False


def commits(root, base):
    """The non-merge commits of base..HEAD, oldest first, as (sha, parent, subject, message)."""
    git(root, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    out = git(root, "log", "--no-merges", "--reverse", "-z", "--format=%H" + FIELD + "%P" + FIELD + "%B", base + "..HEAD")
    found = []
    for chunk in out.split("\0"):
        if not chunk.strip():
            continue
        sha, parents, message = chunk.lstrip("\n").split(FIELD, 2)
        parent = parents.split()[0] if parents.split() else None
        found.append((sha, parent, message.strip().split("\n", 1)[0], message))
    return found


def added_test_paths(root, parent, sha):
    out = git(root, "diff", "--numstat", "-z", "--no-renames", parent, sha)
    paths = []
    for entry in out.split("\0"):
        if not entry:
            continue
        added, _deleted, path = entry.split("\t", 2)
        if added != "0" and guard.is_test_rel(path):  # "-" is a binary file: it adds content
            paths.append(path)
    return paths


def check_landed(root, parent):
    return bool(git(root, "ls-tree", "--name-only", parent, "--", SELF_REL).strip())


def gaps(root, base):
    """One line per commit that adds test lines with no valid trailer. Raises Unknown when git cannot say."""
    lines = []
    rollout = check_landed(root, "HEAD")  # git's tree, not the disk: only a repo that tracks the check has a rollout
    for sha, parent, subject, message in commits(root, base):
        if parent is None or REVERT.search(message) or (rollout and not check_landed(root, parent)):
            continue
        paths = added_test_paths(root, parent, sha)
        if paths and not has_trailer(message):
            shown = ", ".join(paths[:MAX_PATHS]) + (" and %d more" % (len(paths) - MAX_PATHS) if len(paths) > MAX_PATHS else "")
            lines.append("check_red_run: FAIL: %s %s: adds lines to %s with no valid Red-run trailer" % (sha[:7], subject, shown))
    return lines


def main(args):
    base, root = os.environ.get("BASE_SHA", ""), os.getcwd()
    rest = list(args)
    while rest:
        flag = rest.pop(0)
        if flag not in ("--base", "--root") or not rest:
            print("check_red_run: FAIL: usage: check_red_run.py [--base <sha>] [--root <dir>]")
            return 1
        if flag == "--base":
            base = rest.pop(0)
        else:
            root = rest.pop(0)
    if not base:
        print("check_red_run: UNKNOWN, no base: pass --base <sha> or set BASE_SHA")
        return 2
    try:
        bad = gaps(root, base)
    except Unknown as err:
        print("check_red_run: UNKNOWN, " + str(err))
        return 2
    for line in bad:
        print(line)
    if bad:
        print("check_red_run: add `Red-run: <command> -> <N> failed on <sha>` (N 1 or more), or "
              "`Red-run: none: <reason>` for a change that adds no new claim, to the commit message.")
        print("check_red_run: a commit already pushed: reword it to add the trailer "
              "(`git commit --amend` for the last commit, or `git rebase -i` for an older one), "
              "then push with `git push --force-with-lease`.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
