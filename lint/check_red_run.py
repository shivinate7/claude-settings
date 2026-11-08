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
commit, even beside a valid one. A line counts as a Red-run line, at line start and in any case, in two ways. First, a key that reads
`red`, then any run of spaces, underscores or hyphens (none too), then `run` or `runs`, then optional spaces and a colon
(`Red-Run:`, `Red-run :`, `Red-runs:`, `Red run:`, `Red_run:`, `Redrun:`). Second, the same key with no colon, only when the
line also ends in `-> <N> failed on <sha>` (`Red-run python3 x -> 1 failed on <sha>`). A bare line-start "Red run" with no colon
and no such tail is prose: eleven main messages carry valid trailers and begin a line that way. A key that is not exactly
`Red-run:` is malformed. Prose that mentions red-run mid-line, and words such as `Redress:` or `Reduce:`, are not judged. The failed form judges the label word of its command in two layers, so a
typo is not read as a failed form. `label_word(line)` is the one normaliser: it reads the text after `Red-run:`, takes the
first word, and strips from both ends to a fixed point, so the order of nesting never matters: list markers at the start (`-`, `+`,
a `1)` or `1.` word; `>` strips at both ends, with the brackets), emphasis (`*`, `~`, `_`), backticks, quotes straight and curly, brackets, `#`, and a trailing `,` or `:`.
A leading underscore that belongs to a name stays (`_build/run_tests.sh`, `__main__.py`, `_mutant.sh`): it goes only when
the word closes with an underscore too, or its core is bare letters once wrappers and list markers go (`_mutant`,
`_-mutant`). It returns three fields of that one stripped word: the word in lower case, whether a colon ended it, and
upper_env, True when the word before folding is an upper-case `NAME=` assignment (`- MUTATE_ONLY=x` reads True).
`mutant_like` and `refused_word` read those three fields and nothing else. This reads the label region of the line, not
every word: a scan of the whole line flips 15 to 26 accepted main commits, such as one that wrote
`(mutant: code_check.py:266 returns [])` after its command. A mutant mention after a real first word still passes. First,
it refuses a label word that starts with `mutant` or `mutation` (`mutants:`, `mutant(A)`, `mutant-A`, `mutant=x`, a
no-colon `mutant A (...)`, `(mutant A)`, `_**mutant**_`), or is exactly `none` or `non` (`(none)`, `_(none)_`). Second,
unless upper_env is True (`MUTATE_ONLY=x`, or `MUTATE_ONLY="worktree-home: ..."` as a main commit wrote it), it refuses a
label word that starts with `mutat` or `mutan` (`mutate`, `mutate=x`, `mutan:`), or whose leading letters are one edit or
one adjacent swap from `mutant` or `mutation` (`mutnat`, `mtuant`, `mutnt`, `mutaiton`). Any `NAME=` word, lower case
too, stays exempt from the colon refusal: a label word that ended in a colon (`runner:`, `nonee:`) is refused otherwise.
The valid `mutant:` and `none:` forms are routed to their own patterns before the failed form, so neither layer reads
them. Real commands pass (`mutmut run`, `./mutation_probe.sh`, `_build/run_tests.sh`, `NONE=1 python3 ...`,
`env X=1 python3 ...`, `nonstop ...`, `(cd lint && python3 ...)`). Three main commits wrote the no-colon mutant form;
decision `red-run-trailer-on-test-commits` names them. Limits: a typo two edits away (`mtunat`), a mutant label after an
env or assignment prefix, a mutant mention after a real first word, `./mutant`, a none typo beyond `none` and `non`, and
prose first words pass.

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
# A Red-run line is a near-miss key followed by a colon (`Red-runs:`, `Red run:`, `Red_run:`, `Redrun:`, any case, spaces
# before the colon), or a key with no colon that also carries the failed form's tail. Only `Red-run:` exactly can be valid.
# A bare line-start "Red run" with no colon is not a key: eleven main messages carry valid trailers and begin a line so.
RED_KEY_WORD = re.compile(r"^red[\s_-]*runs?", re.IGNORECASE)
RED_KEY = re.compile(RED_KEY_WORD.pattern + r"\s*:", re.IGNORECASE)
RED_KEY_NO_COLON = re.compile(RED_KEY_WORD.pattern + r"\b.* -> \d+ failed on [0-9a-f]{7,64}\s*$", re.IGNORECASE)
# First words, besides the mutant-like ones (`mutant_like`), a failed-form command may not be. Each is a typo of the none
# keyword. The failed pattern would accept it as a command that never ran. No real command is one of these words.
REFUSED_NONE_WORDS = frozenset(("none", "non"))
# An upper-case environment assignment as the label word (`MUTATE_ONLY=x`, `MUTATE_ONLY="a: b"`), read by `label_word`
# on the stripped word before folding. It is a real command's prefix, so the second layer (`mutant_like`) skips it.
UPPER_ENV_WORD = re.compile(r"^[A-Z_][A-Z0-9_]*=")
# Any assignment as the label word. It is exempt from the colon refusal only (`lint_mode=on:`).
ENV_WORD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# What `label_word` strips from a word: brackets, quotes (straight and curly), emphasis (`*`, `~`), backticks and `#`, from
# both ends. A list marker (`-`, `+`) goes at the start only; `,`, `:` and `_` go at the end only. A leading underscore is
# kept when it belongs to a name (`_build/run.sh`, `__main__.py`, `_mutant.sh`): see `label_word`.
WRAPPERS = "()[]{}<>\"'`*#~\u201c\u201d\u2018\u2019"
LIST_MARKERS = "-+"
LIST_NUMBER = re.compile(r"^\d+[.)]$")  # `1)` and `1.` list markers, a word of their own
MUTANT_WORDS = ("mutant", "mutation")
FIELD = "\x1f"
MAX_PATHS = 5


