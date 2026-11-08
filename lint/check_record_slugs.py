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
    Fix: already fixed on main <sha>   a hex sha of 7 to 40 digits (with or without the "none --" lead) that is a
                            commit and an ancestor of origin/main (`git merge-base --is-ancestor`)
Four more rules read the notes file (coordinator rulings 2026-11-07 13:58 and 13:59 CST):
  Ratchet: when the branch touches the notes file, the bullets with no valid Fix at HEAD may not outnumber those at
    the merge base of origin/main and HEAD. Both counts are read live; the total prints. A HEAD with none to count
    reads no base.
  Until: a `Fix: none` line the branch adds or edits carries `Until: YYYY-MM-DD`, today or later and no more than
    UNTIL_CAP_DAYS (14) from today. A step or already-fixed line needs no date. Today is FIXED_TODAY (ISO), else the clock.
  Cite: a `Fix: none` line the branch adds or edits, whose text after the reason names a commit (a 7 to 40 digit
    lowercase hex word with a digit and a letter a-f) or a cost (a number with a time, size or count unit, in any case;
    a spelled number one to ten with a time unit; Nx; linear or quadratic, with -ly or -ally; O(...)), carries check output
    after the reason: a backticked command, then a colon, comma, semicolon, dash, double dash, en or em dash, or arrow, then a verdict word
    (pass, fail, ok, red, green), which may follow a count ("12 passed"). Read with the Until check; each refused note
    prints one FAIL line with its slug.
  Upkeep: expired_notes lists the `Fix: none` lines whose Until is past, for skills/roadmap/build.py.
A notes line holds the field anywhere (the last `Fix:` on the line counts). A debt file holds it as a line that
starts `Fix:` at column one, or after one leading `- `. A notes line whose `- <slug>:` already exists at the merge
base is an edit and passes, so old lines never turn red. Only a step Fix reads origin/roadmap, and only an
already-fixed Fix reads origin/main's history. When such a read cannot run, the check prints UNKNOWN, says the read
did not run, and exits 1 (CI or not). Every diff it parses passes --src-prefix=a/ --dst-prefix=b/.
Cost, every git read of a run with no file argument, per notes file path (the layout gives one, or two):
  - one name-status diff (changes) for the whole branch;
  - one show of origin/main per moved debt file (the feel-fix check);
  - the added lines (added_note_lines, run twice: once for the Fix check, once for the Until and Cite checks): an ls-tree of
    HEAD and a diff each, and, for the Fix check only when the branch adds a bullet, a merge-base, an ls-tree of the
    merge base and a show of it;
  - one show of HEAD per added debt file;
  - two processes per distinct step named (step_exists: a rev-parse of origin/roadmap, then an ls-tree);
  - three per already-fixed sha (fixed_on_main: a rev-parse of origin/main, a rev-parse of the sha, a merge-base);
  - the ratchet, only when the branch touches the notes file: an ls-tree and a show of HEAD, and, when HEAD has a
    bullet with no valid Fix, a merge-base plus an ls-tree and a show of the merge base.
No file is written, no process is left running, no timer. commit_fixes (read by lint/report_guard.py) is one git show
of one commit, one process.

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
NONE_REASONS = ("owner decides", "needs the Mac", "needs a Windows run", "rare and harmless")
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


class FixUnread(Unknown):
    """A ref a Fix names could not be read, so the Fix is not known to be valid. Never green."""


class RoadmapUnread(FixUnread):
    """origin/roadmap could not be read, so a step Fix is not known to be valid."""


class MainUnread(FixUnread):
    """origin/main could not be read, so an already-fixed sha is not known to be on main."""


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


def patch_added(diff):
    """{path: (is_new, [added lines])} from the text of a zero-context patch made with --src-prefix=a/ --dst-prefix=b/
    (the callers pass both, so a diff.noprefix or diff.mnemonicPrefix setting never changes the header form). A line counts only inside a hunk, so a
    removed line that starts with dashes is never a file header."""
    out, path, is_new, in_hunk = {}, None, False, False
    for raw in diff.split("\n"):
        if raw.startswith("diff --git"):
            path, is_new, in_hunk = None, False, False
        elif not in_hunk and raw.startswith("--- "):
            is_new = raw == "--- /dev/null"
        elif not in_hunk and raw.startswith("+++ "):
            path = raw[6:].rstrip("\t") if raw.startswith("+++ b/") else None
            if path:
                out[path] = (is_new, [])
        elif raw.startswith("@@"):
            in_hunk = True
        elif in_hunk and path and raw.startswith("+"):
            out[path][1].append(raw[1:].rstrip("\r"))
    return out


