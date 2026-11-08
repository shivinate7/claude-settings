"""Bake roadmap/data/ into roadmap/roadmap.html, a read-only page that opens straight from disk.

The viewer in page/index.html reads its data through the artifact database (window.claude.use('db')).
This script puts a small read-only stand-in for that database (window.ROADMAP_DB), holding every
JSON file, in front of the page's own script, so the same viewer runs from disk and as the published
artifact. Run it after each edit to roadmap/data/:  python roadmap/build.py
Then republish roadmap/roadmap.html to the roadmap artifact (see roadmap/README.md).

After the build it prints an upkeep list for the triage thread (step c55): open-step notes over
NOTE_WORDS words; in phases that hold an active step, open steps untouched for STALE_DAYS days and
open steps with no note (a later phase waits on purpose, so flagging it would cry wolf); and steps that
entered the top TOP open places in the last day without a "Placed ahead of" line; and open steps
deferred on shiv whose note has neither an "Asked:" nor a "Due after:" line (step c94). It also counts the
files waiting in roadmap/outbox/ (step c98). Cost: one git process per build, no file written.

Before it builds, it refuses a tree with git conflict markers (step c72) in any tracked file under
SCANNED, and writes no page. Cost: one more git process and one read of each scanned file per build.

`python roadmap/build.py --check-staged` is the pre-commit check (roadmap/hooks/pre-commit, installed by
`sh roadmap/hooks/install.sh`, which never sets core.hooksPath; step c138). It reads the step files from the index, not the
working tree, and refuses the commit when it adds or grows an open step's note past NOTE_WORDS words, or
stages a symlink as a step file. A long note the commit leaves alone or trims passes, so one writer's
note never blocks another's commit. It writes no page.

The same check refuses a commit that adds or changes an open step whose "gap" key (stripped, lowercased) is
held by another open step in the index, unless one base held both open with that key, or that has no key
when no base holds its file. Done steps never block. Cost, on top of the note check: when the commit stages
an open step file, one `git ls-files -s -z` and one more `git cat-file --batch` for the index files not yet
read, plus one `git show` per base per staged open step; no file written, and it runs only inside the pre-commit hook.
"""
import datetime
import json
import pathlib
import re
import subprocess
import sys

NOTE_WORDS = 250
STALE_DAYS = 5
TOP = 5
# A step waits on shiv when its note says so. "Asked:" names where the question sits; "Due after:"
# names the work that must land before the question can be asked (step c94).
DEFERRED_ON_SHIV = re.compile(r"Deferred(?: \((?:shiv|needs shiv)[^)]*\)|: shiv)")
ASKED = ("Asked:", "Due after:")
# roadmap.html is left out: build.py rewrites it, so a conflict there is resolved by building.
SCANNED = ("roadmap", "briefs", "plans", "handoffs")
OUTPUT = "roadmap/roadmap.html"

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"


def load(folder):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / folder).glob("*.json"))}


STUB = """<script>
(() => {
  const DATA = %s;
  const snap = docs => ({docs: docs.map(([id, d]) => ({id, data: () => d}))});
  const byOrder = (a, b) => (typeof a[1].order === 'number' ? a[1].order : 1e9) - (typeof b[1].order === 'number' ? b[1].order : 1e9);
  const collection = name => ({
    orderBy: () => ({onSnapshot: ok => ok(snap(Object.entries(DATA[name] || {}).sort(byOrder)))}),
  });
  const doc = path => {
    const [col, id] = path.split('/');
    const d = (DATA[col] || {})[id];
    return {
      onSnapshot: ok => ok({exists: !!d, data: () => d}),
      update: () => Promise.reject(new Error('read only')),
    };
  };
  window.ROADMAP_DB = {use: async () => ({collection, doc, readOnly: true})};
})();
</script>
"""


