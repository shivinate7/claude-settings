#!/usr/bin/env python3
"""Fails when a numbered part of a plan cites no live roadmap step. Stdlib and git only.

    python3 lint/check_plan_step_cites.py [--root <dir>]
        # the repo is the current directory unless --root names one

A plan part is work that a lane builds, and a lane starts from a roadmap step. So each part names its step.

A plan is a file directly in the plans home (the "plans" kind that lint/layout.py gives for the repo it reads) named
<name>.md. The check reads each plan as it stands in the working tree. A part is any indented numbered line: `N. text`
with 2 or more spaces before it. Its label is the nearest ruling bullet above it, `- **<ID>.` (ID like R26 or G1),
else `(no ruling id)`. The part text is the part line and the lines after it that sit indented deeper than its marker.
It ends at a blank line, a line at the marker's indent or less, the next part, a ruling bullet or a heading.

Each part needs one valid cite `step:<slug>` in its part text, outside a code fence. A cite counts when no letter or
hyphen sits before `step:`, so a tag such as `cs-step:<slug>` is no cite. A part passes when any one cite is valid.
A valid cite names a step file roadmap/data/steps/<slug>.json on the roadmap branch. The branch is read with git
(refs/remotes/origin/roadmap first, then refs/heads/roadmap), never from the working tree, so the steps are the live
ones and no list is copied here. An opaque slug (one letter then digits, such as c55) says nothing alone, so it is
valid only with a gloss in parentheses right after it: `step:c55 (short gloss)`.

A fence is a line of 3 or more backticks or tildes at any indent, closed by a fence of the same mark that is at least
as long. A fenced block holds no ruling, no part and no cite. The fence pattern takes any indent because a part's
content sits 5 spaces in, past the 0 to 3 that a bare CommonMark fence allows.

Output, one line per flagged part: `<file>:<line>: <ruling> part <N>: <reason>`.

Cost: one git process to find the roadmap branch (two when origin/roadmap is absent), one to list its steps, and one
read per plan file. No file, timer or log is written.

Exit 0: clean. Exit 1: a part has no valid cite. Exit 2: UNKNOWN, because the roadmap branch, the repo or the plans
home could not be read. Unknown is never 0 here: a green exit on an unread branch would hide a gap. A repo whose plans
home does not exist holds no plans, so it is clean.
"""
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layout  # noqa: E402  the one home of the plans kind (lint/layout.py)
sys.path.append(os.path.join(HERE, "..", "hooks"))  # appended, so no hooks module shadows a lint one
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

STEPS_DIR = "roadmap/data/steps/"  # the folder of step files on the roadmap branch
ROADMAP_REFS = ("refs/remotes/origin/roadmap", "refs/heads/roadmap")  # tried in order
NO_RULING = "(no ruling id)"

PART = re.compile(r"^( {2,})(\d+)\.(?:\s|$)")
RULING = re.compile(r"^- \*\*([A-Za-z]+\d+[A-Za-z0-9]*)\.")
RULING_ANY_INDENT = re.compile(r"^\s*- \*\*[A-Za-z]+\d+[A-Za-z0-9]*\.")
HEADING = re.compile(r"^\s*#{1,6}(?:\s|$)")
FENCE = re.compile(r"^\s*(`{3,}(?=[^`]*$)|~{3,})")  # any indent; a backtick fence's info string holds no backtick
CITE = re.compile(r"(?<![A-Za-z-])step:([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")
OPAQUE = re.compile(r"^[A-Za-z]\d+$")
GLOSS = re.compile(r"\s*\(\s*\S[^)]*\)")


class Unknown(Exception):
    """A read failed, so the roadmap branch or the plans home is not known."""


def git(root, *args, check=True):
    try:
        done = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    except OSError as err:  # git is missing, or --root names no folder
        raise Unknown("git %s could not start in %s: %s" % (args[0], root, err)) from err
    if check and done.returncode:
        raise Unknown("git %s failed: %s" % (args[0], done.stderr.strip()))
    return done


