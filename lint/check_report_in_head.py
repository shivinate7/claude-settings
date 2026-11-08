#!/usr/bin/env python3
"""Fails when a builder's report names a file that is not in its pushed branch head's diff. Stdlib and git only.

    python3 lint/check_report_in_head.py --branch <name> [--base <ref>] [--root <dir>] [--report <path>|-]
        # base: origin/main when no flag is given; root: the current directory; report: stdin when no flag or `-`

A builder's report lists the files it changed on one `Files:` line (`agents/builder.md`). A hook can refuse a
builder's edit and the builder still report it. The reviewer then reads a change that is not there. This check reads the pushed head, never the local tree: it fetches refs/heads/<branch> from origin, and
the base too when <base> is `origin/<name>`, so a stale local ref never stands in. It diffs `--name-only
--no-renames` from the merge base of <base> and that head to the head. A renamed file shows under both names. A fix
round passes `--base <last reviewed head>`, so only the round's own change counts.

The report line: one line that starts, after any blockquote, bullet or bold marks, with `Files:`. It holds
repo-relative paths split on `,` or `;`. Each entry may carry backticks or bold marks (`**path**:10-20`), a leading
`./`, a trailing `.`, a trailing parenthesised note (`(new)`, `(lines 10-20)`), and an optional `:<range>`
(`lint/a.py:10-20`; spaces allowed round the `:` and the dash; a hyphen or an en dash; an `L` before either number,
as in `L10-L20`). A bare range after a separator (`30-40`) continues the prior path's range. `Files: none` (any
case) reports no files. Other lines are not read. The report is read as strict UTF-8, from stdin or the file,
whatever the locale.

Exit 0: every listed path is in the diff. Exit 1: each missing path is named. Exit 2: UNKNOWN, because the branch is
not on origin, git failed, stdin is closed with no --report file, the report file cannot be read, the report is not
UTF-8, has no `Files:` line, more than one, an empty one, `Files: none`, an absolute path entry, or a range with no
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
NOTE = re.compile(r"\s*\([^()]*\)$")
ABSOLUTE = re.compile(r"^(?:/|\\|[A-Za-z]:[\\/])")
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
    """The entry without backticks, bold marks, a trailing period, or a trailing parenthesised note."""
    entry = entry.replace("`", "").replace("**", "").strip()
    while True:
        before = entry
        entry = NOTE.sub("", entry.rstrip(".").strip()).strip("*").strip()
        if entry == before:
            return entry


def reported_paths(report):
    """The repo-relative paths of the report's one Files line, in order, without repeats."""
    lines = [m.group(1) for m in map(FILES_LINE.match, report.splitlines()) if m]
    if not lines:
        raise Unknown("the report has no Files line")
    if len(lines) > 1:
        raise Unknown("the report has %d Files lines, want one" % len(lines))
    entries = [e for e in map(clean_entry, split_entries(lines[0])) if e]
    if len(entries) == 1 and entries[0].lower() == "none":
        raise Unknown("no files reported (the Files line says none)")
    paths = []
    for entry in entries:
        if BARE_RANGE.match(entry):
            if not paths:
                raise Unknown("the Files line starts with a range and no path: " + entry)
            continue
        if ABSOLUTE.match(entry):
            raise Unknown("the Files line holds an absolute path: " + entry)
        entry = clean_entry(RANGE.sub("", entry))
        while entry.startswith("./"):
            entry = entry[2:]
        if entry and entry not in paths:
            paths.append(entry)
    if not paths:
        raise Unknown("the Files line is empty")
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