def fixed_on_main(root, sha, ref="origin/main"):
    """True when `sha` is a commit that is an ancestor of `ref`. False for a sha that names no commit, or one that is
    not on `ref`. Raises MainUnread when `ref` or the ancestry read cannot run: that is unknown, never a missing fix."""
    def run(*args):
        return _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    try:
        if run("rev-parse", "--verify", "--quiet", ref + "^{commit}").returncode:
            raise Unknown("%s does not name a commit" % ref)
        if run("rev-parse", "--verify", "--quiet", sha + "^{commit}").returncode:
            return False
        code = run("merge-base", "--is-ancestor", sha, ref).returncode
        if code not in (0, 1):
            raise Unknown("git merge-base --is-ancestor exited %d" % code)
        return code == 0
    except (Unknown, OSError) as err:
        raise MainUnread("the %s read did not run (%s)" % (ref, err))


def added_note_lines(root, path, base="origin/main", head="HEAD", edits=False):
    """The bullet lines the branch adds to the notes file `path`, from the merge base of `base` and `head`, minus each
    line whose `- <slug>:` the merge base already holds (an edit), unless `edits`, which keeps them. A heading or a
    blank line is no note. Raises Unknown when git cannot say. A file the branch deletes or never holds adds no line,
    and its base is not read."""
    if not git_text(root, "ls-tree", "--name-only", head, "--", path).strip():
        return []
    diff = git_text(root, "-c", "core.quotepath=off", "diff", "--unified=0", "--no-color", "--no-ext-diff",
                    "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/", f"{base}...{head}", "--", path)
    notes = [l for l in patch_added(diff).get(path, (False, []))[1] if NOTE_LINE.match(l)]
    if not notes or edits:
        return notes
    mb = git_text(root, "merge-base", base, head).strip()
    held = set()
    if git_text(root, "ls-tree", "--name-only", mb, "--", path).strip():
        for old in git_text(root, "show", mb + ":" + path).splitlines():
            m = NOTE_SLUG.match(old)
            if m:
                held.add(m.group(1))
    return [l for l in notes if not (NOTE_SLUG.match(l) and NOTE_SLUG.match(l).group(1) in held)]


def _note_entry(path, line):
    m = NOTE_SLUG.match(line)
    return (path, m.group(1) if m else line.strip()[:40], [parse_fix(line)])


def _debt_entry(path, lines):
    return (path, path, [parse_fix(l) for l in lines if DEBT_FIX_LINE.match(l)])


def added_fixes(root, files, head="HEAD"):
    """[(path, label, fixes)] for each note line the branch adds and each debt file among `files` (the added files).
    `fixes` holds one parse_fix result per Fix field: one for a note line, one per Fix line of a debt file. So []
    is a debt file with no Fix line, and None marks a field in no listed form."""
    out = []
    for path in layout.candidates(root, "debt-notes"):
        out += [_note_entry(path, line) for line in added_note_lines(root, path)]
    debt = debt_file(root)
    for path in files:
        if debt(path):
            out.append(_debt_entry(path, show(root, head, path)))
    return out


def commit_fixes(root, sha):
    """The same entries as added_fixes, for what the one commit `sha` adds: each bullet it adds to the notes file and
    each debt file it creates. No merge-base grandfathering: lint/report_guard.py reads only the step Fix. One git
    process. Raises Unknown when git cannot read the commit."""
    notes = layout.candidates(root, "debt-notes")
    diff = git_text(root, "-c", "core.quotepath=off", "show", "--format=", "--unified=0", "--no-color", "--no-ext-diff",
                    "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/", "--no-renames", sha, "--", *notes, *layout.candidates(root, "debts"))
    debt, out = debt_file(root), []
    for path, (is_new, lines) in patch_added(diff).items():
        if path in notes:
            out += [_note_entry(path, l) for l in lines if NOTE_LINE.match(l)]
        elif is_new and debt(path):
            out.append(_debt_entry(path, lines))
    return out


