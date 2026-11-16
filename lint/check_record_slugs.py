#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in the folders lint/layout.json marks as records. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

Also fails when a debt file deleted, renamed out of the debt folder, or edited to drop its Feel line against
origin/main was a feel-fix (a line starting `**Feel.**`) with no valid device-trial line (`**Device check.**`, then
simulator or device, then an ISO time with a zone): a fix CI passes can still feel wrong on a device.

Also fails on the notes (decision notes-merge-union): the old notes file takes deletes only, so a line added to it
whose full text is not at the merge base is refused, an in-place edit included. A note is a file in the note folder
(lint/layout.json, kind notes) that holds one line `- <slug>: <text>`, its slug equal to its file name. An added note
file whose name is over 32 characters, or whose line is not in that form, is refused. The folder's README is not a
note. A deleted or edited note file passes.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git, so only the slug length of a note file is read

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


NOTE_LINE = re.compile(r"^- ([a-z0-9-]+): ")  # the one line a note file holds: `- <slug>: <text>`
NOTE_README = "README.md"  # the note folder's own description: not a note
CLIP = 60  # characters of a refused line that a message shows


def note_dir(root):
    """The note folder of `root` with its trailing slash. Raises layout.LayoutError when the layout cannot be read."""
    return layout.path(root, "notes") + "/"


def note_files(files, folder):
    """The note files among `files`: a .md file in the note folder other than its README."""
    return [f for f in files if f.startswith(folder) and f.endswith(".md") and f != folder + NOTE_README]


def merge_base(root):
    """The commit where HEAD left origin/main. Raises Unknown when git cannot say."""
    found = git_names(root, "merge-base", "origin/main", "HEAD")
    if not found:
        raise Unknown("git merge-base printed nothing")
    return found[0].strip()


def bad_note_form(root, files, folder):
    """The note files among `files` whose text at HEAD is not one `- <slug>: <text>` line with the slug equal to the
    file name. Raises Unknown when git cannot show a file."""
    out = []
    for f in note_files(files, folder):
        lines = [l for l in show(root, "HEAD", f) if l.strip()]
        slug = NOTE_LINE.match(lines[0]) if len(lines) == 1 else None
        if not slug or slug.group(1) != os.path.basename(f)[:-3]:
            out.append(f)
    return out


def new_note_lines(root, added, moved):
    """The lines the branch adds to the old notes file that its merge base does not hold, in the file's order. A
    blank line is not a note. A line moved within the file, or one of two swapped, is held already. Raises Unknown
    when git cannot show a file."""
    frozen = set(layout.candidates(root, "debt-notes"))
    touched = (frozen & set(added)) | {new for status, old, new in moved if status != "D" and new in frozen}
    out, base = [], None
    for path in sorted(touched):
        was = [old for status, old, new in moved if new == path]  # the path it had at the base: a rename names it
        if path in added or not was:
            held = set()
        else:
            base = base or merge_base(root)
            held = set(show(root, base, was[0]))
        out += [l for l in show(root, "HEAD", path) if l.strip() and l not in held]
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
        folder = note_dir(ROOT)
    except layout.LayoutError as err:  # a check that cannot read its folders is red, never green
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    try:
        if args:  # files given: git is not read, so the feel-fix and note checks do not run
            files, feel, bad_form, new_lines, renamed = args, [], [], [], []
        else:
            files, moved = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, moved)
            renamed = [new for status, old, new in moved if status == "R"]  # a note like a deleted one reads as a rename
            bad_form = bad_note_form(ROOT, files + renamed, folder)
            new_lines = new_note_lines(ROOT, files, moved)
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        return 1 if os.environ.get("CI") else 0  # CI exit code is a verdict: unknown is red there
    bad = too_long(files, dirs + (folder,)) + too_long(note_files(renamed, folder), (folder,))
    for f in bad:
        print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
    for f in bad_form:
        print("check_record_slugs: FAIL: a note file holds one line `- <slug>: <text>`, its slug the file name: %s" % f)
    for line in new_lines:
        print("check_record_slugs: FAIL: a new or edited note is its own file, %s<slug>.md, as `- <slug>: <text>`: %s"
              % (folder, line[:CLIP]))
    for f, how in feel:
        print("check_record_slugs: FAIL: feel-fix debt %s with no device check: %s"
              % ("deleted" if how == "deleted" else "lost its Feel line", f))
    return 1 if bad or bad_form or new_lines or feel else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
