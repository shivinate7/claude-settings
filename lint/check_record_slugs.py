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

Also fails on the Seen field (decision notes-sightings-expiry, a note counts its sightings and expires). A note's line
may end with `Seen: YYYY-MM-DD xN`. An added note file needs a valid field: a calendar date no later than today and no
more than SEEN_EXPIRY_DAYS old, N of 1 or more. N of 2 or more is refused: the note is a debt, so move it to a debt file
and delete the note file. An edited or renamed note file keeps the count its merge base copy held and may not drop the
field that copy had; its date is not judged. A debt file's `Seen:` line (column one, or after `- `), when present, must be a
calendar date no later than today with N of 1 or more, at any age. Today is FIXED_TODAY (ISO) when set, else the clock.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git, so only the slug length of a note file is read
    python3 lint/check_record_slugs.py --next-debt
        # the slug of the open debt to fix next: highest Seen count, then oldest Seen date, then slug
    python3 lint/check_record_slugs.py --debt-flow START END
        # the debt files opened and closed from the parent of START to END
        # (both read the git repo of the current directory, never the repo that holds the script)

The functions take a repo root, so lint/compliance_probes.py reads a child's records with them.
"""
import collections
import datetime
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import git_reads  # noqa: E402  the one home of the shallow probe (hooks/git_reads.py)
import local_time  # noqa: E402  the one home of the Central clock (hooks/local_time.py)
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)
import _guard_sections  # noqa: E402  the one home of the guard test's section header and faults
import rule_audit  # noqa: E402  section_dir(): the folder hooks/test_guard.py's SECTION_DIR names

MAX = 32
ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


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


def git_text(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def changes(root, base="origin/main", head="HEAD", renames=True, direct=False):
    """(added, moved) files of `root` from the merge base of `base` and `head` to `head` (with `direct`, from `base`
    itself, the net change of the two), from one process. `moved` holds
    (status, old, new) for each delete, modify and rename; a rename names two paths. The rename flag is explicit (-M, or
    --no-renames for the debt flow, where a rename is a delete and an add), so diff.renames in a config never moves the
    verdict. Raises Unknown when git cannot say."""
    span = [base, head] if direct else [f"{base}...{head}"]
    names = git_names(root, "diff", "--name-status", "-z", "-M" if renames else "--no-renames", *span)
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


def debt_dirs(root):
    """The debt folders of `root`, the one home of the list debt_file tests against: the repo's own when legacy-repos
    keeps them, else the layout's candidates."""
    kept = layout.unmoved(root).get("debts")
    return (kept,) if kept else layout.candidates(root, "debts")


def debt_file(root):
    """A test of a path: is it a debt file of `root`? The folders are layout.candidates: the first one that exists, then the layout's own.
    A repo that legacy-repos keeps its debts elsewhere has that one folder: the layout's own is not where its debts are.
    The folder's README and notes file sit beside the debts but are not debts: never checked, never shown."""
    dirs = tuple(p + "/" for p in debt_dirs(root))
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


# The note form, as a refusal clause: the guard's write-time log (hooks/guard.py note_form_hit) reads it from here, and
# the log cuts a long match, so it stays short. %s: the note folder with its slash. The first agent rule below builds on it.
NEW_NOTE_REFUSAL = "a new or edited note is its own file, %s<slug>.md, as `- <slug>: <text>`"
# The note rules an agent must follow, one list for the refusal below and the SubagentStart brief (hooks/agent_brief.py
# imports it). {folder} is the note folder with its slash, {old} the old notes file; layout.fill_note_paths fills both.
# The first entry holds the note form, and the refusal for a bad new note prints it.
AGENT_FORM_RULES = (
    NEW_NOTE_REFUSAL[0].upper() + NEW_NOTE_REFUSAL[1:].replace("%s", "{folder}")
    + ". The slug is the file name, 32 characters or fewer, and not digits only.",
    "The old notes file {old} takes deletes only: add no line to it and edit none.",
)
NOTE_LINE = re.compile(r"^- ([a-z0-9-]+): +\S")  # the one line a note file holds: `- <slug>: <text>`, text not empty
DIGITS = re.compile(r"[0-9]+")  # a digits-only slug reads as an old `note:<digits>` ref (hooks/feedback_guard.py)
NOTE_README = "README.md"  # the note folder's own description: not a note
CLIP = 60  # characters of a refused line that a message shows


