#!/usr/bin/env python3
"""Fails when a builder's report names a file that is not in its pushed branch head's diff. Stdlib and git only.

    python3 lint/check_report_in_head.py --branch <name> [--base <ref>] [--root <dir>] [--report <path>|-]
        # base: origin/main when no flag is given; root: the current directory; report: stdin when no flag or `-`

A builder's report lists the files it changed on one `Files:` line (`agents/builder.md`). A hook can refuse a
builder's edit and the builder still report it. The reviewer then reads a change that is not there. This check reads the pushed head, never the local tree: it fetches refs/heads/<branch> from origin, and
the base too when <base> is `origin/<name>`, so a stale local ref never stands in. It diffs `--name-only
--no-renames` from the merge base of <base> and that head to the head. A renamed file shows under both names. A fix
for a review passes `--base <last reviewed head>`, so only that fix's own change counts.

The report line: one line that starts, after any blockquote, bullet or bold marks, with `Files:`. It holds
repo-relative paths split on `,` or `;`. Each entry may carry backticks or bold marks (`**path**:10-20`), a leading
`./`, a trailing `.`, a trailing parenthesised note (`(new)`, `(lines 10-20)`), a note after the path (`path: new
helper`, `path - added`), and an optional `:<range>` (`lint/a.py:10-20`; spaces allowed round the `:` and the dash; a
hyphen or an en dash; an `L` before either number, as in `L10-L20`). A bare range after a separator (`30-40`)
continues the prior path's range. A path-like token inside parentheses (`(lint/a.py)`, `(see lint/a.py)`) is a
listed path. The list goes on past the `Files:` line in two forms: a next line after a line that ends in `,` or `;`
(a wrapped line), and `- ` or `* ` bullets right after it. Each bullet counts only when it is one path-like token,
so a prose bullet (`- Done: widget edited`) is not read. `Files: none` (any case) reports no files. A blank line ends
the list. Other lines are not read. The report is read as strict UTF-8, from stdin or the file,
whatever the locale.

Exit 0: every listed path is in the diff. Exit 1: each missing path is named. Exit 2: UNKNOWN, because the branch is
not on origin, git failed, stdin is closed with no --report file, the report file cannot be read, the report is not
UTF-8, has no line in the accepted form `Files:` (`1. Files:` and `Files (changed):` are not), more than one, an empty one, `Files: none`, an absolute path entry, or a range with no
path before it.
Unknown is never 0 here: a green exit on an unread head would hide the gap.

Scope: file level. It shows that each reported file changed from the base, not that each reported edit landed: a
second edit to a file that already changed passes (debt `report-in-head-file-level`). A changed file the report
leaves out is not judged.

Cost: 3 git calls per run (one fetch of the branch and the base, one rev-parse of the fetched head, one diff). The
fetch adds objects and updates FETCH_HEAD and the remote-tracking refs it fetches, and nothing else. The lane runs it once per builder report, before it spawns the
reviewer (decision `builder-report-in-head`).
"""
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

TAG = "check_report_in_head"
FILES_LINE = re.compile(r"^[\s>*\-]*Files\**\s*:\**\s*(.*)$")
DASHES = "-–—"
SPAN = r"L?\d+(?:\s*[%s]\s*L?\d+)?" % DASHES
RANGE = re.compile(r"\s*:\s*%s$" % SPAN)
BARE_RANGE = re.compile(r"^%s$" % SPAN)
ABSOLUTE = re.compile(r"^(?:/|\\|[A-Za-z]:[\\/])")
PAREN = re.compile(r"\(([^()]*)\)")
BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
# a note after the path: `path: new helper` or `path - added`; a range was cut before this runs
NOTE_AFTER = re.compile(r"^(\S+?)\s*(?::\s+|\s+[%s]\s+)\S.*$" % DASHES)
# path-like: a slash, or an extension that starts with a letter, so `e.g.` and `v1.10` are not paths
EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]{1,4}$")
FORM = "the accepted form is one line `Files: path, path`"
USAGE = "usage: check_report_in_head.py --branch <name> [--base <ref>] [--root <dir>] [--report <path>|-]"


class Unknown(Exception):
    """A read failed or the report cannot be read, so the verdict is not known."""


