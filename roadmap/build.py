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
"""
import datetime
import json
import pathlib
import re
import subprocess

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
            when = datetime.datetime.fromisoformat(line[1:])
        elif line.endswith(".json"):
            seen.setdefault(pathlib.Path(line).stem, when)
    return seen


def upkeep(steps):
    now = datetime.datetime.now(datetime.timezone.utc)
    open_ = sorted(((k, d) for k, d in steps.items() if d.get("status") != "done"),
                   key=lambda kd: kd[1].get("order", 1e9))
    live = {d.get("phase") for _, d in open_ if d.get("status") == "active"}
    long_, stale, empty, unasked = [], [], [], []
    for k, d in open_:
        note = d.get("note") or ""
        if DEFERRED_ON_SHIV.search(note) and not any(a in note for a in ASKED):
            unasked.append(k)
        words = len(note.split())
        if words > NOTE_WORDS:
            long_.append(f"{k} ({words})")
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
    print("upkeep: " + "; ".join(f"{label}: {len(v)}" for label, v in rows))
    for label, v in rows:
        if v:
            print(f"  {label}: {', '.join(v)}")


if __name__ == "__main__":
    main()