UNTIL_CAP_DAYS = 14  # a `Fix: none` note names a date no further out than this many days from today
UNTIL = re.compile(r"(?<![\w-])Until:[ \t]*(\d{4}-\d{2}-\d{2})(?!\d)")


def today():
    """Today's date. FIXED_TODAY (an ISO date) replaces the clock, so a suite pins it. Raises ValueError on a bad value."""
    pinned = os.environ.get("FIXED_TODAY")
    return datetime.date.fromisoformat(pinned) if pinned else datetime.date.today()


def until_of(line):
    """The date of the last `Until: YYYY-MM-DD` on `line`, or None when there is none or it is not a calendar date."""
    marks = UNTIL.findall(line)
    try:
        return datetime.date.fromisoformat(marks[-1]) if marks else None
    except ValueError:
        return None


def until_problem(line, now):
    """Why the note `line` fails the Until rule, else ''. Only the `Fix: none` form needs a date: a step Fix and an
    already-fixed Fix need none."""
    fix = parse_fix(line)
    if not fix or fix[0] != "none":
        return ""
    until = until_of(line)
    if until is None:
        return "has Fix: none with no Until: YYYY-MM-DD"
    if until < now:
        return "has an Until date (%s) that is past" % until
    if until > now + datetime.timedelta(days=UNTIL_CAP_DAYS):
        return "has an Until date (%s) more than %d days from today" % (until, UNTIL_CAP_DAYS)
    return ""


# A `Fix: none` reason is a bare listed phrase. A commit or a cost after it is a claim about a fix or a cost that nobody
# re-reads, so it needs check output beside it.
COMMIT = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
TIME_UNITS = ("ms", "milliseconds?", "s", "secs?", "seconds?", "mins?", "minutes?", "hrs?", "hours?", "days?")
SIZE_UNITS = ("lines?", "chars?", "characters?", "bytes?", "[kmg]i?b")
COUNT_UNITS = ("queries", "times", "calls")
SPELLED = "one|two|three|four|five|six|seven|eight|nine|ten"
# The "," in the lookbehind keeps a start inside a run of "1," from retrying, so the scan stays linear. "a second" is not
# a cost: only a spelled number then a time unit is, and "linearizable" is no "linear".
COST = re.compile(
    r"(?<![\w.,])\d[\d,]*(?:\.\d+)?(?:[ \t-]?(?:" + "|".join(TIME_UNITS + SIZE_UNITS + COUNT_UNITS) + r")|x)(?!\w)"
    + r"|(?<!\w)(?:" + SPELLED + r")[ \t]+(?:" + "|".join(TIME_UNITS) + r")(?!\w)"
    + r"|(?<!\w)(?:quadratic(?:ally)?|linear(?:ly)?)(?!\w)|(?<!\w)(?-i:O)\(", re.I)
CHECK_OUTPUT = re.compile(r"`[^`]+`[ \t]*(?:->|=>|--|[:,;\u2013\u2014\u2192-])?[ \t]*(?:\d+[ \t]+)?(?:pass|passed|fail|failed|ok|red|green)(?!\w)",
                          re.I)


def cite_problem(line):
    """Why the note `line` fails the cite rule, else ''. A `Fix: none` note whose text after the reason names a commit or
    a cost needs check output (a backticked command, then a verdict word). The gap text before the Fix is not read."""
    marks = list(FIX_MARK.finditer(line))
    fix = parse_fix(line)
    if not fix or fix[0] != "none":
        return ""
    rest = line[FIX_BODY.match(line, marks[-1].end()).end():]
    named = "a commit" if COMMIT.search(rest) else "a cost" if COST.search(rest) else ""
    if not named or CHECK_OUTPUT.search(rest):
        return ""
    return "has Fix: none naming %s with no check output" % named


def until_failures(root, now):
    """[(path, label, why)] for each line the branch adds or edits in the notes file that fails the Until rule or the
    cite rule. A line that fails both lists the Until reason."""
    bad = []
    for path in layout.candidates(root, "debt-notes"):
        for line in added_note_lines(root, path, edits=True):
            why = until_problem(line, now) or cite_problem(line)
            if why:
                bad.append((path, _note_entry(path, line)[1], why))
    return bad


