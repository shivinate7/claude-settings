#!/usr/bin/env python3
"""The one reader of the ruled store: the owner's rulings that main has not yet taken in. Standard library only.

    python3 lint/ruled_store.py --session-line REPO   the lines the session-start hook prints, or nothing
    python3 lint/ruled_store.py list REPO             every open entry in full
    python3 lint/ruled_store.py check REPO            exit 1 on a store problem (check_store), exit 3 and a line that
                                                      starts "unknown" when the store cannot be read

The store is the folder roadmap/rulings on origin/roadmap of REPO, one JSON file per ruling. An entry holds `id`,
`at` (ISO 8601 with a zone), `ruling`, `source`, `status` ("open" or "closed"), `supersedes` (a list of
{"kind", "ref"}) or `supersedes_none` (the reason it supersedes nothing; a reason that starts with "unread" means
triage has not read it yet), and optionally `quote` (the owner's own words), `step` (the roadmap step that lands the
ruling) and `lands_in` ({"path", "contains"}).

An entry is open until its ruling is on main. It closes when `status` is "closed", or when the text of
`lands_in.contains` is found, whitespace-normalised, in the blob of `lands_in.path` on origin/main. Triage writes
the entries, and the restart plan cites them. The decision record is ruled-store-one-home.

ENTRIES_LIFT_GUARDS is the one switch. True (decision ruled-store-one-home) lets an entry govern the guard rules it
names in its `supersedes` (kind "guard-rule"). ruling_for_guard(rule id, entries) returns the newest entry that governs
that rule, or None. An entry governs only when its status is "open", check_entry flags nothing in it, and it is not
unchecked. guard_ruling_line(entry) words the note a guard prints when it lets the ruled act through. False makes
every entry text only. A guard rule id is the first token of the ref, with a trailing ":" cut, in kebab-case
(guard_rule_id); a ref with no such token names no rule.

An entry whose store file was added or changed in a commit on STORE_REF made at or after CUTOFF_AT must name what it
supersedes when the kind is "ruling": the first token of the ref is the exact `id` of an entry in the store whose `at` is
strictly earlier than its own (check_store). A file last changed before CUTOFF_AT is not checked. `check` reads that
scope with one `git log --diff-merges=first-parent` over the store folder, filtered by commit date here: a merge counts
only what it adds to the store ref's main line. A pure rename (same text, new name) is not a change; a rename with edits is. A failed log, or a shallow repo (its log ends early), reads unknown,
like an unreadable store; `check` then names the cause in its unknown line.

Cost: this module keeps no process and no timer and writes no file. ruled_entries starts two read-only git processes
(one ls-tree, one cat-file --batch). open_entries starts one more cat-file --batch, and only when an open entry names
`lands_in`. check_store adds, only when the store has entries, one rev-parse (the shallow test) and one git log (it detects renames, in the same process), and,
only when an open entry names a `step`, one more cat-file --batch; its listing, when it fails, costs one more
rev-parse, to tell a missing ref from a lost commit or tree. A missing ref, a missing folder or a failed git start
gives [], never an error.

An unchecked entry (`supersedes_none` starts with "unread": triage has not read what it supersedes) informs a session
and is marked "(unchecked, not law)" in the past-ruling search. It never governs a guard: ruling_for_guard and
lifted_guards skip it, even when it lists a guard ref.
"""
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# A caller that already put hooks/ on the path (report_guard puts a stamped guard.d copy first) keeps its order: this
# module adds hooks/ last, and only when _nowindow is not importable yet, as a script run from lint/ needs.
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:
    sys.path.append(os.path.join(HERE, "..", "hooks"))
    import _nowindow  # noqa: E402

