#!/usr/bin/env python3
"""Fails when a commit adds lines to a test path and carries no red-run trailer, or cites a ruling with no home and
no time. Stdlib and git only (plus lint/report_guard.py for the time forms).

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

A ruling cite (`outcomes-grant-covers-named-act`): a commit message that makes a ruling claim names the ruling's home and
its time. A claim is one of the phrases in RULING_CITE_RE: the owner, Shivam or the arbiter with `ruling`, `'s ruling`
or `ruled` (also `owner-ruled`, `ruled by the owner`), or `per ruling`, `per the ruling`. It sits in the subject, the
body or a trailer, outside backticks and fences (a fence is cut out whole, blank lines included). A negation
(`no owner ruling`) is not a claim. The claim's own paragraph names a home and a time, or a `Ruling:` line in the
trailer block does, both on that line; that line covers a claim in the subject or the trailer block, never in a body
paragraph. A home is `item N x`, `item N, pick x`, `item <slug>`, `step:<slug>`, `rule:<id>`, or `decision <folder>/<slug>.md`
(or `decision <slug>` when that file is in the commit's tree), the folder read from lint/layout.py. A time is a stamp in
the forms of STAMP_FULL_RE and STAMP_CLOCK_RE (lint/report_guard.py, the one home): `YYYY-MM-DD HH:MM CST` or
`HH:MM CST`. The FAIL line says which part is missing. It judges each non-merge, non-revert commit, whatever paths it
touches. Rollout: it judges a commit only when its author date is at or after the author date of the first commit
reachable from HEAD that adds RULING_CITE_RE to this file (one `git log -S` read per run), so a commit written before
the rule landed is not judged, a cherry-pick of it included. The Red-run rule and its own gate are unchanged.

Limits: a pure rename of a test file reads as a delete and an add, so it needs `Red-run: none: <reason>`. A
branch that merged a newer main carries main's commits in the range, and each is judged like the rest.

Exit 0: clean. Exit 1: a commit is named with its short sha and subject, and for a test gap its test path. Exit 2: UNKNOWN, because git
could not read the range or no base was given. Unknown is never 0 here: a green exit on an unread range would hide a gap.
"""
import functools
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import guard  # noqa: E402  is_test_rel is the one home of what a test path is (hooks/guard.py)
import layout  # noqa: E402  where the decisions folder is (lint/layout.py)
from report_guard import STAMP_CLOCK_RE, STAMP_FULL_RE  # noqa: E402  the time forms (lint/report_guard.py)

SELF_REL = "lint/check_red_run.py"
RED = re.compile(r"^Red-run: \S.*? -> (\d+) failed on [0-9a-fA-F]{7,64}\s*$")
REVERT = re.compile(r"^This reverts commit [0-9a-fA-F]{7,64}\.?\s*$", re.MULTILINE)
NONE = re.compile(r"^Red-run: none: \s*\S.*$")
# A ruling claim: the owner, Shivam or the arbiter as the one who ruled. The lookahead keeps a name such as `ruling-kind` out.
_ACTOR = r"(?:the\s+)?(?:owner|shivam|arbiter)"
RULING_CITE_RE = re.compile(
    r"\b(?:%s(?:['’]s)?[\s-]+rulings?|%s[\s-]+ruled|ruled\s+by\s+%s|per\s+(?:the\s+)?rulings?)(?![\w-])"
    % (_ACTOR, _ACTOR, _ACTOR), re.I)
NEGATED_BEFORE = re.compile(r"\b(?:no|not|never|without|nor)\s+(?:(?:an?|the|any)\s+)?$", re.I)  # "no owner ruling" claims nothing
RULING_TRAILER = re.compile(r"^Ruling:[ \t]*(\S.*)$", re.MULTILINE)
RULING_MARKER = "RULING_CITE_RE"  # the string whose first commit starts the rollout
ITEM_HOME_RE = re.compile(r"\bitem\s+(?:\d+(?:\s*[a-z]\b|,\s*pick\s+[a-z]\b)|[a-z][a-z0-9]*(?:-[a-z0-9]+)+)", re.I)
REF_HOME_RE = re.compile(r"\b(?:step|rule):[a-z0-9][\w-]*", re.I)
DECISION_HOME_RE = re.compile(r"\bdecision\s+`?([\w./-]+)", re.I)
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
CODE_SPAN_RE = re.compile(r"`[^`]*`")
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


@functools.lru_cache(maxsize=None)
def decision_folders(root):
    """The folders a decision record may sit in, from lint/layout.py (the one home of where records live)."""
    try:
        return tuple(layout.candidates(root, "decisions"))
    except (layout.LayoutError, KeyError, OSError) as err:
        raise Unknown("the decisions folder is unreadable: %s" % err)


def decision_named(root, sha):
    """A function that says whether a token after the word decision names a file under the decisions folder: the path
    `<folder>/<slug>.md`, or a slug whose file `<folder>/<slug>.md` exists in the commit's tree."""
    def named(token):
        token = token.rstrip(".,;:)")
        folders = decision_folders(root)
        for folder in folders:
            if token.startswith(folder + "/"):
                return re.fullmatch(r"[\w-]+\.md", token[len(folder) + 1:]) is not None
        slug = token[:-3] if token.endswith(".md") else token
        if not re.fullmatch(r"[\w-]+", slug):
            return False
        return any(_nowindow.run(["git", "cat-file", "-e", "%s:%s/%s.md" % (sha, folder, slug)], cwd=root,
                                 capture_output=True).returncode == 0 for folder in folders)
    return named


