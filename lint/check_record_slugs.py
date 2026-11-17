#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in the folders lint/layout.json marks as records. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

Also fails, over the whole tree and not the diff, when two guard test section files (tests/guard/) share a header number,
or a file's name number disagrees with its `# section <n>` header: git merges two branches' new section files clean, and
hooks/test_guard.py then stops on the pair. The header read comes from lint/_guard_sections.py, the folder from lint/rule_audit.py section_dir().

Also fails when a debt file deleted, renamed out of the debt folder, or edited to drop its Feel line against
origin/main was a feel-fix (a line starting `**Feel.**`) with no valid device-trial line (`**Device check.**`, then
simulator or device, then an ISO time with a zone): a fix CI passes can still feel wrong on a device.

Also fails on the notes (decision notes-merge-union): the old notes file takes deletes only, so a line added to it
whose count at HEAD is over its count at the merge base is refused, an in-place edit included. A note is a file in the
note folder (lint/layout.json, kind notes) that holds one line `- <slug>: <text>`, its slug equal to its file name and
not digits only (an old `note:<digits>` ref reads that way). An added note file whose name is over 32 characters, and an
added, renamed or edited note file whose line is not in that form, or that sits in a subfolder of the note folder (a
note is flat), is refused. The folder's README is not a note. A
deleted note file passes.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git, so only the slug length of a note file is read

The functions take a repo root, so lint/compliance_probes.py reads a child's records with them.
"""
import collections
import datetime
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)
import _guard_sections  # noqa: E402  the one home of the guard test's section header and faults
import rule_audit  # noqa: E402  section_dir(): the folder hooks/test_guard.py's SECTION_DIR names

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
    """The lines of `path` at `ref`, split on "\n" only: splitlines() also splits on U+2028, formfeed and lone CR, which
    would turn one line of a note into two. A trailing CR (a CRLF file) is not part of the line."""
    r = _nowindow.run(["git", "show", ref + ":" + path], cwd=root, capture_output=True)  # bytes: text mode turns CR into LF
    if r.returncode:
        raise Unknown("git show failed: %s" % r.stderr.decode("utf-8", "replace").strip())
    lines = r.stdout.decode("utf-8", "replace").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [l[:-1] if l.endswith("\r") else l for l in lines]


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


NOTE_LINE = re.compile(r"^- ([a-z0-9-]+): +\S")  # the one line a note file holds: `- <slug>: <text>`, text not empty
DIGITS = re.compile(r"[0-9]+")  # a digits-only slug reads as an old `note:<digits>` ref (hooks/feedback_guard.py)
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
    """[(file, why)] for the note files among `files` that sit in a folder of the note folder, whose text at HEAD is not
    one `- <slug>: <text>` line with the slug equal to the file name, or whose slug is digits only. Raises Unknown when
    git cannot show a file."""
    out = []
    for f in note_files(files, folder):
        if "/" in f[len(folder):]:
            out.append((f, "nested"))
            continue
        lines = [l for l in show(root, "HEAD", f) if l.strip()]
        slug = NOTE_LINE.match(lines[0]) if len(lines) == 1 else None
        name = os.path.basename(f)[:-3]
        if not slug or slug.group(1) != name:
            out.append((f, "form"))
        elif DIGITS.fullmatch(name):
            out.append((f, "digits"))
    return out


def new_note_lines(root, added, moved):
    """The lines the branch adds to the old notes file, in the file's order: a line whose count at HEAD is over its count
    at the merge base. A blank line is not a note. A moved line, or one of two swapped, is held already. Raises Unknown
    when git cannot show a file."""
    frozen = set(layout.candidates(root, "debt-notes"))
    touched = (frozen & set(added)) | {new for status, old, new in moved if status != "D" and new in frozen}
    out, base = [], None
    for path in sorted(touched):
        was = [old for status, old, new in moved if new == path]  # the path it had at the base: a rename names it
        if path in added or not was:
            held = collections.Counter()
        else:
            base = base or merge_base(root)
            held = collections.Counter(show(root, base, was[0]))
        seen = collections.Counter()
        for l in show(root, "HEAD", path):
            if not l.strip():
                continue
            seen[l] += 1
            if seen[l] > held[l]:
                out.append(l)
    return out


def tracked(root):
    return git_names(root, "ls-files", "-z")


def too_long(files, dirs):
    """The record files among `files` whose slug is over MAX characters. Same normpath as
    lint/check_ruling_kind.py, so ./decisions/x.md is judged like decisions/x.md."""
    return [f for f in files if os.path.normpath(f).replace("\\", "/").startswith(dirs)
            and f.endswith(".md") and len(os.path.basename(f.replace("\\", "/"))[:-3]) > MAX]


def section_faults(root):
    """[(path, message)] for each guard test section file of `root` that has a bad header, a name that disagrees with its
    header, or a header number another file holds. Paths are relative to `root`, with forward slashes."""
    rel = rule_audit.section_dir(root)
    if not rel:
        runner = "hooks/test_guard.py"
        if os.path.isfile(os.path.join(root, *runner.split("/"))):  # a runner whose folder cannot be read is red, never green
            return [(runner, "names no SECTION_DIR folder this check can read")]
        return []  # a root with no runner holds no section set
    folder = os.path.join(root, *rel.split("/"))
    return [(os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/"), message)
            for name, message in _guard_sections.faults(_guard_sections.read(folder))]


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
    sections = section_faults(ROOT)  # the tree, not the diff or the file arguments: a git read that fails does not hide it
    for f, message in sections:
        print("check_record_slugs: FAIL: guard test section file %s: %s" % (message, f))
    try:
        if args:  # files given: git is not read, so the feel-fix and note checks do not run
            files, feel, bad_form, new_lines, renamed = args, [], [], [], []
        else:
            files, moved = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, moved)
            renamed = [new for status, old, new in moved if status == "R"]  # a note like a deleted one reads as a rename
            edited = [new for status, old, new in moved if status == "M"]
            bad_form = bad_note_form(ROOT, files + renamed + edited, folder)
            new_lines = new_note_lines(ROOT, files, moved)
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        # Unknown is red in CI, and red anywhere once a section fault has printed: that fault is a verdict already.
        return 1 if os.environ.get("CI") or sections else 0
    bad = too_long(files, dirs + (folder,)) + too_long(note_files(renamed, folder), (folder,))
    for f in bad:
        print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
    for f, why in bad_form:
        if why == "nested":
            print("check_record_slugs: FAIL: a note file sits directly in %s, not in a folder of it: %s" % (folder, f))
        elif why == "digits":
            print("check_record_slugs: FAIL: a note slug is more than digits, so it is not read as an old note number: %s"
                  % f)
        else:
            print("check_record_slugs: FAIL: a note file holds one line `- <slug>: <text>`, its slug the file name: %s"
                  % f)
    for line in new_lines:
        print("check_record_slugs: FAIL: a new or edited note is its own file, %s<slug>.md, as `- <slug>: <text>`: %s"
              % (folder, line[:CLIP]))
    for f, how in feel:
        print("check_record_slugs: FAIL: feel-fix debt %s with no device check: %s"
              % ("deleted" if how == "deleted" else "lost its Feel line", f))
    return 1 if bad or bad_form or new_lines or feel or sections else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
