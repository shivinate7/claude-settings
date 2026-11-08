#!/usr/bin/env python3
"""Fails when a commit adds lines to a test path and carries no red-run trailer. Stdlib and git only.

    python3 lint/check_red_run.py [--base <sha>] [--root <dir>]
        # the base is env BASE_SHA when no flag is given; the repo is the current directory unless --root names one

A new test is seen red on the old code before it is trusted (`roles-each-layer-proves-once`). The test-author
records that run as a trailer on the commit that adds the test:

    Red-run: <command> -> <N> failed on <sha>       N is 1 or more, sha is 7 or more hex digits
    Red-run: mutant: <mutation> -> <N> failed on <sha>
                                                    for a claim only a mutation shows red: <mutation> is non-empty, and
                                                    sha has the same shape as the failed form's
    Red-run: none: <reason>                         a change that adds no new claim, such as a re-pointed fixture

A message passes only when it has at least one Red-run line and every Red-run line is valid: one malformed line fails the
commit, even beside a valid one. A line counts as a Red-run line when its key reads `red-run` followed by optional spaces and a colon at line
start, in any case (`Red-Run:`, `red-run:`, `Red-run :`); a key that is not exactly `Red-run:` is malformed. Prose that
mentions red-run mid-line is not judged. The failed form refuses a command whose first word starts with `mutant` or
`mutation` (`mutants:`, `mutation:`, `mutant(A)`, `mutant-A`, `mutantA:`, a no-colon `mutant A (...)`), or is exactly
`mutate`, `none` or `non`, so a typo is not read as a failed form. Two main commits (408340997, 1762ec79f) wrote the
no-colon mutant form.

A line whose keyword reads `mutant` is judged by the mutant form alone, never by the command form. The mutant
pattern takes `Red-run:`, then any whitespace or none (a tab, or no space: `Red-run:mutant:`), `mutant` in any case,
any whitespace before the colon, the colon, then one or more spaces. The failed and none forms need a literal space after
`Red-run:`. The check reads the sha's shape only, as it does for the
failed form, and never that the sha exists or that the mutation was made: those parts are claimed. A rebase or a
cherry-pick rewrites the commit a sha names, so a reach check raised false alarms.

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
MUTANT_KEY = re.compile(r"^Red-run:\s*(?i:mutant)\s*:")  # routes a line to the mutant form
MUTANT = re.compile(r"^Red-run:\s*(?i:mutant)\s*: \s*\S.*? -> (\d+) failed on [0-9a-fA-F]{7,64}\s*$")
REVERT = re.compile(r"^This reverts commit [0-9a-fA-F]{7,64}\.?\s*$", re.MULTILINE)
NONE = re.compile(r"^Red-run: none: \s*\S.*$")
RED_KEY = re.compile(r"^red-run\s*:", re.IGNORECASE)  # a Red-run line in any case; only `Red-run:` exactly can be valid
# First words, besides the mutant-like ones (`mutant_like`), a failed-form command may not be. Each is a typo of the none
# keyword. The failed pattern would accept it as a command that never ran. No real command is one of these words.
REFUSED_NONE_WORDS = frozenset(("none", "non"))
FIELD = "\x1f"
MAX_PATHS = 5


class Unknown(Exception):
    """A git read failed, so the range is not known."""


def git(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def command_of(line):
    """The first word of a failed-form line's command, lower case, with trailing colons dropped."""
    words = line[len("Red-run:"):].split()
    return words[0].rstrip(":").lower() if words else ""


def valid_line(line):
    """True when one Red-run line is a valid mutant, failed or none form. Pure."""
    line = line.rstrip()
    if MUTANT_KEY.match(line):
        mutant = MUTANT.match(line)
        return bool(mutant) and int(mutant.group(1)) >= 1
    if NONE.match(line):
        return True
    red = RED.match(line)
    return bool(red) and int(red.group(1)) >= 1 and not mutant_like(line) and command_of(line) not in REFUSED_NONE_WORDS


def mutant_like(line):
    """True when the failed-form command starts like the mutant keyword: it starts with `mutant` or `mutation`, or is
    `mutate`. The one home of the mutant-like refusal and of the hint that names the mutant form. Pure."""
    word = command_of(line)
    return word.startswith(("mutant", "mutation")) or word == "mutate"


def has_valid_trailer(message):
    """True when the message has a Red-run line and every Red-run line is valid. Pure: it reads no repo."""
    lines = [line for line in message.splitlines() if RED_KEY.match(line)]
    return bool(lines) and all(valid_line(line) for line in lines)


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
        if not paths:
            continue
        if not has_valid_trailer(message):
            hint = ""
            if any(mutant_like(l) and not valid_line(l) for l in message.splitlines() if RED_KEY.match(l)):
                hint = "; a mutant line reads `Red-run: mutant: <mutation> -> <N> failed on <sha>`"
            shown = ", ".join(paths[:MAX_PATHS]) + (" and %d more" % (len(paths) - MAX_PATHS) if len(paths) > MAX_PATHS else "")
            lines.append("check_red_run: FAIL: %s %s: adds lines to %s with no valid Red-run trailer%s" % (sha[:7], subject, shown, hint))
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
        print("check_red_run: add `Red-run: <command> -> <N> failed on <sha>` (N 1 or more), "
              "`Red-run: mutant: <mutation> -> <N> failed on <sha>` (a claim only a mutation shows red), or "
              "`Red-run: none: <reason>` for a change that adds no new claim, to the commit message.")
        print("check_red_run: the last commit, not yet pushed: reword it with "
              "`git commit --amend -m <subject> -m \"Red-run: ...\"`, then `git push`.")
        print("check_red_run: a flagged commit that is not last, or is already pushed: "
              "`git switch -c <new branch> <sha>^`, `git cherry-pick <sha>`, "
              "`git commit --amend -m <subject> -m \"Red-run: ...\"`, "
              "`git cherry-pick <sha>..<old head>`, `git push -u origin <new branch>`, "
              "then open a replacement PR.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