ENTRIES_LIFT_GUARDS = True  # an open entry governs the guard rules it names
STORE_REF = "origin/roadmap"
MAIN_REF = "origin/main"
STORE_DIR = "roadmap/rulings/"
STEP_DIR = "roadmap/data/steps/"  # one JSON file per roadmap step on STORE_REF; its `status` is "done" once landed
STEP_SLUG = re.compile(r"^[\w.-]+$")
RULE_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
STATUSES = ("open", "closed")
REQUIRED = ("id", "at", "ruling", "source")
SESSION_ENTRIES = 5  # entry lines after the header; with the header and the command line, at most 7 of the 8 allowed
RULING_CUT = 100
REF_CUT = 80
GIT_TIMEOUT = 30
# A git start must read REPO, never an outer repo that a hook or CI step points at through these.
STRIPPED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE")
_FAR_PAST = datetime.min.replace(tzinfo=timezone.utc)
# A store file last changed in a commit before this instant keeps the refs it was written with; the ruling-ref rule
# starts here (owner grant, waiting-page item 877 option a; scope by commit, item 881 b).
CUTOFF_AT = datetime(2026, 11, 15, 11, 33, tzinfo=timezone(timedelta(hours=-6)))
EXIT_UNKNOWN = 3  # the store could not be read: neither clean nor flawed
# The cause `check` names in its unknown line, one per way the store or its history fails to read.
CAUSE_NO_GIT = "git cannot start or timed out"
CAUSE_LOST_TREE = "the store ref resolves but its commit or rulings tree is lost"
CAUSE_LOST_BLOB = "the object of a ruling file is lost"
CAUSE_NO_BLOBS = "git could not read the ruling files"
CAUSE_SHALLOW = "the repo is shallow, so the store's history ends early"
CAUSE_NO_SHALLOW_TEST = "git could not say whether the repo is shallow"
CAUSE_NO_LOG = "git log of the store failed (a lost commit in its history, or git older than 2.31)"
CAUSE_ERROR = "an error while reading the store"


