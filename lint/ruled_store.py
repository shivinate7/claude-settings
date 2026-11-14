#!/usr/bin/env python3
"""The one reader of the ruled store: the owner's rulings that main has not yet taken in. Standard library only.

    python3 lint/ruled_store.py --session-line REPO   the lines the session-start hook prints, or nothing
    python3 lint/ruled_store.py list REPO             every open entry in full
    python3 lint/ruled_store.py check REPO            exit 1 on a store problem (check_store)

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

Freshness (step roadmap-ref-fresh-before-verdict): a read of STORE_REF (read_store, ruled_entries, session_lines)
first calls lint/roadmap_ref.py, which fetches origin/roadmap when its last fetch is older than MAX_AGE, bounded at
FETCH_TIMEOUT, and else reads it as of that fetch. When the fetch failed, session_lines adds "read as of <time>" to its
header, `list` prints it on one stderr line, and read_store appends it to the caller's `notes`. check_store and a read of any other ref fetch nothing.

Cost: this module keeps no timer and writes no file of its own. A fresh ref adds no process (roadmap_ref reads one
stat); a stale one adds one `git fetch` of at most FETCH_TIMEOUT seconds, and git writes FETCH_HEAD and the ref.
ruled_entries starts two read-only git processes (one ls-tree, one cat-file --batch). open_entries starts one more cat-file --batch, and only when an open entry
names `lands_in`. check_store adds one more cat-file --batch, only when an open entry names a `step`. A missing ref, a
missing folder or a failed git start gives [], never an error.

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
from datetime import datetime, timezone

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


def _git(repo_dir, args, text=None):
    """(exit code, stdout bytes) of one git start in repo_dir. The code is None when git cannot start or times out."""
    env = {key: value for key, value in os.environ.items() if key not in STRIPPED}
    try:
        done = _nowindow.run(["git", "-C", repo_dir] + list(args), input=text, capture_output=True, env=env,
                             timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, b""
    return done.returncode, done.stdout


def _batch_blobs(repo_dir, specs):
    """{spec: bytes} for each `ref:path` spec that names a blob, from one cat-file --batch. A missing spec is absent
    from the answer. Returns {} when git fails."""
    if not specs:
        return {}
    code, out = _git(repo_dir, ["cat-file", "--batch"], ("\n".join(specs) + "\n").encode("utf-8"))
    found, pos = {}, 0
    if code != 0:
        return found
    for spec in specs:
        end = out.find(b"\n", pos)
        if end < 0:
            break
        head = out[pos:end].split()
        pos = end + 1
        if len(head) == 3 and head[1] == b"blob" and head[2].isdigit():
            size = int(head[2])
            found[spec] = out[pos:pos + size]
            pos += size + 1  # the blob is followed by one newline
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


def _load(repo_dir, ref):
    """(entries, state, bad) of the store at `ref` in repo_dir. `bad` lists a problem line for each store file that is
    not a JSON object. See read_store for the rest."""
    try:
        code, listing = _git(repo_dir, ["ls-tree", "-z", "--name-only", ref, STORE_DIR])
        if code is None:
            return [], "unreadable", []
        names = [n.decode("utf-8", "replace") for n in listing.split(b"\0") if n.endswith(b".json")]
        if code != 0 or not names:
            return [], "absent", []
        specs = ["%s:%s" % (ref, name) for name in names]
        blobs = _batch_blobs(repo_dir, specs)
        if not blobs:
            return [], "unreadable", []
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
                entries.append(body)
            else:
                bad.append("%s is not a JSON object" % name)
        return sorted(entries, key=entry_instant), "ok", bad
    except Exception:
        return [], "unreadable", []


def _fresh_note(repo_dir, ref):
    """The note "read as of HH:MM TZ" when `ref` is the store ref and could not be fetched fresh, else "". When the
    freshness check itself cannot run (it raises, or its module cannot be imported) the note is "read as of unknown:
    <why>": a read is never silent about how fresh it is. Imported at call time: lint/roadmap_ref.py is the one home of
    the roadmap fetch, and a case may swap it."""
    if ref != STORE_REF:
        return ""
    try:
        if HERE not in sys.path:
            sys.path.append(HERE)
        import roadmap_ref
        return roadmap_ref.fresh_ref(repo_dir)
    except Exception as exc:
        return "read as of unknown: " + (" ".join(str(exc).split()) or type(exc).__name__)[:80]


def _read(repo_dir, ref, note=None):
    """(entries, state, bad, note): _load after one fresh_ref call. The one place a read of the store ref fetches. A
    caller that already ran the freshness check for repo_dir passes its `note` ("" for none), and no second check runs."""
    if note is None:
        note = _fresh_note(repo_dir, ref)
    return _load(repo_dir, ref) + (note,)


def read_store(repo_dir, ref=STORE_REF, note=None, notes=None):
    """(entries, state) of the store at `ref` in repo_dir, oldest first by instant. state is "ok" (also an empty
    folder that exists), "absent" (no such ref, folder or repo) or "unreadable" (git cannot start, or fails after the
    listing worked). A file that is not a JSON object is skipped. When `ref` is STORE_REF the read first fetches
    origin/roadmap if it is older than roadmap_ref.MAX_AGE, bounded at roadmap_ref.FETCH_TIMEOUT; a fetch that fails
    reads the ref as it is, and its note "read as of <time>" is appended to `notes` when given. A caller that already
    ran the check for repo_dir passes `note` (its result, "" for none) to skip a second one. Never raises."""
    entries, state, _bad, said = _read(repo_dir, ref, note)
    if said and notes is not None:
        notes.append(said)
    return entries, state


def ruled_entries(repo_dir, ref=STORE_REF):
    """The entries of the store at `ref`, oldest first by instant; [] when the store is absent or unreadable. Fetches
    a stale STORE_REF as read_store does."""
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
    command line. The store ref is fetched when older than MAX_AGE (read_store); when that fetch fails, the header
    ends "read as of HH:MM TZ". Never raises."""
    try:
        entries, _state, _bad, note = _read(repo_dir, STORE_REF)
        opened = open_entries(entries, repo_dir)
        if not opened:
            return []
        newest = sorted(opened, key=entry_instant, reverse=True)
        unread = sum(1 for e in opened if is_unchecked(e))
        lines = ["rulings not on main: %d open (%d with no supersedes read yet), newest first" % (len(opened), unread)
                 + (", " + note if note else "")]
        for entry in newest[:SESSION_ENTRIES]:
            lines.append("  %s %s: %s | supersedes %s" % (entry.get("id", "?"), entry.get("at", "?"), _one_line(entry),
                                                          supersedes_text(entry, REF_CUT)))
        lines.append("  read them in full, from the claude-settings clone: python3 lint/ruled_store.py list %s"
                     % shlex.quote(repo_dir))
        return lines
    except Exception:
        return []


