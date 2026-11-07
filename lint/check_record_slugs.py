#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in the folders lint/layout.json marks as records. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

Also fails when a debt file deleted, renamed out of the debt folder, or edited to drop its Feel line against
origin/main was a feel-fix (a line starting `**Feel.**`) with no valid device-trial line (`**Device check.**`, then
simulator or device, then an ISO time with a zone): a fix CI passes can still feel wrong on a device.

Also fails when a line the branch adds to the debt notes file (layout key "debt-notes"), or a debt file the branch
adds, names no fix (decision `notes-name-their-fix`: a gap in a file nobody reads never gets fixed). The Fix field is
the one home of this grammar (FIX_BODY, NONE_REASONS, parse_fix); lint/report_guard.py imports it. A valid Fix is:
    Fix: step:<slug>        <slug> is a step file on origin/roadmap (roadmap/data/steps/<slug>.json)
    Fix: none -- <reason>   or "none —"; the reason is one of NONE_REASONS
    Fix: already fixed on main <sha>   a hex sha of 7 to 40 digits (with or without the "none --" lead)
A notes line holds the field anywhere (the last `Fix:` on the line counts). A debt file holds it as a line that
starts `Fix:` at column one, or after one leading `- `. A notes line whose `- <slug>:` already exists at the merge
base is an edit and passes, so old lines never turn red. Only a step Fix reads origin/roadmap, one `git ls-tree` per
step. When that read cannot run, the check prints UNKNOWN, says the read did not run, and exits 1 (CI or not).
Cost: a diff and a show of the notes file, a show of each added debt file, one git process per step named; no
file written, no process left running, no timer.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git

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


ROADMAP = "origin/roadmap"
STEP_PATH = "roadmap/data/steps/%s.json"
NONE_REASONS = ("owner decides", "needs the Mac", "rare and harmless")
SLUG = r"[a-z0-9][a-z0-9-]*"
DASH = r"(?:—|--)"
FIX_BODY = re.compile(
    r"(?:step:(?P<step>" + SLUG + r")(?![\w-])"
    + r"|(?:none\s*" + DASH + r"\s*)?already fixed on main (?P<sha>[0-9a-f]{7,40})(?!\w)"
    + r"|none\s*" + DASH + r"\s*(?P<reason>" + "|".join(re.escape(r) for r in NONE_REASONS) + r")(?!\w))")
FIX_MARK = re.compile(r"(?<![\w-])Fix:[ \t]*")
NOTE_LINE = re.compile(r"^[-*+]\s")
NOTE_SLUG = re.compile(r"^[-*+]\s+([\w.-]+)\s*:")
DEBT_FIX_LINE = re.compile(r"^(?:- )?Fix:")


class RoadmapUnread(Unknown):
    """origin/roadmap could not be read, so a step Fix is not known to be valid. Never green."""


def parse_fix(text):
    """The Fix field of `text`, read after its last `Fix:`: ("step", slug), ("none", reason), ("fixed", sha), or
    None when the field is missing or in no listed form. The text is read as text, never as code: a quote or a
    comment opener before the field changes nothing."""
    marks = list(FIX_MARK.finditer(text))
    if not marks:
        return None
    m = FIX_BODY.match(text, marks[-1].end())
    if not m:
        return None
    if m.group("step"):
        return ("step", m.group("step"))
    if m.group("sha"):
        return ("fixed", m.group("sha"))
    return ("none", m.group("reason"))


def git_text(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def step_exists(root, slug, ref=ROADMAP):
    """True when `ref` holds the step file of `slug`. Raises RoadmapUnread when the ref cannot be read: a read that
    could not run is never a missing step."""
    try:
        git_text(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        return bool(git_text(root, "ls-tree", "--name-only", ref, "--", STEP_PATH % slug).strip())
    except Unknown as err:
        raise RoadmapUnread("the %s read did not run (%s)" % (ref, err))


def added_note_lines(root, path, base="origin/main", head="HEAD"):
    """The bullet lines the branch adds to the notes file `path`, from the merge base of `base` and `head`, minus each
    line whose `- <slug>:` the merge base already holds (an edit). A heading or a blank line is no note. Raises
    Unknown when git cannot say. A file the branch deletes or never holds adds no line, and its base is not read."""
    if not git_text(root, "ls-tree", "--name-only", head, "--", path).strip():
        return []
    diff = git_text(root, "diff", "--unified=0", "--no-color", "--no-ext-diff", "--no-textconv", f"{base}...{head}",
                    "--", path)
    lines, in_hunk = [], False
    for raw in diff.split("\n"):
        if raw.startswith("@@"):
            in_hunk = True
        elif raw.startswith("diff --git"):
            in_hunk = False
        elif in_hunk and raw.startswith("+"):
            lines.append(raw[1:].rstrip("\r"))
    notes = [l for l in lines if NOTE_LINE.match(l)]
    if not notes:
        return []
    mb = git_text(root, "merge-base", base, head).strip()
    held = set()
    if git_text(root, "ls-tree", "--name-only", mb, "--", path).strip():
        for old in git_text(root, "show", mb + ":" + path).splitlines():
            m = NOTE_SLUG.match(old)
            if m:
                held.add(m.group(1))
    return [l for l in notes if not (NOTE_SLUG.match(l) and NOTE_SLUG.match(l).group(1) in held)]


def added_fixes(root, files, head="HEAD"):
    """[(path, label, fixes)] for each note line the branch adds and each debt file among `files` (the added files).
    `fixes` holds one parse_fix result per Fix field: one for a note line, one per Fix line of a debt file. So []
    is a debt file with no Fix line, and None marks a field in no listed form."""
    out = []
    for path in layout.candidates(root, "debt-notes"):
        for line in added_note_lines(root, path):
            m = NOTE_SLUG.match(line)
            out.append((path, m.group(1) if m else line.strip()[:40], [parse_fix(line)]))
    debt = debt_file(root)
    for path in files:
        if debt(path):
            out.append((path, path, [parse_fix(l) for l in show(root, head, path) if DEBT_FIX_LINE.match(l)]))
    return out


def fix_failures(root, entries):
    """[(path, label, why)] for each entry of added_fixes with no valid Fix. Raises RoadmapUnread when a step
    cannot be read."""
    bad = []
    for path, label, fixes in entries:
        if not fixes or None in fixes:
            bad.append((path, label, "names no valid Fix (step:<slug> on %s, or none -- <reason>)" % ROADMAP))
            continue
        for kind, value in fixes:
            if kind == "step" and not step_exists(root, value):
                bad.append((path, label, "names step:%s, which is not on %s" % (value, ROADMAP)))
    return bad


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
        if args:  # files given: the diff is not read, so the feel-fix and Fix checks do not run
            files, feel, entries = args, [], []
        else:
            files, moved = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, moved)
            entries = added_fixes(ROOT, files)
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
    try:
        unfixed = fix_failures(ROOT, entries)
    except RoadmapUnread as err:  # a step Fix cannot be judged: red on any machine, never green
        print("check_record_slugs: UNKNOWN, %s, so no step Fix was checked" % err)
        return 1
    for path, label, why in unfixed:
        print('check_record_slugs: FAIL: "%s" %s: %s' % (label, why, path))
    return 1 if bad or feel or unfixed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
