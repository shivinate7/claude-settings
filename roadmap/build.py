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

`python roadmap/build.py --check-staged` is the pre-commit hook (roadmap/hooks/pre-commit, installed by
`git config core.hooksPath roadmap/hooks`; step c138). It reads the step files from the index, not the
working tree, and refuses the commit when an open step's note that the commit adds or changes is over
NOTE_WORDS words. An over-cap note the commit leaves alone passes, so one writer's note never blocks
another's commit. It writes no page.
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


def over_cap(steps):
    """'id (words)' for each open step whose note is over NOTE_WORDS words: the one count of the cap."""
    hits = []
    for k, d in steps.items():
        if not isinstance(d, dict) or d.get("status") == "done":
            continue
        words = len((d.get("note") or "").split())
        if words > NOTE_WORDS:
            hits.append(f"{k} ({words})")
    return hits


STEPS_PATH = "roadmap/data/steps/"


def staged_notes_over_cap(repo):
    """over_cap() for the open step notes the staged commit adds or changes, read from the index.

    A note counts as changed when its text differs from HEAD's (and, while a merge is being committed,
    from each MERGE_HEAD's, so a note the other side wrote passes). A staged file that is not valid JSON
    is skipped: it has no note to count, and build.py fails loudly on it at the next build.
    """
    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)

    def note_at(rev, path):
        r = git("show", f"{rev}:{path}")
        if r.returncode:
            return None
        try:
            d = json.loads(r.stdout)
        except ValueError:
            return None
        return d.get("note") if isinstance(d, dict) else None

    bases = ["HEAD"] if git("rev-parse", "-q", "--verify", "HEAD^{commit}").returncode == 0 else []
    merge_head = pathlib.Path(repo, git("rev-parse", "--git-path", "MERGE_HEAD").stdout.strip())
    if merge_head.is_file():
        bases += merge_head.read_text().split()
    if bases:
        out = git("diff", "--cached", "--no-renames", "--name-only", "-z", "--diff-filter=AM", "HEAD", "--",
                  STEPS_PATH).stdout
    else:
        out = git("ls-files", "-z", "--", STEPS_PATH).stdout
    steps = {}
    for path in filter(None, out.split("\0")):
        if not path.endswith(".json"):
            continue
        r = git("show", f":{path}")
        try:
            d = json.loads(r.stdout)
        except ValueError:
            print(f"pre-commit: {path} is not valid JSON; its note was not counted", file=sys.stderr)
            continue
        if not isinstance(d, dict):
            continue
        if any(note_at(b, path) == d.get("note") for b in bases):
            continue
        steps[pathlib.PurePosixPath(path).stem] = d
    return over_cap(steps)


def check_staged():
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    repo = top.stdout.strip() if top.returncode == 0 else str(ROOT.parent)
    hits = staged_notes_over_cap(repo)
    if hits:
        print(f"Commit refused: these notes are over {NOTE_WORDS} words. Cut them, stage, and commit again:",
              file=sys.stderr)
        print("\n".join(f"  {h[:-1]} words)" for h in hits), file=sys.stderr)
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
    long_, stale, empty, unasked = over_cap(dict(open_)), [], [], []
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
