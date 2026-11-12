#!/usr/bin/env python3
"""The one reader of the ruled store: the owner's rulings that main has not yet taken in. Standard library only.

    python3 lint/ruled_store.py --session-line REPO   the lines the session-start hook prints, or nothing
    python3 lint/ruled_store.py list REPO             every open entry in full
    python3 lint/ruled_store.py check REPO            exit 1 when an entry lacks a required key or a zoned `at`

The store is the folder roadmap/rulings on origin/roadmap of REPO, one JSON file per ruling. An entry holds `id`,
`at` (ISO 8601 with a zone), `ruling`, `source`, `status` ("open" or "closed"), `supersedes` (a list of
{"kind", "ref"}) or `supersedes_none` (the reason it supersedes nothing; a reason that starts with "unread" means
triage has not read it yet), and optionally `lands_in` ({"path", "contains"}).

An entry is open until the owner's ruling is on main. It closes when `status` is "closed", or when the text of
`lands_in.contains` is found, whitespace-normalised, in the blob of `lands_in.path` on origin/main. Triage writes
the entries, and the restart plan cites them. The decision record is ruled-store-one-home.

ENTRIES_LIFT_GUARDS is the one switch (owner item 646). False, the setting, makes an entry text only: it informs a
session and the question judge and lifts no guard rule. True lets an open entry lift the guard rules it names in
its `supersedes` (kind "guard-rule"). Nothing calls lifted_guards yet; the switch sets what it returns.

Cost: this module keeps no process and no timer and writes no file. ruled_entries starts two read-only git processes
(one ls-tree, one cat-file --batch). open_entries starts one more cat-file --batch, and only when an open entry
names `lands_in`. A missing ref, a missing folder or a failed git start gives [], never an error.
"""
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone

ENTRIES_LIFT_GUARDS = False  # owner item 646: False is text only (option a); True lets an open entry lift guard rules
STORE_REF = "origin/roadmap"
MAIN_REF = "origin/main"
STORE_DIR = "roadmap/rulings/"
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
        done = subprocess.run(["git", "-C", repo_dir] + list(args), input=text, capture_output=True, env=env,
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


def read_store(repo_dir, ref=STORE_REF):
    """(entries, state) of the store at `ref` in repo_dir, oldest first by instant. state is "ok" (also an empty
    folder that exists), "absent" (no such ref, folder or repo) or "unreadable" (git cannot start, or fails after the
    listing worked). A file that is not a JSON object is skipped. Never raises."""
    try:
        code, listing = _git(repo_dir, ["ls-tree", "-z", "--name-only", ref, STORE_DIR])
        if code is None:
            return [], "unreadable"
        names = [n.decode("utf-8", "replace") for n in listing.split(b"\0") if n.endswith(b".json")]
        if code != 0 or not names:
            return [], "absent"
        specs = ["%s:%s" % (ref, name) for name in names]
        blobs = _batch_blobs(repo_dir, specs)
        if not blobs:
            return [], "unreadable"
        entries = []
        for spec in specs:
            try:
                body = json.loads(blobs[spec].decode("utf-8"))
            except (KeyError, ValueError):
                continue
            if isinstance(body, dict):
                entries.append(body)
        return sorted(entries, key=entry_instant), "ok"
    except Exception:
        return [], "unreadable"


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


def lifted_guards(entries):
    """The guard rules the open entries lift: each `supersedes` ref of kind "guard-rule". [] while ENTRIES_LIFT_GUARDS
    is False."""
    if not ENTRIES_LIFT_GUARDS:
        return []
    lifted = []
    for entry in entries:
        if entry.get("status") == "closed":
            continue
        for item in _supersedes(entry):
            ref = item.get("ref")
            if item.get("kind") == "guard-rule" and isinstance(ref, str) and ref not in lifted:
                lifted.append(ref)
    return lifted


def check_entry(entry):
    """One problem line per defect: a missing or empty required key, an `at` that is unreadable or has no zone, and
    neither a listed `supersedes` nor a `supersedes_none` reason."""
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
    reason = entry.get("supersedes_none")
    if not _supersedes(entry) and not (isinstance(reason, str) and reason.strip()):
        problems.append("neither supersedes nor supersedes_none is set")
    return problems


def _unread(entry):
    reason = entry.get("supersedes_none")
    return not _supersedes(entry) and isinstance(reason, str) and reason.strip().lower().startswith("unread")


def supersedes_text(entry, cut=None):
    """The supersedes refs joined by "; ", each cut to `cut` characters when given; "none", or "unread" for an entry
    triage has not read, when it lists none."""
    refs = [str(item.get("ref", "")) for item in _supersedes(entry)]
    if not refs:
        return "unread" if _unread(entry) else "none"
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
        unread = sum(1 for e in opened if _unread(e))
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


def _check(repo_dir):
    bad = 0
    for entry in ruled_entries(repo_dir):
        for problem in check_entry(entry):
            print("%s: %s" % (entry.get("id", "?"), problem))
            bad += 1
    return 1 if bad else 0


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