class Unknown(Exception):
    """A git read failed, so the range is not known."""


def git(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def label_word(line):
    """The red-run label of a whole `Red-run:` line, the one normaliser the word rule reads: (word in lower case,
    ended_in_colon, upper_env). The word is the first word after `Red-run:` once wrappers are gone. Each word is stripped
    to a fixed point from both ends, so the order of nested wrappers never matters (`_**mutant**_`, `**_mutant_**`,
    `_(none)_`). A leading underscore is stripped only when the word closes with an underscore too, or its core is bare
    letters once wrappers and list markers go (`_mutant`, `_-mutant`); a name such as `_build/run.sh` keeps it. A word
    that strips to nothing (`-`, `>`, `1)`) is skipped, and a colon it held (`:`, `-:`) goes on to the next word, so
    the label still ends in a colon. upper_env is True when the same stripped word, before it is
    folded to lower case, is an upper-case `NAME=` assignment (`- MUTATE_ONLY=x` reads True). The key is cut by its
    own match, so a near-miss key of any width (`Red-run :`, `Red-runs:`, `Red run`) does not shift the word. No key or
    no word: ("", False, False). Pure."""
    key = RED_KEY.match(line) or RED_KEY_WORD.match(line)
    if not key:
        return "", False, False
    skipped_colon = False
    for token in line[key.end():].split():
        if LIST_NUMBER.match(token):
            continue
        colon = False
        while True:
            before = token
            lead = token.lstrip(WRAPPERS + LIST_MARKERS)
            word = lead.rstrip(WRAPPERS + ",:_")
            colon = colon or ":" in lead[len(word):]
            if lead.startswith("_") and ("_" in lead[len(word):]
                                         or re.fullmatch(r"[A-Za-z]*", word.strip("_" + WRAPPERS + LIST_MARKERS))):
                word = word.lstrip("_")
            token = word
            if token == before:
                break
        if token:
            return token.casefold(), colon or skipped_colon, bool(UPPER_ENV_WORD.match(token))
        skipped_colon = skipped_colon or colon
    return "", False, False


def within_one_edit(a, b):
    """True when a and b differ by one insert, delete, substitution or adjacent swap. Pure."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def valid_line(line):
    """True when one Red-run line is a valid mutant, failed or none form. Pure."""
    line = line.rstrip()
    if MUTANT_KEY.match(line):
        mutant = MUTANT.match(line)
        return bool(mutant) and int(mutant.group(1)) >= 1
    if NONE.match(line):
        return True
    red = RED.match(line)
    return bool(red) and int(red.group(1)) >= 1 and not mutant_like(line) and not refused_word(line)


def mutant_like(line):
    """True when the failed-form label word reads like the mutant keyword. Layer 1: its label word starts with
    `mutant` or `mutation` (an assignment too, so `mutant=x` stays refused). Layer 2, unless the label word is an
    upper-case environment assignment (upper_env, `MUTATE_ONLY=x`): it starts with `mutat` or `mutan`, or its leading letters are
    one edit or adjacent swap from `mutant` or `mutation`. It reads only the three fields of `label_word`. The one home
    of the mutant-like refusal and of the hint that names the mutant form. Pure."""
    word, _, upper_env = label_word(line)
    if word.startswith(MUTANT_WORDS):
        return True
    if upper_env:
        return False
    if word.startswith(("mutat", "mutan")):
        return True
    letters = re.match(r"[a-z]+", word)
    return bool(letters) and any(within_one_edit(letters.group(), m) for m in MUTANT_WORDS)


def refused_word(line):
    """True when the failed-form label word is a none typo (`none`, `non`), or, unless it is an environment assignment,
    ends in a colon: a keyword typo such as `runner:` or `nonee:`. The valid `mutant:` and `none:` lines are routed to
    their own forms before this is read. Pure."""
    word, colon, _ = label_word(line)
    if word in REFUSED_NONE_WORDS:
        return True
    return colon and not ENV_WORD.match(word)


def red_lines(message):
    """The Red-run lines of a message: the one home of what counts as one, read by the validity check and the hint. Pure."""
    return [line for line in message.splitlines() if RED_KEY.match(line) or RED_KEY_NO_COLON.match(line)]


def has_valid_trailer(message):
    """True when the message has a Red-run line and every Red-run line is valid. Pure: it reads no repo."""
    lines = red_lines(message)
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
            if any(mutant_like(l) and not valid_line(l) for l in red_lines(message)):
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