def conflict_markers(repo):
    """file:line of each conflict marker in the tracked files under SCANNED.

    A `=======` line counts only between `<<<<<<< ` and `>>>>>>> `, so a Markdown setext heading passes.
    """
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--", *SCANNED],
                         capture_output=True, text=True, check=True).stdout
    hits = []
    for name in sorted(set(filter(None, out.split("\0")))):
        if name == OUTPUT:
            continue
        try:
            lines = (repo / name).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        inside = False
        for n, line in enumerate(lines, 1):
            if line.startswith("<<<<<<< "):
                inside = True
            elif line.startswith(">>>>>>> "):
                inside = False
            elif not (inside and line == "======="):
                continue
            hits.append(f"{name}:{n}: {line}")
    return hits


def note_words(d):
    """The one count of a note's length."""
    return len((d.get("note") or "").split())


def over_cap(steps):
    """(id, words) for each open step whose note is over NOTE_WORDS words."""
    return [(k, n) for k, d in steps.items()
            if isinstance(d, dict) and d.get("status") != "done" and (n := note_words(d)) > NOTE_WORDS]


STEPS_PATH = "roadmap/data/steps"


def gap_key(d):
    """A step's gap key as compared: stripped and lowercased; "" when absent, empty or not a string."""
    g = d.get("gap")
    return g.strip().lower() if isinstance(g, str) else ""


def shown(path):
    return path.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


NOT_JSON = object()


class Staged:
    """What the staged commit changes under STEPS_PATH, and the bases it is committed onto.

    Only files directly in STEPS_PATH count, as in load(). Bases are HEAD, plus each MERGE_HEAD while a
    merge is committed. Blobs are read through one `git cat-file --batch` per call to blobs(), and a blob
    is read once per commit.
    """

    def __init__(self, repo):
        self.repo = repo
        self.cache = {}  # blob -> parsed JSON value, or NOT_JSON
        self.bases = ["HEAD"] if self.git("rev-parse", "-q", "--verify", "HEAD^{commit}").returncode == 0 else []
        merge_head = pathlib.Path(repo, self.git("rev-parse", "--git-path", "MERGE_HEAD").stdout.strip())
        if merge_head.is_file():
            self.bases += merge_head.read_text().split()
        self.entries = []  # (mode, blob, path) of each staged add, change or type change
        if self.bases:
            fields = self.git("diff", "--cached", "--raw", "-z", "--no-renames", "--diff-filter=AMT", "HEAD", "--",
                              STEPS_PATH).stdout.split("\0")
            for meta, path in zip(fields[0::2], fields[1::2]):
                _, mode, _, blob, _ = meta.split(" ", 4)
                self.entries.append((mode, blob, path))
        else:
            self.entries = self.listing()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True,
                              encoding="utf-8", errors="surrogateescape")

    def listing(self):
        """(mode, blob, path) of every file in the index under STEPS_PATH."""
        out = []
        for line in filter(None, self.git("ls-files", "-s", "-z", "--", STEPS_PATH).stdout.split("\0")):
            meta, path = line.split("\t", 1)
            mode, blob, _ = meta.split(" ")
            out.append((mode, blob, path))
        return out

    def blobs(self, shas):
        """Parse each blob not read yet, all in one git process."""
        todo = sorted(set(shas) - self.cache.keys())
        if not todo:
            return
        data = subprocess.run(["git", "-C", str(self.repo), "cat-file", "--batch"],
                              input="".join(f"{b}\n" for b in todo).encode(), capture_output=True).stdout
        pos = 0
        for blob in todo:
            end = data.index(b"\n", pos)
            head = data[pos:end].split()
            pos = end + 1
            if head[1] == b"missing":
                self.cache[blob] = NOT_JSON
                continue
            size = int(head[2])
            try:  # surrogateescape, as git() decodes: a non-UTF-8 note still parses and is counted
                self.cache[blob] = json.loads(data[pos:pos + size].decode("utf-8", "surrogateescape"))
            except ValueError:
                self.cache[blob] = NOT_JSON
            pos += size + 1

    def step_at(self, rev, path):
        r = self.git("show", f"{rev}:{path}")
        try:
            d = json.loads(r.stdout) if r.returncode == 0 else None
        except ValueError:
            return None
        return d if isinstance(d, dict) else None

    @staticmethod
    def is_step_file(path):
        p = pathlib.PurePosixPath(path)
        return str(p.parent) == STEPS_PATH and p.name.endswith(".json")

    def changed(self):
        """(steps, refusal lines, invalid paths) for the staged step files.

        steps is (path, parsed step). A staged symlink is refused, since load() would follow it. A file
        that is not JSON is reported in `invalid`; one that is JSON but not an object has no fields to check.
        The next build fails loudly on either.
        """
        files = [e for e in self.entries if self.is_step_file(e[2])]
        self.blobs(b for m, b, _ in files if m != "120000")
        steps, refused, invalid = [], [], []
        for mode, blob, path in files:
            if mode == "120000":
                refused.append(f"{shown(path)} is a symlink; build.py would follow it. Commit the file itself.")
            elif self.cache[blob] is NOT_JSON:
                invalid.append(path)
            elif isinstance(self.cache[blob], dict):
                steps.append((path, self.cache[blob]))
        return steps, refused, invalid

    def index_steps(self):
        """(path, parsed step) of each step file in the index."""
        files = [e for e in self.listing() if self.is_step_file(e[2]) and e[0] != "120000"]
        self.blobs(b for _, b, _ in files)
        return [(path, self.cache[blob]) for _, blob, path in files if isinstance(self.cache[blob], dict)]


