#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in the folders lint/layout.json marks as records. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

Also fails when the lane's own diff adds a notes row whose `- <slug>:` the notes file already holds, or adds the same
slug twice (lane_duplicate_slugs). A duplicate that main already holds does not fail a lane that adds none.

Also fails when a debt file deleted, renamed out of the debt folder, or edited to drop its Feel line against
origin/main was a feel-fix (a line starting `**Feel.**`) with no valid device-trial line (`**Device check.**`, then
simulator or device, then an ISO time with a zone): a fix CI passes can still feel wrong on a device.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git; a duplicate anywhere in the notes file fails
    python3 lint/check_record_slugs.py --list
        # print every duplicate note slug, main's included, and exit 0

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


NOTE_ROW = re.compile(r"^- ([A-Za-z0-9][\w.-]*)[ \t]*:", re.M)


def note_slug_counts(text):
    """({lowercased slug: slug as first written}, {lowercased slug: row count}) of the rows of `text`, a notes file."""
    first, seen = {}, {}
    for slug in NOTE_ROW.findall(text):
        key = slug.lower()
        first.setdefault(key, slug)
        seen[key] = seen.get(key, 0) + 1
    return first, seen


def duplicate_note_slugs(text):
    """The slugs that `text`, a notes file, writes as the start of two or more rows (`- <slug>:` at line start, spaces
    before the colon allowed), in first-seen order, spelled as first written. Case does not tell slugs apart.
    A slug named inside a row's text is not a row."""
    first, seen = note_slug_counts(text)
    return [first[key] for key, n in seen.items() if n > 1]


def lane_duplicate_slugs(text, base_text):
    """The duplicate slugs of `text` that the lane adds against `base_text`: a slug with more rows than the base held
    that now has two or more. Editing a row of a duplicate the base already holds adds none."""
    first, seen = note_slug_counts(text)
    base = note_slug_counts(base_text)[1]
    return [first[key] for key, n in seen.items() if n > 1 and n > base.get(key, 0)]


def report_duplicates(dup):
    for slug in dup:
        print("check_record_slugs: FAIL: notes slug written on more than one row: %s. Merge the rows into one, "
              "or give each its own slug." % slug)


def notes_file(root):
    """The path of the first notes file that exists among layout.candidates, or None when none does."""
    for rel in layout.candidates(root, "debt-notes"):
        if os.path.isfile(os.path.join(root, rel)):
            return rel
    return None


def notes_text(root):
    """The text of the notes file, or "" when none exists."""
    rel = notes_file(root)
    if rel is None:
        return ""
    with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def base_notes_text(root, rel, base="origin/main"):
    """The text of `rel` at the merge base of `base` and HEAD, or "" when the base has no such file. Raises Unknown when
    git cannot say, or cannot show a file the base holds."""
    sha = git_names(root, "merge-base", base, "HEAD")[0].strip()
    if not git_names(root, "ls-tree", "-z", "--name-only", sha, "--", rel):
        return ""
    return "\n".join(show(root, sha, rel)) + "\n"


def main(args):
    if args == ["--list"]:
        try:
            for slug in duplicate_note_slugs(notes_text(ROOT)):
                print("check_record_slugs: duplicate note slug: %s" % slug)
        except layout.LayoutError as err:
            print("check_record_slugs: FAIL: " + str(err))
            return 1
        return 0
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
        dup = duplicate_note_slugs(notes_text(ROOT))  # read first: an UNKNOWN below must not hide a duplicate
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    try:
        if args:  # files given: git is not read, so the feel-fix check does not run
            files, feel = args, []
        else:
            files, moved = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, moved)
            rel = notes_file(ROOT)
            if rel is not None:  # only rows the lane adds fail; --list names the duplicates main holds
                dup = lane_duplicate_slugs(notes_text(ROOT), base_notes_text(ROOT, rel))
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        report_duplicates(dup)
        return 1 if os.environ.get("CI") or dup else 0  # CI exit code is a verdict: unknown is red there
    bad = too_long(files, dirs)
    for f in bad:
        print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
    for f, how in feel:
        print("check_record_slugs: FAIL: feel-fix debt %s with no device check: %s"
              % ("deleted" if how == "deleted" else "lost its Feel line", f))
    report_duplicates(dup)
    return 1 if bad or feel or dup else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