def has_home(text, named):
    """True when the text names a home: `item N x`, `item N, pick x`, `item <slug>`, `step:<slug>`, `rule:<id>`, or a
    decision file (`named`)."""
    return bool(ITEM_HOME_RE.search(text) or REF_HOME_RE.search(text)
                or any(named(m.group(1)) for m in DECISION_HOME_RE.finditer(text)))


def has_time(text):
    return bool(STAMP_FULL_RE.search(text) or STAMP_CLOCK_RE.search(text))


def has_claim(paragraph):
    """True when a paragraph makes a ruling claim outside backticks and not behind a negation."""
    plain = CODE_SPAN_RE.sub(" ", paragraph)
    return any(not NEGATED_BEFORE.search(plain[:m.start()]) for m in RULING_CITE_RE.finditer(plain))


def missing_cite(message, named):
    """None when each ruling claim is cited, else the missing part: "no home", "no time" or "no home and no time", for
    the first claim paragraph that lacks one. A paragraph cites in its own text. A `Ruling:` line in the trailer
    block (the last paragraph), with a home and a time on that line, also covers a claim in the subject or the
    trailer block, never a claim in a body paragraph. Fenced blocks are cut out whole, blank lines in them included;
    a code span never crosses a paragraph, because the message is split into paragraphs first."""
    paragraphs = re.split(r"\n\s*\n", FENCE_RE.sub(" ", message))
    last = len(paragraphs) - 1
    covered = any(has_home(m.group(1), named) and has_time(m.group(1))
                  for m in RULING_TRAILER.finditer(paragraphs[last]))
    for index, paragraph in enumerate(paragraphs):
        if not has_claim(paragraph):
            continue
        home, time = has_home(paragraph, named), has_time(paragraph)
        if (home and time) or (covered and index in (0, last)):
            continue
        return "no home and no time" if not (home or time) else ("no time" if home else "no home")
    return None


def ruling_rollout_time(root):
    """The author date (epoch seconds) of the first commit reachable from HEAD that adds RULING_CITE_RE to this file,
    or None when no commit does. One git read per run. A cherry-pick keeps its author date, so a rebuilt batch does
    not judge a commit written before the rule landed."""
    out = git(root, "log", "-S" + RULING_MARKER, "--reverse", "--format=%at", "HEAD", "--", SELF_REL).split()
    return int(out[0]) if out else None


def commits(root, base):
    """The non-merge commits of base..HEAD, oldest first, as (sha, parent, subject, message, author date in seconds)."""
    git(root, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    out = git(root, "log", "--no-merges", "--reverse", "-z", "--format=%H" + FIELD + "%P" + FIELD + "%at" + FIELD + "%B",
              base + "..HEAD")
    found = []
    for chunk in out.split("\0"):
        if not chunk.strip():
            continue
        sha, parents, authored, message = chunk.lstrip("\n").split(FIELD, 3)
        parent = parents.split()[0] if parents.split() else None
        found.append((sha, parent, message.strip().split("\n", 1)[0], message, int(authored)))
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
    """(kind, line) per failing commit: kind is "red" for a test gap, "ruling" for an uncited ruling claim. A commit can
    fail both. Raises Unknown when git cannot say."""
    found = []
    rollout = check_landed(root, "HEAD")  # git's tree, not the disk: only a repo that tracks the check has a rollout
    since = ruling_rollout_time(root)
    for sha, parent, subject, message, authored in commits(root, base):
        if parent is None or REVERT.search(message):
            continue
        if not (rollout and not check_landed(root, parent)):
            paths = added_test_paths(root, parent, sha)
            if paths and not has_trailer(message):
                shown = ", ".join(paths[:MAX_PATHS]) + (" and %d more" % (len(paths) - MAX_PATHS) if len(paths) > MAX_PATHS else "")
                found.append(("red", "check_red_run: FAIL: %s %s: adds lines to %s with no valid Red-run trailer" % (sha[:7], subject, shown)))
        if since is not None and authored >= since:
            lacks = missing_cite(message, decision_named(root, sha))
            if lacks:
                found.append(("ruling", "check_red_run: FAIL: %s %s: cites a ruling with %s in the claim's paragraph" % (sha[:7], subject, lacks)))
    return found


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
    for _kind, line in bad:
        print(line)
    kinds = {kind for kind, _line in bad}
    if "red" in kinds:
        print("check_red_run: add `Red-run: <command> -> <N> failed on <sha>` (N 1 or more), or "
              "`Red-run: none: <reason>` for a change that adds no new claim, to the commit message.")
    if "ruling" in kinds:
        print("check_red_run: in the claim's paragraph, or in a `Ruling:` trailer line, name the ruling's home "
              "(`item N x`, `step:<slug>`, `decision <slug>` or `rule:<id>`) and its time "
              "(`YYYY-MM-DD HH:MM CST` or `HH:MM CST`). A phrase that only names a thing goes in backticks.")
    if bad:
        trailer = "Red-run: ..." if "red" in kinds else "Ruling: ..."
        print("check_red_run: the last commit, not yet pushed: reword it with "
              "`git commit --amend -m <subject> -m \"%s\"`, then `git push`." % trailer)
        print("check_red_run: a flagged commit that is not last, or is already pushed: "
              "`git switch -c <new branch> <sha>^`, `git cherry-pick <sha>`, "
              "`git commit --amend -m <subject> -m \"%s\"`, "
              "`git cherry-pick <sha>..<old head>`, `git push -u origin <new branch>`, "
              "then open a replacement PR." % trailer)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