note_dir = layout.note_dir  # the one home is lint/layout.py; kept here for the callers that read it from this check


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


SEEN_EXPIRY_DAYS = 30  # a note whose last sighting is older than this many days expires; a new note's Seen is no older
SEEN_MARK = re.compile(r"(?<![\w-])Seen:[ \t]*")
SEEN_BODY = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}) x([0-9]+)(?![\w])")
DEBT_SEEN_LINE = re.compile(r"^(?:- )?Seen:")


def today():
    """Today's date in US Central (hooks/local_time.py, the one home of the Central clock; decision local-time-central).
    FIXED_TODAY (an ISO date) replaces the clock, so a suite pins it. Raises ValueError on a bad value."""
    pinned = os.environ.get("FIXED_TODAY")
    return datetime.date.fromisoformat(pinned) if pinned else local_time.central_parts(local_time.clock())[0].date()


def parse_seen(text):
    """(date, count) of the last `Seen: YYYY-MM-DD xN` on `text`, or None when there is none or it is malformed: a date
    that is no calendar day, a count of 0, or no count. A malformed field is told from a missing one by SEEN_MARK.
    The text is read as text, never as code."""
    marks = list(SEEN_MARK.finditer(text))
    m = SEEN_BODY.match(text, marks[-1].end()) if marks else None
    if not m:
        return None
    try:
        date = datetime.date.fromisoformat(m.group(1))
    except ValueError:
        return None
    count = int(m.group(2))
    return (date, count) if count >= 1 else None


def seen_problem(text, now, added=True, floor=0, kept=False):
    """Why the note text `text` fails the Seen rule, else ''. An added note needs a valid field whose date is no older
    than SEEN_EXPIRY_DAYS. An edited one needs none, unless its base copy had one (`kept`): the edit may not drop it. A
    field it carries must be valid (the age is not judged, so an old note is never red for being old). Either way the
    date is not in the future, N is under 2 (a second sighting makes the note a debt), and N is not below `floor`, the
    count the merge base held."""
    if not SEEN_MARK.search(text):
        if kept:
            return "drops its Seen field (its copy at the merge base had one)"
        return "has no Seen: YYYY-MM-DD xN (a note counts its sightings)" if added else ""
    seen = parse_seen(text)
    if seen is None:
        return "has a Seen field that is not Seen: YYYY-MM-DD xN (a calendar date, N of 1 or more)"
    date, count = seen
    if date > now:
        return "has a Seen date (%s) in the future" % date
    if added and date < now - datetime.timedelta(days=SEEN_EXPIRY_DAYS):
        return "has a Seen date (%s) more than %d days old" % (date, SEEN_EXPIRY_DAYS)
    if count < floor:
        return "lowers its sightings from x%d to x%d" % (floor, count)
    if count >= 2:
        return "has %d sightings, so it is a debt: move it to a debt file, carry its Seen line, and delete the note file" % count
    return ""


def note_text(lines):
    """The text of a note file: its non-blank lines joined, so one read serves the one-line form and a malformed copy."""
    return " ".join(l for l in lines if l.strip())


def note_seen_failures(root, now, files, moved, folder, skip=()):
    """[(path, why)] for each note file the branch adds, edits or renames that fails the Seen rule, in path order. An added
    file is judged alone. An edited or renamed file also reads its merge base copy, for the count floor and the kept field.
    A deleted file passes. A file in `skip` already failed on its form. Raises Unknown when git cannot show a file."""
    out, base = [], None
    adds = [(f, None) for f in note_files(files, folder)]
    edits = [(new, old) for status, old, new in moved if status in "MR" and note_files([new], folder)]
    for path, old in sorted(adds + edits):
        if path in skip:
            continue
        held = None
        if old is not None:
            base = base or merge_base(root)
            held = note_text(show(root, base, old))
        floor = (parse_seen(held) or (None, 0))[1] if held else 0
        kept = bool(held and SEEN_MARK.search(held))
        why = seen_problem(note_text(show(root, "HEAD", path)), now, added=old is None, floor=floor, kept=kept)
        if why:
            out.append((path, why))
    return out