def staged_notes_over_cap(staged):
    """(over_cap pairs, refusal lines) for the step files the staged commit adds or changes, read from the index.

    An open note over the cap passes only when some base held the same step open with at least as many
    words: a commit may keep or trim a long note, never add or grow one. A staged file that is not valid
    JSON is skipped: it has no note to count.
    """
    changed, refused, invalid = staged.changed()
    for path in invalid:
        print(f"pre-commit: {shown(path)} is not valid JSON; its note was not counted", file=sys.stderr)
    steps = {}
    for path, d in changed:
        olds = [staged.step_at(b, path) for b in staged.bases]
        if any(o and o.get("status") != "done" and note_words(o) >= note_words(d) for o in olds):
            continue
        steps[shown(pathlib.PurePosixPath(path).stem)] = d
    return over_cap(steps), refused


def staged_gap_refusals(staged):
    """Refusal lines for the open steps the staged commit adds or changes whose gap key is missing or shared.

    An open step on key K is refused when another open step in the index holds K, unless one single base
    held both open with K: a commit may keep a pair that already shared a key, never make one. A step with
    no key is refused only when no base holds its file, so a step filed before gap keys can still be edited.
    Done steps are never checked and never block. The index is read only when a staged open step needs it.
    """
    def stem(path):
        return shown(pathlib.PurePosixPath(path).stem)

    def held(rev, path, key):
        d = staged.step_at(rev, path)
        return d is not None and d.get("status") != "done" and gap_key(d) == key

    open_changed = sorted((path, d) for path, d in staged.changed()[0] if d.get("status") != "done")
    if not open_changed:
        return []
    holders = {}
    for path, d in staged.index_steps():
        if d.get("status") != "done" and gap_key(d):
            holders.setdefault(gap_key(d), []).append(path)
    refused = []
    for path, d in open_changed:
        key = gap_key(d)
        if not key:
            if all(staged.step_at(b, path) is None for b in staged.bases):
                refused.append(f'{stem(path)} has no gap. Add a "gap" field: a slug naming the one gap it closes.')
            continue
        for other in sorted(holders.get(key, [])):
            if other != path and not any(held(b, path, key) and held(b, other, key) for b in staged.bases):
                refused.append(f'{stem(other)} holds the gap "{key}", and {stem(path)} takes it too. '
                               f"Close {stem(other)}, or give {stem(path)} its own gap.")
    return refused


def check_staged():
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                         encoding="utf-8", errors="surrogateescape")
    repo = top.stdout.strip() if top.returncode == 0 else str(ROOT.parent)
    staged = Staged(repo)
    hits, refused = staged_notes_over_cap(staged)
    refused += staged_gap_refusals(staged)
    if hits:
        print(f"Commit refused: these notes are over {NOTE_WORDS} words. Cut them, stage, and commit again:",
              file=sys.stderr)
        print("\n".join(f"  {k} ({n} words)" for k, n in hits), file=sys.stderr)
    if refused:
        print("Commit refused:\n" + "\n".join("  " + r for r in refused), file=sys.stderr)
    if hits or refused:
        raise SystemExit(1)


