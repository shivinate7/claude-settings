#!/usr/bin/env python3
"""Fails when a commit adds lines to a test path and carries no red-run trailer. Stdlib and git only.

    python3 lint/check_red_run.py [--base <sha>] [--root <dir>]
        # the base is env BASE_SHA when no flag is given; the repo is the current directory unless --root names one

A new test is seen red on the old code before it is trusted (`roles-each-layer-proves-once`). The test-author
records that run as a trailer on the commit that adds the test:

    Red-run: <command> -> <N> failed on <sha>       N is 1 or more, sha is 7 or more hex digits
    Red-run: none: <reason>                         a change that adds no new claim, such as a re-pointed fixture

The check reads each non-merge commit in <base>..<head> in one `git log --numstat`. <head> is HEAD for the CLI. When
<head>'s tree holds lint/check_red_run.py (this repo), it judges a commit only when that commit's parent tree holds
the file too, so a commit from before the check landed is not judged. In a repo whose <head> lacks the file, it
judges each commit in the range. A revert commit (git's `This reverts commit <sha>.`
line) is not judged: its lines were judged once already. Nor is a commit whose tree equals the tree of one of its
ancestors (any commit reachable from its parent, main's history included): it writes back a reviewed tree. That
read runs only for a commit that would otherwise be a gap, in one `git log --format=%T` capped at MAX_ANCESTORS; a
failed read, or a cap reached with no match, leaves the gap. A test path is one that `is_test_rel` in hooks/guard.py
judges (the one home), read from the install of this script, never from the repo it reads. A commit that only deletes test lines needs no trailer. A merge is not judged;
the commits it brings in are.

The guard calls `gaps` before a `git push` (`_push_hit` in hooks/guard_merge.py, rule red-run), with <head> the pushed
source ref, an `exclude` revision (the default base), so the push judges the lane's own commits only, and its own
`is_test_rel`, so this file never imports guard there. The CLI passes `guard.is_test_rel`, imported in `main`.

Limits: a pure rename of a test file reads as a delete and an add, so it needs `Red-run: none: <reason>`. A
branch that merged a newer main carries main's commits in the range, and the CLI judges each like the rest. The
guard's push check leaves out the commits the default base holds.

Exit 0: clean. Exit 1: a commit is named with its short sha, subject and test path. Exit 2: UNKNOWN, because git
could not read the range or no base was given. Unknown is never 0 here: a green exit on an unread range would hide a gap.
"""
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

SELF_REL = "lint/check_red_run.py"
RED = re.compile(r"^Red-run: \S.*? -> (\d+) failed on [0-9a-fA-F]{7,64}\s*$")
REVERT = re.compile(r"^This reverts commit [0-9a-fA-F]{7,64}\.?\s*$", re.MULTILINE)
NONE = re.compile(r"^Red-run: none: \s*\S.*$")
FIELD = "\x1f"
START = "\x01"  # opens each commit in the log output, so a commit's header and its file rows split apart
MAX_PATHS = 5
# The most ancestors whose trees a gap commit is compared with. It is large enough to reach back past the whole
# history of a repo this size, and small enough to bound the read to a few hundred KB of tree ids per gap commit.
MAX_ANCESTORS = 5000
# The printed remedy, one line each. The guard's push refusal quotes the first two. It leaves the third out,
# because it names a branch switch, which a refusal never names (rule git-remedy-never-names-target).
REMEDY = (
    "check_red_run: add `Red-run: <command> -> <N> failed on <sha>` (N 1 or more), or "
    "`Red-run: none: <reason>` for a change that adds no new claim, to the commit message.",
    "check_red_run: the last commit, not yet pushed: reword it with "
    "`git commit --amend -m <subject> -m \"Red-run: ...\"`, then `git push`.",
    "check_red_run: a flagged commit that is not last, or is already pushed: "
    "`git switch -c <new branch> <sha>^`, `git cherry-pick <sha>`, "
    "`git commit --amend -m <subject> -m \"Red-run: ...\"`, "
    "`git cherry-pick <sha>..<old head>`, `git push -u origin <new branch>`, "
    "then open a replacement PR.",
)


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


def commits(root, base, head, exclude, is_test_rel):
    """The non-merge commits of base..head, minus those `exclude` holds, oldest first, as (sha, tree, parent,
    subject, message, test paths it adds). `is_test_rel` says what a test path is (guard.is_test_rel, the one home).
    One `git log --numstat` reads the range and each commit's files. Raises Unknown when git cannot read it,
    or when a revision starts with a dash, which git would read as an option."""
    revs = [base + ".." + head] + (["^" + exclude] if exclude else [])
    if any(rev.startswith("-") or rev.startswith("^-") for rev in revs) or head.startswith("-"):
        raise Unknown("a revision starts with a dash: " + " ".join(revs))
    out = git(root, "log", "--no-merges", "--reverse", "-z", "--numstat", "--no-renames",
              "--format=" + START + "%H" + FIELD + "%T" + FIELD + "%P" + FIELD + "%B", *revs)
    found = []
    for chunk in out.split(START):
        if not chunk.strip("\0\n"):
            continue
        header, *entries = chunk.split("\0")  # a message holds no NUL: the first field is the header, the rest are file rows
        sha, tree, parents, message = header.lstrip("\n").split(FIELD, 3)
        parent = parents.split()[0] if parents.split() else None
        paths = []
        for entry in entries:
            if entry.strip("\n"):
                added, _deleted, path = entry.lstrip("\n").split("\t", 2)
                if added != "0" and is_test_rel(path):  # "-" is a binary file: it adds content
                    paths.append(path)
        found.append((sha, tree, parent, message.strip().split("\n", 1)[0], message, paths))
    return found


def check_landed(root, rev):
    return bool(git(root, "ls-tree", "--name-only", rev, "--", SELF_REL).strip())


def restores_an_ancestor_tree(root, parent, tree):
    """True when `tree` is the tree of a commit reachable from `parent`, main's history included. One
    `git log --format=%T` reads at most MAX_ANCESTORS trees. A failed read, or a cap reached with no match,
    is False: the commit stays a gap."""
    try:
        out = git(root, "log", "-n", str(MAX_ANCESTORS), "--format=%T", parent)
    except Unknown:
        return False
    return tree in out.split()


def gaps(root, base, head="HEAD", exclude="", *, is_test_rel):
    """One line per commit that adds test lines with no valid trailer. Raises Unknown when git cannot say.
    The range is base..head without the commits `exclude` holds. The rollout reads head's tree. `is_test_rel`
    is the caller's judge of a test path: the guard passes its own, the CLI passes guard.is_test_rel. A commit
    whose tree is an ancestor's is not a gap, and that read runs only for a commit that would otherwise be one."""
    lines = []
    rollout = None  # read at the first commit that could be a gap, so a range with none costs the log alone
    for sha, tree, parent, subject, message, paths in commits(root, base, head, exclude, is_test_rel):
        if parent is None or not paths or REVERT.search(message) or has_trailer(message):
            continue
        if rollout is None:
            rollout = check_landed(root, head)  # git's tree, not the disk: only a repo that tracks the check has a rollout
        if rollout and not check_landed(root, parent):
            continue
        if restores_an_ancestor_tree(root, parent, tree):
            continue
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
    import guard  # the CLI's judge of a test path: is_test_rel is the one home of what a test path is (hooks/guard.py)
    try:
        bad = gaps(root, base, is_test_rel=guard.is_test_rel)
    except Unknown as err:
        print("check_red_run: UNKNOWN, " + str(err))
        return 2
    for line in bad:
        print(line)
    if bad:
        print("\n".join(REMEDY))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