def debt_seen_problem(lines, now):
    """Why the Seen lines of a debt file fail, else ''. A line that starts `Seen:` at column one, or after one leading
    `- `, must be a calendar date no later than `now` and N of 1 or more. There is no age limit. No Seen line is fine."""
    for line in lines:
        if DEBT_SEEN_LINE.match(line):
            seen = parse_seen(line)
            if seen is None:
                return "has a Seen line that is not Seen: YYYY-MM-DD xN (a calendar date, N of 1 or more)"
            if seen[0] > now:
                return "has a Seen date (%s) in the future" % seen[0]
    return ""


def debt_seen_failures(root, now, files, moved):
    """[(path, why)] for each debt file the branch adds, edits or renames in whose Seen line is malformed or in the
    future: one show each. Raises Unknown when git cannot show a file."""
    debt = debt_file(root)
    paths = [f for f in files if debt(f)] + [new for status, _old, new in moved if status in "MR" and debt(new)]
    return [(path, why) for path in dict.fromkeys(paths) for why in [debt_seen_problem(show(root, "HEAD", path), now)] if why]


def open_debts(root):
    """[(slug, count, date)] for each debt file in the debt folders of the checkout `root`, from one listing of each
    folder and one read of each debt. The count and date come from the last valid Seen line (`Seen:` at column one,
    or after `- `); a debt with no valid Seen line counts as 1 with no date."""
    debt = debt_file(root)
    found = []
    for folder in dict.fromkeys(debt_dirs(root)):
        base = os.path.join(root, *folder.split("/"))
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not debt(folder + "/" + name):
                continue
            with open(os.path.join(base, name), encoding="utf-8", errors="replace") as handle:
                seen = [parse_seen(l) for l in handle.read().splitlines() if DEBT_SEEN_LINE.match(l)]
            date, count = (seen[-1] if seen and seen[-1] else (None, 1))
            found.append((name[:-3], count, date))
    return found


def next_debt(root):
    """The slug of the open debt to fix next, or None when there is none: the highest Seen count, then the oldest Seen
    date (a debt with no date after the dated ones), then the slug."""
    ranked = sorted(open_debts(root), key=lambda d: (-d[1], d[2] is None, d[2] or datetime.date.max, d[0]))
    return ranked[0][0] if ranked else None


def debt_flow(root, start, end):
    """(opened slugs, closed slugs): the debt files added and deleted from the parent of `start` (the empty tree when
    `start` is a root commit of a full clone) to `end`, so `start` itself counts. The count is net: a debt that `start` adds and a later
    commit deletes is in neither list. One git diff with renames off, one rev-parse that START is a commit, one for its
    parent, and a hash-object only when it has none. The folder's README and notes file are no debts. Raises Unknown
    when git cannot say, and when `start` names no commit (never read as a root commit)."""
    def run(*args, **kw):
        return _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace", **kw)
    if run("rev-parse", "--verify", "--quiet", start + "^{commit}").returncode:
        raise Unknown("%s names no commit" % start)
    parent = run("rev-parse", "--verify", "--quiet", start + "^")
    if parent.returncode:
        if git_reads.is_shallow(root) is not False:  # a shallow boundary commit has no parent: its window is unknown
            raise Unknown("%s has no parent in a clone that may be shallow" % start)
        parent = run("hash-object", "-t", "tree", "--stdin", input="")
        if parent.returncode:
            raise Unknown("git hash-object failed: %s" % parent.stderr.strip())
    added_files, moved = changes(root, parent.stdout.strip(), end, renames=False, direct=True)
    debt = debt_file(root)
    return (sorted(os.path.basename(f)[:-3] for f in added_files if debt(f)),
            sorted(os.path.basename(old)[:-3] for status, old, _new in moved if status == "D" and debt(old)))


