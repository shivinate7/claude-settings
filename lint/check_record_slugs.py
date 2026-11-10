#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in the folders lint/layout.json marks as records. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

Also fails when a debt file deleted, renamed out of the debt folder, or edited to drop its Feel line against
origin/main was a feel-fix (a line starting `**Feel.**`) with no valid device-trial line (`**Device check.**`, then
simulator or device, then an ISO time with a zone): a fix CI passes can still feel wrong on a device.

Two whole-tree checks read every decision and debt file, whatever the diff holds:
    check_gloss: the first backticked cite of another record's slug in a file carries a gloss, ` (` two or more
        words `)`. A reader who meets a bare slug has to open the record to learn what it is.
    check_links: a debt's Decision part is `none` or names an existing decision; a decision's gap section
        (`## Safety holes, named`, `## Known gaps`, `## Gaps`) lists only debts that exist; and a debt that cites
        a decision with a gap section is named in it. A link that rots leaves a reader on a dead end.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git and the whole-tree checks
        # no files: the diff against origin/main, then the whole-tree checks

The functions take a repo root, so lint/compliance_probes.py reads a child's records with them.
"""
import datetime
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)

MAX = 32
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Unknown(Exception):
    """A git read failed, so the added files are not known."""


def record_dirs(root):
    """The record folders of `root` as path prefixes. Raises layout.LayoutError when the layout cannot be read."""
    return tuple(folder + "/" for folder in layout.folders(root, "record"))


def git_names(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return [name for name in r.stdout.split("\0") if name]


def changes(root, base="origin/main", head="HEAD"):
    """(added, moved) files of `root` from the merge base of `base` and `head` to `head`, from one process. `moved` holds
    (status, old, new) for each delete, modify and rename; a rename names two paths. -M is explicit, so diff.renames in a
    config never moves the verdict. Raises Unknown when git cannot say."""
    names = git_names(root, "diff", "--name-status", "-z", "-M", f"{base}...{head}")
    added, moved, i = [], [], 0
    while i < len(names):
        status = names[i]
        n = 2 if status[0] in "RC" else 1
        paths = names[i + 1:i + 1 + n]
        i += 1 + n
        if status == "A":
            added.append(paths[0])
        elif status[0] in "DMR":
            moved.append((status[0], paths[0], paths[-1]))
    return added, moved


def added(root):
    """The files `root` adds against its origin/main. Raises Unknown when git cannot say."""
    return changes(root)[0]


def marker(name=None):
    """The regex of a record's marker line: `**Name.**` at column one, or after `- `. With no name, any marker."""
    return re.compile(r"^(?:- )?\*\*" + (re.escape(name) if name else r"[^*]+") + r"\.\*\*")


FEEL = marker("Feel")
TRIAL = re.compile(r"^(?:- )?\*\*Device check\.\*\*\s*(simulator|device)[,\s]+(\S+)\s*$")