def expired_notes(root, now):
    """[(path, slug, until)] for each bullet of the notes file in the checkout `root` whose Fix is none and whose Until
    date is before `now`, in file order. A note with no readable date is not listed: only the added or edited
    lines are held to the rule. Raises layout.LayoutError when the layout cannot be read."""
    out = []
    for path in layout.candidates(root, "debt-notes"):
        full = os.path.join(root, *path.split("/"))
        if not os.path.isfile(full):
            continue
        with open(full, encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines():
                fix, until = parse_fix(line), until_of(line)
                if NOTE_LINE.match(line) and fix and fix[0] == "none" and until and until < now:
                    out.append((path, _note_entry(path, line)[1], until))
    return out


def unfixed_notes(root, ref):
    """How many bullets of the notes file at `ref` have no valid Fix. A ref with no notes file holds none."""
    count = 0
    for path in layout.candidates(root, "debt-notes"):
        if git_text(root, "ls-tree", "--name-only", ref, "--", path).strip():
            count += sum(1 for l in git_text(root, "show", ref + ":" + path).splitlines()
                         if NOTE_LINE.match(l) and parse_fix(l) is None)
    return count


def notes_ratchet(root, files, moved, base="origin/main"):
    """(path, head count, base count) when the branch touches the notes file, else None. The count of bullets with no
    valid Fix at HEAD may not exceed the count at the merge base of `base` and HEAD, so a branch forked before main
    lowered its count is not blamed for it. Both are read live, with no stored baseline. A HEAD with none to count
    reads no base. Raises Unknown when git cannot say."""
    notes = layout.candidates(root, "debt-notes")
    touched = set(files) | {p for _status, old, new in moved for p in (old, new)}
    if not touched & set(notes):
        return None
    head = unfixed_notes(root, "HEAD")
    if not head:
        return notes[0], 0, 0
    return notes[0], head, unfixed_notes(root, git_text(root, "merge-base", base, "HEAD").strip())


def fix_failures(root, entries):
    """[(path, label, why)] for each entry of added_fixes with no valid Fix. Raises FixUnread when a step
    cannot be read, or origin/main when an already-fixed sha needs it."""
    bad = []
    for path, label, fixes in entries:
        if not fixes or None in fixes:
            bad.append((path, label, "names no valid Fix. Use step:<slug> on %s; or none -- <reason> with the reason one "
                        "of (%s) and Until: YYYY-MM-DD no more than %d days from today; or already fixed on main <sha>"
                        % (ROADMAP, ", ".join(NONE_REASONS), UNTIL_CAP_DAYS)))
            continue
        for kind, value in fixes:
            if kind == "step" and not step_exists(root, value):
                bad.append((path, label, "names step:%s, which is not on %s" % (value, ROADMAP)))
            elif kind == "fixed" and not fixed_on_main(root, value):
                bad.append((path, label, "names commit %s, which is not an ancestor of origin/main" % value))
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
            files, feel, entries, dated, ratchet = args, [], [], [], None
        else:
            files, moved = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, moved)
            entries = added_fixes(ROOT, files)
            dated = until_failures(ROOT, today())
            ratchet = notes_ratchet(ROOT, files, moved)
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except ValueError as err:  # FIXED_TODAY is the only value read here that can fail to parse
        print("check_record_slugs: FAIL: FIXED_TODAY is not an ISO date (%s)" % err)
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
    except FixUnread as err:  # a step or sha Fix cannot be judged: red on any machine, never green
        print("check_record_slugs: UNKNOWN, %s, so no Fix was checked" % err)
        return 1
    for path, label, why in unfixed:
        print('check_record_slugs: FAIL: "%s" %s: %s' % (label, why, path))
    for path, label, why in dated:
        print('check_record_slugs: FAIL: "%s" %s: %s' % (label, why, path))
    grown = False
    if ratchet:
        path, head, base = ratchet
        grown = head > base
        print("check_record_slugs: %s: notes with no valid Fix: %d now, %d at the merge base%s: %s"
              % ("FAIL" if grown else "ok", head, base, " (the count may not grow)" if grown else "", path))
    return 1 if bad or feel or unfixed or dated or grown else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