def cwd_root():
    """The top of the git repo of the current directory, never the repo that holds this script. Raises Unknown outside
    a repo or when git cannot run."""
    return os.path.normpath(git_text(os.getcwd(), "rev-parse", "--show-toplevel").strip())


def report_command(args):
    """The exit code of `--next-debt` or `--debt-flow START END` when `args` is one of them, else None. Both read the
    repo of the current directory, so the installed copy under ~/.claude reads the repo a session works in; outside any
    repo they print UNKNOWN and exit 1."""
    next_flag = args[:1] == ["--next-debt"] and len(args) == 1
    flow_flag = args[:1] == ["--debt-flow"] and len(args) == 3 and not any(a.startswith("-") for a in args[1:])
    if not (next_flag or flow_flag):
        return None
    try:
        root = cwd_root()
    except (Unknown, OSError) as err:
        print("check_record_slugs: UNKNOWN, no git repo at the current directory (%s)" % err)
        return 1
    try:
        if next_flag:
            slug = next_debt(root)
            if slug is None:
                print("check_record_slugs: no open debt", file=sys.stderr)
            else:
                print(slug)
            return 0
        opened, closed = debt_flow(root, args[1], args[2])
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except Unknown as err:  # a pace number that could not be read is unknown, never 0
        print("check_record_slugs: UNKNOWN, " + str(err))
        return 1
    print("debts opened %d, closed %d" % (len(opened), len(closed)))
    for slug in opened:
        print("+ " + slug)
    for slug in closed:
        print("- " + slug)
    return 0


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
    done = report_command(args)
    if done is not None:
        return done
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
            files, feel, bad_form, new_lines, renamed, seen = args, [], [], [], [], []
        else:
            files, moved = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, moved)
            renamed = [new for status, old, new in moved if status == "R"]  # a note like a deleted one reads as a rename
            edited = [new for status, old, new in moved if status == "M"]
            bad_form = bad_note_form(ROOT, files + renamed + edited, folder)
            new_lines = new_note_lines(ROOT, files, moved)
            now = today()
            seen = [("a note", f, why) for f, why in
                    note_seen_failures(ROOT, now, files, moved, folder, skip={f for f, _why in bad_form})]
            seen += [("a debt file", f, why) for f, why in debt_seen_failures(ROOT, now, files, moved)]
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except ValueError as err:  # FIXED_TODAY is the only value read here that can fail to parse
        print("check_record_slugs: FAIL: FIXED_TODAY is not an ISO date (%s)" % err)
        return 1
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        # Unknown is red in CI, and red anywhere once a section fault has printed: that fault is a verdict already.
        return 1 if os.environ.get("CI") or sections else 0
    bad = too_long(files, dirs + (folder,)) + too_long(note_files(renamed, folder), (folder,))
    bad_long_note = [f for f in bad if f.startswith(folder)]
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
        print("check_record_slugs: FAIL: %s: %s" % (NEW_NOTE_REFUSAL % folder, line[:CLIP]))
    for kind, f, why in seen:
        print("check_record_slugs: FAIL: %s %s: %s" % (kind, why, f))
    if new_lines:  # the old file's rule is for a refused line in it only: any other refusal must not name that file
        for rule in AGENT_FORM_RULES:
            print("check_record_slugs: note rule: " + layout.fill_note_paths(ROOT, rule))
    elif bad_form or bad_long_note:
        print("check_record_slugs: note rule: " + layout.fill_note_paths(ROOT, AGENT_FORM_RULES[0]))
    for f, how in feel:
        print("check_record_slugs: FAIL: feel-fix debt %s with no device check: %s"
              % ("deleted" if how == "deleted" else "lost its Feel line", f))
    return 1 if bad or bad_form or new_lines or seen or feel or sections else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