def has_trial(line):
    """True for a device-trial line: the marker, simulator or device, then an ISO time with a zone."""
    m = TRIAL.match(line)
    if not m:
        return False
    try:
        return datetime.datetime.fromisoformat(m.group(2).replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def show(root, ref, path):
    r = _nowindow.run(["git", "show", ref + ":" + path], cwd=root, capture_output=True, encoding="utf-8",
                      errors="replace")
    if r.returncode:
        raise Unknown("git show failed: %s" % r.stderr.strip())
    return r.stdout.splitlines()


def debt_file(root):
    """A test of a path: is it a debt file of `root`? The folders are layout.candidates: the first one that exists, then the layout's own.
    A repo that legacy-repos keeps its debts elsewhere has that one folder: the layout's own is not where its debts are.
    The folder's README and notes file sit beside the debts but are not debts: never checked, never shown."""
    kept = layout.unmoved(root).get("debts")
    dirs = tuple(p + "/" for p in ((kept,) if kept else layout.candidates(root, "debts")))
    not_debts = {d + "README.md" for d in dirs} | set(layout.candidates(root, "debt-notes"))
    return lambda f: f.startswith(dirs) and f.endswith(".md") and f not in not_debts


def unchecked_feel_debts(root, moved):
    """[(path, how)] for each debt whose origin/main text has a Feel line and no valid device-trial line, and that
    the branch deletes or renames out of the debt folder ("deleted"), or edits or renames inside it so the Feel
    line is gone ("dropped"). Markers count at line start, with an optional "- ". Raises Unknown when git cannot
    show a file."""
    debt = debt_file(root)
    out = []
    for status, old, new in moved:
        if not debt(old):
            continue
        lines = show(root, "origin/main", old)
        if not any(FEEL.match(l) for l in lines) or any(has_trial(l) for l in lines):
            continue
        if status == "D" or not debt(new):
            out.append((old, "deleted"))
        elif not any(FEEL.match(l) for l in show(root, "HEAD", new)):
            out.append((new, "dropped"))
    return out


def tracked(root):
    return git_names(root, "ls-files", "-z")


def too_long(files, dirs):
    """The record files among `files` whose slug is over MAX characters. Same normpath as
    lint/check_ruling_kind.py, so ./decisions/x.md is judged like decisions/x.md."""
    return [f for f in files if os.path.normpath(f).replace("\\", "/").startswith(dirs)
            and f.endswith(".md") and len(os.path.basename(f.replace("\\", "/"))[:-3]) > MAX]


# Whole-tree checks. Each returns problem strings for the records under `root`; none reads git.

GAP_HEADING = re.compile(r"^## (?:Safety holes, named|Known gaps|Gaps)\s*$")
FENCE = re.compile(r"^\s*(?:```|~~~)")
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")  # one inline span: its own backtick run closes it
SPAN_ONLY = re.compile(r"`([^`\n]+)`")
SLUG = r"[a-z0-9][a-z0-9-]*"
DECISION_PART = marker("Decision")
WHAT_PART = marker("What")
DEBT_LABEL = re.compile(r"\bdebts?:?\s+((?:`[^`\n]+`(?:\s*,\s*(?:and\s+)?|\s+and\s+)?)+)", re.I)
DEBT_HEAD = re.compile(r"^(?:[-*]\s+)?debts?:\s*$", re.I)  # a label line whose list is the bullets below it


def record_files(root):
    """({slug: path} of decisions, {slug: path} of debts) of `root`: the first existing folder of each kind. The
    folder's README and the debt notes file sit beside the records but are not records."""
    skip = {"README.md"} | {os.path.basename(n) for n in layout.candidates(root, "debt-notes")}

    def stems(kind):
        for rel in layout.candidates(root, kind):
            folder = os.path.join(root, *rel.split("/"))
            if os.path.isdir(folder):
                return {f[:-3]: rel + "/" + f for f in sorted(os.listdir(folder)) if f.endswith(".md") and f not in skip}
        return {}
    return stems("decisions"), stems("debts")


def read_lines(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def prose(lines):
    """`lines` with fenced code blocks blanked, so a cite shown as an example is not read."""
    out, fenced = [], False
    for line in lines:
        if FENCE.match(line):
            fenced = not fenced
            out.append("")
        else:
            out.append("" if fenced else line)
    return out


def gloss_after(text, end):
    """The words of the parenthesised gloss that follows `text[:end]`, or [] when none does. Parens nest, so a gloss
    may hold a code span or a call like f(x)."""
    m = re.compile(r"\s*\(").match(text, end)
    if not m:
        return []
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return text[m.end():i - 1].split() if not depth else []


def check_gloss(root):
    """Problems for each record file whose first backticked cite of another record's slug has no gloss of two or
    more words. Later cites of the same slug are free."""
    decisions, debts = record_files(root)
    slugs = {**decisions, **debts}
    problems = []
    for own, rel in slugs.items():
        text = "\n".join(prose(read_lines(root, rel)))
        seen = set()
        for m in CODE_SPAN.finditer(text):
            cite = m.group(2).strip()
            if cite not in slugs or cite == own or cite in seen:
                continue
            seen.add(cite)
            if len(gloss_after(text, m.end())) < 2:
                problems.append("%s: first cite of `%s` has no gloss of two or more words in parentheses" % (rel, cite))
    return problems


def decision_slug(line):
    """What a debt's Decision line names: "none" for none, the slug for a slug, else None."""
    rest = DECISION_PART.sub("", line, count=1).strip()
    m = re.match(r"`?(" + SLUG + r")`?(?![A-Za-z0-9-])", rest)
    return m.group(1) if m else None


def gap_sections(lines):
    """The lines of each gap section of a decision, one list per section. A section ends at the next H2."""
    out, current = [], None
    for line in prose(lines):
        if line.startswith("## "):
            current = [] if GAP_HEADING.match(line) else None
            if current is not None:
                out.append(current)
        elif current is not None:
            current.append(line)
    return out


def listed_debts(section):
    """The slugs a gap section labels as debts: the spans after `debt` or `debts`, and the bullets under a `Debts:`
    line. Only those leading spans count, so a code span inside a gloss, or a note, is not a debt."""
    found, bullets = [], False
    for line in section:
        if bullets and re.match(r"\s*[-*]\s+`", line):
            found.append(SPAN_ONLY.search(line).group(1))
            continue
        bullets = bool(DEBT_HEAD.match(line.strip()))
        for m in DEBT_LABEL.finditer(line):
            found += SPAN_ONLY.findall(m.group(1))
    return found


def check_links(root):
    """Problems for each debt whose Decision part is neither `none` nor an existing decision, each stale debt a gap
    section lists, and each debt that cites a decision with a gap section but is not named there."""
    decisions, debts = record_files(root)
    gaps = {}  # decision slug -> every span its gap sections hold: a debt named in any form is listed
    problems = []
    for slug, rel in decisions.items():
        sections = gap_sections(read_lines(root, rel))
        if not sections:
            continue
        lines = [line for s in sections for line in s]
        gaps[slug] = {c for line in lines for c in SPAN_ONLY.findall(line)}
        for debt in listed_debts(lines):
            if debt not in debts:
                problems.append("%s: gap section lists `%s`, which is no debt file" % (rel, debt))
    for slug, rel in debts.items():
        parts = [l for l in prose(read_lines(root, rel)) if DECISION_PART.match(l)]
        if not parts:
            if any(WHAT_PART.match(l) for l in read_lines(root, rel)):  # a file with no What part is no shaped debt yet
                problems.append("%s: no Decision part" % rel)
            continue
        named = decision_slug(parts[0])
        if named is None:
            problems.append("%s: Decision part names no decision slug and is not `none`" % rel)
        elif named != "none" and named not in decisions:
            problems.append("%s: Decision part names `%s`, which is no decision file" % (rel, named))
        elif named in gaps and slug not in gaps[named]:
            problems.append("%s: cites `%s`, whose gap section does not name `%s`" % (rel, named, slug))
    return problems


def main(args):
    unknown = [a for a in args if a.startswith("-")]
    if unknown:  # read as a file name, an unknown option would skip git and check nothing
        print("check_record_slugs: FAIL: unknown option: %s" % " ".join(unknown))
        return 1
    try:
        dirs = record_dirs(ROOT)
    except layout.LayoutError as err:  # a check that cannot read its folders is red, never green
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    try:
        if args:  # files given: neither git nor the whole tree is read, so only the slug length is checked
            files, feel, whole = args, [], []
        else:
            whole = check_gloss(ROOT) + check_links(ROOT)
            files, moved = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, moved)
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        return 1 if os.environ.get("CI") else 0  # CI exit code is a verdict: unknown is red there
    bad = too_long(files, dirs)
    for f in bad:
        print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
    for f, how in feel:
        print("check_record_slugs: FAIL: feel-fix debt %s with no device check: %s"
              % ("deleted" if how == "deleted" else "lost its Feel line", f))
    for problem in whole:
        print("check_record_slugs: FAIL: " + problem)
    return 1 if bad or feel or whole else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