def git(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def split_entries(line):
    """The line's entries, split on `,` and `;` outside parentheses, so a note like `(new, big)` stays whole."""
    entries, depth, start = [], 0, 0
    for i, ch in enumerate(line):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif ch in ",;" and not depth:
            entries.append(line[start:i])
            start = i + 1
    entries.append(line[start:])
    return entries


def clean_entry(entry):
    """The entry without backticks, bold marks, or a trailing period."""
    entry = entry.replace("`", "").replace("**", "").strip()
    while True:
        before = entry
        entry = entry.rstrip(".").strip().strip("*").strip()
        if entry == before:
            return entry


def path_like(token):
    return "/" in token or bool(EXTENSION.search(token))


def take_parens(entry):
    """(the entry without its parenthesised groups, the path-like tokens inside them). `(new)` holds none."""
    inner = []
    while True:
        m = PAREN.search(entry)
        if not m:
            return entry, inner
        for token in re.findall(r"[^\s,;]+", clean_entry(m.group(1))):
            token = clean_entry(RANGE.sub("", token.strip(":")))
            if path_like(token):
                inner.append(token)
        entry = entry[:m.start()] + " " + entry[m.end():]


def list_items(report):
    """[(text, is_bullet)] of the report's one Files line and the lines that go on from it."""
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if FILES_LINE.match(line)]
    if not starts:
        raise Unknown("the report has no `Files:` line; " + FORM)
    if len(starts) > 1:
        raise Unknown("the report has %d `Files:` lines, want one; %s" % (len(starts), FORM))
    items = [(FILES_LINE.match(lines[starts[0]]).group(1), False)]
    for line in lines[starts[0] + 1:]:
        bullet = BULLET.match(line)
        if not line.strip() or FILES_LINE.match(line):
            break
        if bullet:
            items.append((bullet.group(1), True))
        elif items[-1][0].rstrip().endswith((",", ";")):
            items.append((line, False))
        else:
            break
    return items


def reported_paths(report):
    """The repo-relative paths of the report's one Files line and its continuation, in order, without repeats."""
    items = list_items(report)
    entries = [(e, bullet) for text, bullet in items for e in split_entries(text)]
    if len(entries) == 1 and clean_entry(entries[0][0]).lower() == "none":
        raise Unknown("no files reported (the Files line says none)")
    paths = []
    for raw, bullet in entries:
        raw, inner = take_parens(raw)
        entry = clean_entry(raw)
        found = []
        if BARE_RANGE.match(entry):
            if not paths and not bullet:
                raise Unknown("the Files line starts with a range and no path: " + entry)
        elif entry:
            if ABSOLUTE.match(entry):
                raise Unknown("the Files line holds an absolute path: " + entry)
            entry = clean_entry(RANGE.sub("", entry))
            note = NOTE_AFTER.match(entry)
            entry = clean_entry((note.group(1) if note else entry).rstrip(":"))
            while entry.startswith("./"):
                entry = entry[2:]
            # a bullet is a path only when it is one path-like token, so prose in a bullet is not read
            if entry and not (bullet and (len(entry.split()) > 1 or not path_like(entry))):
                found.append(entry)
        for path in found + inner:
            if ABSOLUTE.match(path):
                raise Unknown("the Files line holds an absolute path: " + path)
            if path not in paths:
                paths.append(path)
    if not paths:
        raise Unknown("the Files line is empty; " + FORM)
    return paths


def pushed_diff(root, branch, base):
    """(head sha, set of paths changed from merge-base(base, head) to head), read from origin's refs/heads/<branch>."""
    specs = ["+refs/heads/%s:refs/remotes/origin/%s" % (branch, branch)]
    if base.startswith("origin/") and base != "origin/" + branch:
        name = base[len("origin/"):]
        specs.append("+refs/heads/%s:refs/remotes/origin/%s" % (name, name))
    try:
        git(root, "fetch", "--quiet", "--no-tags", "origin", *specs)
    except Unknown as err:
        raise Unknown("branch %s (or base %s) is not readable on origin: %s" % (branch, base, err))
    head = git(root, "rev-parse", "--verify", "refs/remotes/origin/%s^{commit}" % branch).strip()
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
            stdin = getattr(sys.stdin, "buffer", None)
            if stdin is None:
                raise Unknown("stdin is closed and no --report file was given")
            raw = stdin.read()
        else:
            with open(report_path, "rb") as f:
                raw = f.read()
        try:
            report = raw.decode("utf-8-sig")
        except UnicodeDecodeError as err:
            raise Unknown("the report is not UTF-8 (%s)" % err)
        paths = reported_paths(report)
        head, changed = pushed_diff(root, branch, base)
    except (Unknown, OSError, ValueError) as err:
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