def _git(repo_dir, args, text=None):
    """(exit code, stdout bytes) of one git start in repo_dir. The code is None when git cannot start or times out."""
    env = {key: value for key, value in os.environ.items() if key not in STRIPPED}
    try:
        done = _nowindow.run(["git", "-C", repo_dir] + list(args), input=text, capture_output=True, env=env,
                             timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, b""
    return done.returncode, done.stdout


def _batch_blobs(repo_dir, specs, missing=None):
    """{spec: bytes} for each `ref:path` spec that names a blob, from one cat-file --batch. A missing spec is absent
    from the answer. Returns {} when git fails. A caller that must tell a lost object from a path that is not there
    passes a list as `missing`: it gets each spec that cat-file answered "missing" or did not answer at all."""
    if not specs:
        return {}
    code, out = _git(repo_dir, ["cat-file", "--batch"], ("\n".join(specs) + "\n").encode("utf-8"))
    found, pos = {}, 0
    if code != 0:
        return found
    for index, spec in enumerate(specs):
        end = out.find(b"\n", pos)
        if end < 0:
            if missing is not None:
                missing.extend(specs[index:])  # a cut-short answer reads none of the specs after it
            break
        head = out[pos:end].split()
        pos = end + 1
        if len(head) == 3 and head[1] == b"blob" and head[2].isdigit():
            size = int(head[2])
            found[spec] = out[pos:pos + size]
            pos += size + 1  # the blob is followed by one newline
        elif missing is not None and head[-1:] == [b"missing"]:
            missing.append(spec)
    return found


def parse_at(value):
    """The aware datetime of an ISO 8601 `at`, or None when it is unreadable or has no zone."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def entry_instant(entry):
    return parse_at(entry.get("at")) or _FAR_PAST


def _load(repo_dir, ref, strict=False):
    """(entries, state, bad, files, cause) of the store at `ref` in repo_dir. `bad` lists a problem line for each store
    file that is not a JSON object; `files` is each entry's path in the store, in the order of `entries`; `cause` says
    why the state is "unreadable", else "". `strict` is the `check` read. It makes a listing that fails on a ref that
    resolves read "unreadable" (a lost commit or tree), at the cost of one rev-parse, and a lost blob of any one entry
    read "unreadable". Without it that listing reads "absent" and a lost blob is skipped while others read, so the
    session-start hook starts no extra git process and still shows the rest. See read_store for the rest."""
    try:
        code, listing = _git(repo_dir, ["ls-tree", "-z", "--name-only", ref, STORE_DIR])
        if code is None:
            return [], "unreadable", [], [], CAUSE_NO_GIT
        names = [n.decode("utf-8", "replace") for n in listing.split(b"\0") if n.endswith(b".json")]
        if code != 0:
            # The ref is read without a peel: a ref whose commit is lost still resolves, and only a ref that does not
            # resolve at all is absent.
            lost = strict and _git(repo_dir, ["rev-parse", "--verify", "--quiet", ref])[0] == 0
            return [], "unreadable" if lost else "absent", [], [], CAUSE_LOST_TREE if lost else ""
        if not names:
            return [], "absent", [], [], ""
        specs = ["%s:%s" % (ref, name) for name in names]
        missing = []
        blobs = _batch_blobs(repo_dir, specs, missing)
        if missing and (strict or not blobs):
            return [], "unreadable", [], [], CAUSE_LOST_BLOB
        if not blobs:
            return [], "unreadable", [], [], CAUSE_NO_BLOBS
        entries, bad = [], []
        for name, spec in zip(names, specs):
            if spec not in blobs:
                continue
            try:
                body = json.loads(blobs[spec].decode("utf-8"))
            except ValueError:
                bad.append("%s is not valid JSON" % name)
                continue
            if isinstance(body, dict):
                entries.append((body, name))
            else:
                bad.append("%s is not a JSON object" % name)
        entries.sort(key=lambda pair: entry_instant(pair[0]))
        return [e for e, _n in entries], "ok", bad, [n for _e, n in entries], ""
    except Exception:
        return [], "unreadable", [], [], CAUSE_ERROR


def read_store(repo_dir, ref=STORE_REF):
    """(entries, state) of the store at `ref` in repo_dir, oldest first by instant. state is "ok" (also an empty
    folder that exists), "absent" (no such ref, folder or repo) or "unreadable" (git cannot start, or fails after the
    listing worked; `check` also reads a lost commit, tree or single blob so, see _load). A file that is not a JSON
    object is skipped. Never raises."""
    return _load(repo_dir, ref)[:2]


def ruled_entries(repo_dir, ref=STORE_REF):
    """The entries of the store at `ref`, oldest first by instant; [] when the store is absent or unreadable."""
    return read_store(repo_dir, ref)[0]


def _norm(text):
    return " ".join(text.split())


def _lands(entry):
    lands = entry.get("lands_in")
    return isinstance(lands, dict) and isinstance(lands.get("path"), str) and isinstance(lands.get("contains"), str)


def open_entries(entries, repo_dir, main_ref=MAIN_REF):
    """The entries main has not taken in: not closed, and no `lands_in.contains` text, whitespace-normalised, in the
    blob at `lands_in.path` on main_ref. A path missing on main_ref leaves the entry open."""
    live = [e for e in entries if e.get("status") != "closed"]
    wanted = []
    for entry in live:
        if _lands(entry):
            spec = "%s:%s" % (main_ref, entry["lands_in"]["path"])
            if spec not in wanted:
                wanted.append(spec)
    blobs = _batch_blobs(repo_dir, wanted)
    kept = []
    for entry in live:
        if _lands(entry):
            lands = entry["lands_in"]
            needle = _norm(lands["contains"])
            blob = blobs.get("%s:%s" % (main_ref, lands["path"]))
            if needle and blob is not None and needle in _norm(blob.decode("utf-8", "replace")):
                continue
        kept.append(entry)
    return kept


def _supersedes(entry):
    items = entry.get("supersedes")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def guard_rule_id(ref):
    """The guard rule id a "guard-rule" ref names, or "": the ref's first whitespace token with a trailing ":" cut,
    when that is kebab-case. A ref may carry prose after the id. The one matcher for both lookups and check_store."""
    parts = ref.split() if isinstance(ref, str) else []
    token = parts[0].rstrip(":") if parts else ""
    return token if RULE_ID.match(token) else ""


def _governs(entry):
    """True when an entry may govern a guard: status "open", nothing in it that check_entry flags, and not unchecked."""
    return entry.get("status") == "open" and not check_entry(entry) and not is_unchecked(entry)


def _guard_ids(entry):
    return [guard_rule_id(i.get("ref")) for i in _supersedes(entry) if i.get("kind") == "guard-rule"]


def lifted_guards(entries):
    """The guard rule ids that the governing entries name (see _governs). [] while ENTRIES_LIFT_GUARDS is False."""
    if not ENTRIES_LIFT_GUARDS:
        return []
    lifted = []
    for entry in entries:
        if _governs(entry):
            lifted += [rid for rid in _guard_ids(entry) if rid and rid not in lifted]
    return lifted


def ruling_for_guard(guard_rule, entries):
    """The newest entry that governs `guard_rule` (a rule id), or None. None while ENTRIES_LIFT_GUARDS is False."""
    if not ENTRIES_LIFT_GUARDS:
        return None
    named = [e for e in entries if guard_rule and _governs(e) and guard_rule in _guard_ids(e)]
    return max(named, key=entry_instant) if named else None


def guard_ruling_line(entry):
    """The line a guard prints when an entry's ruling lets the act through."""
    return "ruled by %s (owner %s): %s" % (entry.get("id", "?"), entry.get("at", "?"),
                                          _norm(str(entry.get("ruling", "")))[:RULING_CUT])


def check_entry(entry):
    """One problem line per defect: a missing or empty required key, an `at` that is unreadable or has no zone, a
    `status` outside open and closed, and neither a listed `supersedes` nor a `supersedes_none` reason."""
    problems = []
    for key in REQUIRED:
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append("missing key %s" % key)
    if isinstance(entry.get("at"), str) and entry["at"].strip():
        try:
            moment = datetime.fromisoformat(entry["at"].strip().replace("Z", "+00:00"))
        except ValueError:
            problems.append("at is not an ISO 8601 time: %r" % entry["at"])
        else:
            if moment.tzinfo is None:
                problems.append("at has no time zone: %r" % entry["at"])
    if entry.get("status") not in STATUSES:
        problems.append("status is not open or closed: %r" % entry.get("status"))
    reason = entry.get("supersedes_none")
    if not _supersedes(entry) and not (isinstance(reason, str) and reason.strip()):
        problems.append("neither supersedes nor supersedes_none is set")
    return problems


def is_unchecked(entry):
    """True when triage has not read what the entry supersedes: its `supersedes_none` starts with "unread". Such an
    entry informs a session and never governs a guard, even if it lists a guard ref."""
    reason = entry.get("supersedes_none")
    return isinstance(reason, str) and reason.strip().lower().startswith("unread")


def supersedes_text(entry, cut=None):
    """The supersedes refs joined by "; ", each cut to `cut` characters when given; "none", or "unread" for an entry
    triage has not read, when it lists none."""
    refs = [str(item.get("ref", "")) for item in _supersedes(entry)]
    if not refs:
        return "unread" if is_unchecked(entry) else "none"
    if cut:
        refs = [r if len(r) <= cut else r[:cut] + "..." for r in refs]
    return "; ".join(refs)


def _one_line(entry, cut=RULING_CUT):
    text = _norm(str(entry.get("ruling", "")))
    return text if len(text) <= cut else text[:cut] + "..."


def session_lines(repo_dir):
    """The session-start block: [] when no entry is open, else a header, up to five entry lines (newest first) and the
    command line. Never raises."""
    try:
        opened = open_entries(ruled_entries(repo_dir), repo_dir)
        if not opened:
            return []
        newest = sorted(opened, key=entry_instant, reverse=True)
        unread = sum(1 for e in opened if is_unchecked(e))
        lines = ["rulings not on main: %d open (%d with no supersedes read yet), newest first" % (len(opened), unread)]
        for entry in newest[:SESSION_ENTRIES]:
            lines.append("  %s %s: %s | supersedes %s" % (entry.get("id", "?"), entry.get("at", "?"), _one_line(entry),
                                                          supersedes_text(entry, REF_CUT)))
        lines.append("  read them in full, from the claude-settings clone: python3 lint/ruled_store.py list %s"
                     % shlex.quote(repo_dir))
        return lines
    except Exception:
        return []


def _list(repo_dir):
    for entry in sorted(open_entries(ruled_entries(repo_dir), repo_dir), key=entry_instant, reverse=True):
        print("%s  %s" % (entry.get("id", "?"), entry.get("at", "?")))
        print("  ruling: %s" % _norm(str(entry.get("ruling", ""))))
        print("  supersedes: %s" % supersedes_text(entry))
        if entry.get("source"):
            print("  source: %s" % entry["source"])
    return 0


def _joined(ids):
    return ids[0] if len(ids) == 1 else ", ".join(ids[:-1]) + " and " + ids[-1]


def _ref_key(item):
    """What a supersedes ref names, for the shared-ref check: a guard rule id, a quoted main sentence whole (its first
    token, often a file name, names nothing alone), else the ref's first token."""
    ref = item.get("ref")
    if item.get("kind") == "guard-rule":
        return guard_rule_id(ref)
    if item.get("kind") == "main-sentence" and isinstance(ref, str):
        return _norm(ref)
    parts = ref.split() if isinstance(ref, str) else []
    return parts[0] if parts else ""


def _steps_of(entry):
    """The step slugs an entry names: its `steps` list when it has one, else its `step`."""
    listed = entry.get("steps")
    raw = listed if isinstance(listed, list) and listed else [entry.get("step")]
    return [s for s in raw if isinstance(s, str) and STEP_SLUG.match(s)]


def _changed_paths(tokens):
    """The paths a commit's `--name-status -z` tokens put in scope, as str. The tokens run status, path; a rename or
    copy (R or C) carries the old path, then the new one. A deleted file, and the new path of a pure rename or copy
    (score 100), read as nothing: no entry text changed. Any other status counts its path."""
    # git ends the format line of a commit that has names with a newline, which the first token carries.
    tokens = [t for t in tokens if t]
    if tokens:
        tokens[0] = tokens[0].removeprefix(b"\n")
    paths = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        if status[:1] in (b"R", b"C"):
            if i + 2 >= len(tokens):
                break
            if status[1:] != b"100":
                paths.append(tokens[i + 2])
            i += 3
        else:
            if i + 1 >= len(tokens):
                break
            if status[:1] != b"D":
                paths.append(tokens[i + 1])
            i += 2
    return [p.decode("utf-8", "replace") for p in paths]


def _recent_files(repo_dir):
    """(paths, cause): the set of store paths added or changed in a commit on STORE_REF made at or after CUTOFF_AT, and
    "". paths is None, and cause names why, when that cannot be read: a shallow repo (its log ends early), git that
    cannot start, or a log that exits nonzero.
    One git log walks the whole history, with renames detected: a pure rename is no change, a rename with edits is.
    A merge is diffed against its first parent only, so it counts as what it adds
    to the store ref's main line; against the other parent it would also list every file the main line changed, and
    flag an old entry. A side-branch commit is still walked and counts on its own date. The commits are filtered by
    committer date here, never by --since: git stops a --since walk at the first older commit, which hides a file
    changed on a branch whose commits are dated before the cutoff but merged after it. --diff-merges needs git 2.31;
    an older git fails the log, which reads unknown, never clean."""
    code, out = _git(repo_dir, ["rev-parse", "--is-shallow-repository"])
    if code is None:
        return None, CAUSE_NO_GIT
    if code != 0:
        return None, CAUSE_NO_SHALLOW_TEST
    if out.strip() != b"false":
        return None, CAUSE_SHALLOW
    code, out = _git(repo_dir, ["log", "--diff-merges=first-parent", "--find-renames", "--name-status", "-z",
                                "--format=%x01%ct", STORE_REF, "--", STORE_DIR])
    if code is None:
        return None, CAUSE_NO_GIT
    if code != 0:
        return None, CAUSE_NO_LOG
    cutoff = int(CUTOFF_AT.timestamp())
    recent = set()
    for record in out.split(b"\1")[1:]:
        stamp, *tokens = record.split(b"\0")
        if int(stamp) >= cutoff:
            recent.update(_changed_paths(tokens))
    return recent, ""


def _ruling_ref_problems(entries, files, recent):
    """Problem lines for each "ruling" ref, on entries whose file is in `recent`, whose first token is not the exact
    id of a store entry with an earlier `at`. A ref is judged on its id alone, so prose after the id never matters."""
    instants = {}
    for entry in entries:
        if isinstance(entry.get("id"), str):
            instants.setdefault(entry["id"], []).append(entry_instant(entry))
    problems = []
    for entry, name in zip(entries, files):
        if name not in recent:
            continue
        at = entry_instant(entry)
        rid = entry.get("id", "?")
        for item in _supersedes(entry):
            if item.get("kind") != "ruling":
                continue
            ref = item.get("ref")
            parts = ref.split() if isinstance(ref, str) else []
            if not parts:
                problems.append("%s: ruling ref is empty or not a string" % rid)
            elif parts[0] not in instants:
                problems.append("%s: ruling ref %s names no ruling in the store" % (rid, parts[0]))
            elif not any(moment < at for moment in instants[parts[0]]):
                problems.append("%s: ruling ref %s names a ruling not earlier than it" % (rid, parts[0]))
    return problems


def _check_state(repo_dir):
    """(problems, state, cause) of the store: the problem lines of check_store, the read state of read_store, and why
    the state is "unreadable" ("" otherwise)."""
    entries, state, bad, files, cause = _load(repo_dir, STORE_REF, strict=True)
    problems = list(bad)
    for entry in entries:
        rid = entry.get("id", "?")
        problems += ["%s: %s" % (rid, p) for p in check_entry(entry)]
        if any(not rule for rule in _guard_ids(entry)):
            problems.append("entry %s: guard-rule ref names no rule id" % rid)
    if entries:
        recent, log_cause = _recent_files(repo_dir)
        if recent is None:
            state, cause = "unreadable", log_cause
        else:
            problems += _ruling_ref_problems(entries, files, recent)
    opened = open_entries(entries, repo_dir)
    shared = {}
    for entry in opened:
        for item in _supersedes(entry):
            name = _ref_key(item)
            if name:
                ids = shared.setdefault((item.get("kind"), name), [])
                if entry.get("id") not in ids:
                    ids.append(entry.get("id", "?"))
    for (_kind, name), ids in shared.items():
        if len(ids) > 1:
            problems.append("entries %s both supersede %s" % (_joined(ids), name))
    stepped = [(e, _steps_of(e)) for e in opened]
    specs = sorted({"%s:%s%s.json" % (STORE_REF, STEP_DIR, slug) for _e, slugs in stepped for slug in slugs})
    blobs = _batch_blobs(repo_dir, specs)

    def is_done(slug):
        spec = "%s:%s%s.json" % (STORE_REF, STEP_DIR, slug)
        try:
            return json.loads(blobs[spec].decode("utf-8")).get("status") == "done"
        except (KeyError, ValueError, AttributeError):
            return False

    for entry, slugs in stepped:
        if slugs and all(is_done(slug) for slug in slugs):
            noun = "step %s is" % slugs[0] if len(slugs) == 1 else "steps %s are" % _joined(slugs)
            problems.append("%s done but entry %s is still open" % (noun, entry.get("id", "?")))
    return problems, state, cause


def check_store(repo_dir):
    """One problem line per defect in the store: a file that is not a JSON object; each check_entry problem (prefixed by
    the entry's id); a guard-rule ref that names no rule id; on an entry whose file was added or changed in a commit made
    at or after CUTOFF_AT, a "ruling" ref whose first token is empty, is not a string, names no entry in the store, or
    names an entry whose `at` is not strictly earlier; two or more open entries that supersede one ref of one kind; an open entry whose `step` (or, with a
    `steps` list, every listed step) is done on origin/roadmap. A step file that is missing or unreadable is not done.
    [] when the store is clean or absent, and also when it is unreadable: a caller that must tell the two apart uses
    _check_state, as _check does."""
    return _check_state(repo_dir)[0]


def _check(repo_dir):
    problems, state, cause = _check_state(repo_dir)
    for problem in problems:
        print(problem)
    if state == "unreadable":
        print("unknown: the ruled store or its history could not be read (%s), so it is neither clean nor flawed"
              % (cause or CAUSE_ERROR))
        return EXIT_UNKNOWN
    return 1 if problems else 0


def main(argv):
    try:
        if len(argv) == 2 and argv[0] == "--session-line":
            for line in session_lines(argv[1]):
                print(line)
            return 0
        if len(argv) in (1, 2) and argv[0] in ("list", "check"):
            repo = argv[1] if len(argv) == 2 else "."
            return _list(repo) if argv[0] == "list" else _check(repo)
    except Exception:
        return 0 if argv[:1] == ["--session-line"] else 2
    sys.stderr.write(__doc__.split("\n\n")[0] + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