def live_steps(root):
    """The slugs of the step files on the roadmap branch."""
    for ref in ROADMAP_REFS:
        if git(root, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False).returncode == 0:
            break
    else:
        raise Unknown("no roadmap branch: neither origin/roadmap nor roadmap exists in %s" % root)
    out = git(root, "ls-tree", "--name-only", "-z", ref, STEPS_DIR).stdout
    return {name[len(STEPS_DIR):-len(".json")] for name in out.split("\0")
            if name.startswith(STEPS_DIR) and name.endswith(".json")}


def plan_files(root):
    """The plan files directly in the plans home, as repo-relative paths, sorted."""
    try:
        home = layout.path(root, "plans")
    except layout.LayoutError as err:
        raise Unknown("layout unreadable: %s" % err) from err
    folder = os.path.join(root, *home.split("/"))
    try:
        names = os.listdir(folder)
    except FileNotFoundError:
        return []
    except OSError as err:
        raise Unknown("plans home unreadable: %s: %s" % (home, err)) from err
    return sorted(home.rstrip("/") + "/" + name for name in names
                  if name.endswith(".md") and os.path.isfile(os.path.join(folder, name)))


def fenced_lines(lines):
    """One flag per line: True for a fence line and each line inside a fenced block."""
    flags, fence = [], None
    for line in lines:
        mark = FENCE.match(line)
        if fence is None:
            fence = mark.group(1) if mark else None
            flags.append(fence is not None)
        else:
            flags.append(True)
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence) \
                    and not line.strip().strip(fence[0]):
                fence = None
    return flags


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def part_text(lines, fenced, start, marker):
    """The part line and the unfenced lines below it that belong to it, joined."""
    kept = [lines[start]]
    for at in range(start + 1, len(lines)):
        line = lines[at]
        if not line.strip() or indent_of(line) <= marker:
            break
        if not fenced[at] and (PART.match(line) or RULING_ANY_INDENT.match(line) or HEADING.match(line)):
            break
        if not fenced[at]:
            kept.append(line)
    return "\n".join(kept)


def reason(text, steps):
    """None when the part text holds a valid cite, else why it does not."""
    first = None
    for cite in CITE.finditer(text):
        slug = cite.group(1)
        if slug not in steps:
            problem = "step %s does not exist" % slug
        elif OPAQUE.match(slug) and not GLOSS.match(text, cite.end()):
            problem = "opaque step %s needs a gloss" % slug
        else:
            return None
        first = first or problem
    return first or "no step cited"


def gaps(root):
    """One line per part with no valid cite. Raises Unknown when a read fails."""
    steps = live_steps(root)
    found = []
    for rel in plan_files(root):
        try:
            with open(os.path.join(root, *rel.split("/")), encoding="utf-8", errors="replace", newline="") as handle:
                lines = handle.read().replace("\r\n", "\n").split("\n")
        except OSError as err:
            raise Unknown("plan unreadable: %s: %s" % (rel, err)) from err
        fenced = fenced_lines(lines)
        ruling = NO_RULING
        for at, line in enumerate(lines):
            if fenced[at]:
                continue
            bullet = RULING.match(line)
            if bullet:
                ruling = bullet.group(1)
                continue
            part = PART.match(line)
            if part:
                why = reason(part_text(lines, fenced, at, len(part.group(1))), steps)
                if why:
                    found.append("%s:%d: %s part %s: %s" % (rel, at + 1, ruling, part.group(2), why))
    return found


def main(args):
    root = os.getcwd()
    rest = list(args)
    while rest:
        flag = rest.pop(0)
        if flag != "--root" or not rest:
            print("check_plan_step_cites: UNKNOWN, usage: check_plan_step_cites.py [--root <dir>]")
            return 2
        root = rest.pop(0)
    try:
        if not os.path.isdir(root):
            raise Unknown("--root names no folder: %s" % root)
        bad = gaps(root)
    except Unknown as err:
        print("check_plan_step_cites: UNKNOWN, " + str(err))
        return 2
    for line in bad:
        print(line)
    if bad:
        print("check_plan_step_cites: file a roadmap step for each part above, then cite it in the part as "
              "`step:<slug>`, outside any code block. An id such as c55 needs a gloss: `step:c55 (short gloss)`.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