def main():
    hits = conflict_markers(ROOT.parent)
    if hits:
        print("Conflict markers, so no page was written. Resolve them, then build again:")
        print("\n".join("  " + h for h in hits))
        raise SystemExit(1)
    data = {"steps": load("steps"), "topics": load("topics"), "meta": load("meta")}
    page = (ROOT / "page" / "index.html").read_text(encoding="utf-8")
    stub = STUB % json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    head, sep, rest = page.partition("<body>")
    if not sep:
        raise SystemExit("page/index.html has no <body> tag")
    (ROOT / "roadmap.html").write_text(head + sep + "\n" + stub + rest, encoding="utf-8")
    print(f"roadmap.html: {len(data['steps'])} steps, {len(data['topics'])} topics, {len(data['meta'])} meta")
    upkeep(data["steps"])
    outbox = sorted(p.name for p in (ROOT / "outbox").glob("*.md") if p.name != "README.md")
    print(f"outbox: {len(outbox)} file(s)" + (": " + ", ".join(outbox) if outbox else ""))


def added_at():
    """Each step's first-commit time, from one git log; empty when git cannot answer."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--diff-filter=A", "--format=@%aI", "--name-only", "--", "data/steps"],
            capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    seen, when = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            when = datetime.datetime.fromisoformat(line[1:].replace("Z", "+00:00"))
        elif line.endswith(".json"):
            seen.setdefault(pathlib.Path(line).stem, when)
    return seen


READY_FLOOR = 6


def upkeep(steps):
    now = datetime.datetime.now(datetime.timezone.utc)
    open_ = sorted(((k, d) for k, d in steps.items() if d.get("status") != "done"),
                   key=lambda kd: kd[1].get("order", 1e9))
    live = {d.get("phase") for _, d in open_ if d.get("status") == "active"}
    long_, stale, empty, unasked = [f"{k} ({n})" for k, n in over_cap(dict(open_))], [], [], []
    for k, d in open_:
        note = d.get("note") or ""
        if DEFERRED_ON_SHIV.search(note) and not any(a in note for a in ASKED):
            unasked.append(k)
        if d.get("phase") not in live:
            continue
        if not note.strip():
            empty.append(k)
        try:
            at = datetime.datetime.fromisoformat(d.get("updatedAt", "").replace("Z", "+00:00"))
        except ValueError:
            at = None
        if at is None or (now - at).days >= STALE_DAYS:
            stale.append(k)
    added = added_at()
    jumped = [k for k, d in open_[:TOP]
              if k in added and (now - added[k]).total_seconds() < 86400
              and "Placed ahead of" not in (d.get("note") or "")]
    if not added:
        jumped = ["unknown (git log could not run)"]
    rows = [("notes over %d words" % NOTE_WORDS, long_), ("untouched %d days in a live phase" % STALE_DAYS, stale),
            ("no note in a live phase", empty), ("new in top %d with no placement line" % TOP, jumped),
            ("deferred on shiv with no question", unasked)]
    # Ready queue for the build advisor: open todo or active steps (not the c52 and c55 frames)
    # with no deferral, no "Due after" and no "Waits on:" (a Mac check, an owner test).
    # Floor READY_FLOOR (coordinator, Oct 27, after the queue ran dry 09:25-11:26 CDT).
    ready = [k for k, d in open_ if d.get("status") in ("todo", "active") and k not in ("c52", "c55")
             and not DEFERRED_ON_SHIV.search(d.get("note") or "")
             and not any(m in (d.get("note") or "") for m in ("Due after", "Waits on:"))]
    if len(ready) < READY_FLOOR:
        rows.append(("ready todo steps under the floor of %d" % READY_FLOOR, ready or ["none"]))
    print("ready: %d (floor %d): %s" % (len(ready), READY_FLOOR, ", ".join(ready[:READY_FLOOR + 2])))
    print("upkeep: " + "; ".join(f"{label}: {len(v)}" for label, v in rows))
    for label, v in rows:
        if v:
            print(f"  {label}: {', '.join(v)}")


if __name__ == "__main__":
    check_staged() if sys.argv[1:] == ["--check-staged"] else main()