def _list(repo_dir):
    """Prints every open entry in full. A failed fetch of the store ref adds one stderr line: a read is never silent
    about how fresh it is."""
    notes = []
    entries, _state = read_store(repo_dir, notes=notes)
    if notes:
        print("ruled store: %s %s" % (STORE_REF, notes[0]), file=sys.stderr)
    for entry in sorted(open_entries(entries, repo_dir), key=entry_instant, reverse=True):
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


def check_store(repo_dir):
    """One problem line per defect in the store: a file that is not a JSON object; each check_entry problem (prefixed by
    the entry's id); a guard-rule ref that names no rule id; two or more open entries that supersede one ref of one
    kind; an open entry whose `step` (or, with a `steps` list, every listed step) is done on origin/roadmap. A step file
    that is missing or unreadable is not done. [] when the store is clean or absent."""
    entries, _state, bad = _load(repo_dir, STORE_REF)
    problems = list(bad)
    for entry in entries:
        rid = entry.get("id", "?")
        problems += ["%s: %s" % (rid, p) for p in check_entry(entry)]
        if any(not rule for rule in _guard_ids(entry)):
            problems.append("entry %s: guard-rule ref names no rule id" % rid)
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
    return problems


def _check(repo_dir):
    problems = check_store(repo_dir)
    for problem in problems:
        print(problem)
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
