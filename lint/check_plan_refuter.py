#!/usr/bin/env python3
"""Fails when a plan record that a range adds carries no `Refuter:` line. Stdlib and git only.

    python3 lint/check_plan_refuter.py --base <sha> [--root <dir>]
        # the base is env BASE_SHA when no flag is given; the repo is the current directory unless --root names one

A plan is refuted before a lane builds it. The refuter records its verdict on one line of the plan:

    Refuter: <role and model>, <date>, <verdict>         or the same line wrapped as **Refuter:** <text>

The check lists the files that base...HEAD adds, and judges each one that sits directly in the plans home and is
named <name>.md. The plans home is the "plans" kind that lint/layout.py gives for the repo it reads (the one home:
a rolled-out repo reads lint/layout.json, an unrolled repo its legacy path). A plan in a subfolder of the home, a
file that is not .md, and a plan that the range only modifies are not judged. The check reads each plan as it stands
at HEAD, so a line added later in the range counts, and a line removed again does not. The line must start at column
one, hold a word character after the colon (and any `**`) on the same line, with a <...> placeholder not counted as
text, and sit outside a fenced code block (``` or ~~~, closed by a fence of the same mark that is as long as the
opener). A line that starts with the retired word does not count.

Cost: two git processes to read the range, one more per judged plan. No file, timer or log is written.

Exit 0: clean. Exit 1: a plan is named by its path. Exit 2: UNKNOWN, because git could not read the range, the
layout could not be read, or no base was given. Unknown is never 0 here: a green exit on an unread range would hide a gap.
"""
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import layout  # noqa: E402  the one home of the plans kind (lint/layout.py)

REFUTER = re.compile(r"(?:\*\*Refuter:\*\*|Refuter:)(.*)")
PLACEHOLDER = re.compile(r"<[^<>]*>")
WORD = re.compile(r"\w")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


class Unknown(Exception):
    """A read failed, so the range or the plans home is not known."""


def git(root, *args):
    try:
        r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    except OSError as err:  # a --root that names no folder
        raise Unknown("git %s could not start in %s: %s" % (args[0], root, err)) from err
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def has_refuter(text):
    """True when a line outside every fenced block is a Refuter line with a word after the colon."""
    fence = None  # the opening run of the fence we are inside, or None
    for line in text.splitlines():
        mark = FENCE.match(line)
        if fence is None:
            if mark:
                fence = mark.group(1)
                continue
            found = REFUTER.match(line)
            if found and WORD.search(PLACEHOLDER.sub("", found.group(1))):
                return True
        elif mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence) and not line.strip().strip(fence[0]):
            fence = None
    return False


def added_plans(root, base):
    """The .md files that base...HEAD adds directly in the plans home, sorted."""
    git(root, "rev-parse", "--verify", base + "^{commit}")
    try:
        home = layout.path(root, "plans")
    except layout.LayoutError as err:
        raise Unknown("layout unreadable: %s" % err) from err
    out = git(root, "diff", "--no-renames", "--diff-filter=A", "--name-only", "-z", base + "...HEAD")
    prefix = home.rstrip("/") + "/"
    return sorted(path for path in out.split("\0")
                  if path.startswith(prefix) and "/" not in path[len(prefix):] and path.endswith(".md"))


def gaps(root, base):
    """One line per added plan with no Refuter line. Raises Unknown when a read fails."""
    return ["check_plan_refuter: FAIL: %s adds a plan with no `Refuter:` line" % path
            for path in added_plans(root, base) if not has_refuter(git(root, "show", "HEAD:" + path))]


def main(args):
    base, root = os.environ.get("BASE_SHA", ""), os.getcwd()
    rest = list(args)
    while rest:
        flag = rest.pop(0)
        if flag not in ("--base", "--root") or not rest:
            print("check_plan_refuter: FAIL: usage: check_plan_refuter.py --base <sha> [--root <dir>]")
            return 1
        if flag == "--base":
            base = rest.pop(0)
        else:
            root = rest.pop(0)
    if not base:
        print("check_plan_refuter: UNKNOWN, no base: pass --base <sha> or set BASE_SHA")
        return 2
    try:
        bad = gaps(root, base)
    except Unknown as err:
        print("check_plan_refuter: UNKNOWN, " + str(err))
        return 2
    for line in bad:
        print(line)
    if bad:
        print("check_plan_refuter: have a refuter read each plan above, then add a line `Refuter: <role and model>, "
              "<date>, <verdict>` at line start, outside any code block, and push.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
