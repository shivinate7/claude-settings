"""Bake a repo's roadmap into one read-only page that opens straight from disk.

    python3 ~/.claude/skills/roadmap/build.py --repo <checkout> [--record-branch roadmap] [--out FILE]

The steps, topics and numbers come from the repo's record branch, under roadmap/data/. In a
checkout that stands on the record branch, the builder reads the working tree and writes
roadmap/roadmap.html there. In any other checkout it reads the branch through git (origin's copy
first, else the local one) and writes to --out. The record homes (decisions, debts, plans and the
rest) come from the checkout itself, at the paths lint/layout.py gives.

The viewer in page/index.html reads its data through the artifact database (window.claude.use('db')).
The builder puts a small read-only stand-in for that database (window.ROADMAP_DB), holding every JSON
file, in front of the page's own script, so the same viewer runs from disk and as the published
artifact. It also writes window.ROADMAP_BUILD: the commit each panel read, or "unknown" and why.

After the build it prints an upkeep list for the triage thread (step c55): open-step notes over
NOTE_WORDS words; in phases that hold an active step, open steps untouched for STALE_DAYS days and
open steps with no note (a later phase waits on purpose, so flagging it would cry wolf); and steps that
entered the top TOP open places in the last day without a "Placed ahead of" line.

Before it builds, it refuses a record branch with git conflict markers (step c72) in any file under
SCANNED, and writes no page.

Cost per build: about six git processes, one read of each scanned file, one page written. No
watcher, no timer, no log.
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.parse

NOTE_WORDS = 250
STALE_DAYS = 5
TOP = 5
DATA = "roadmap/data"
# roadmap.html is left out: the builder rewrites it, so a conflict there is resolved by building.
SCANNED = ("roadmap", "briefs", "plans", "handoffs")
OUTPUT = "roadmap/roadmap.html"
# The layout kinds whose homes the page reads, with the panel name each one gets.
HOMES = (("decisions", "Decisions"), ("debts", "Debts"), ("debt-notes", "Debt notes"),
         ("plans", "Plans"), ("specs", "Specs"))

# A merge subject that names its pull request: GitHub's merge commit, or a squash title ending "(#N)".
PR_SUBJECT = re.compile(r"^Merge pull request #(\d+)\b|\(#(\d+)\)\s*$")

# The listed kinds the Records panel counts. Each shows its count and its NEWEST newest entries.
LISTED = ("decisions", "debts", "plans")
NEWEST = 5
# The extras: {"map": "<path of the repo map>", "github": "<owner>/<repo>"}. The rolled-out layout
# extras file holds them under "roadmap"; else the record branch holds them in EXTRAS.
EXTRAS = "roadmap/extras.json"
GITHUB = re.compile(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$|/git/([^/]+/[^/]+?)(?:\.git)?/?$")
COMPLIANCE_WHY = "unknown (no home yet: the scorecard lives only in chat until compliance-check writes one)"
BOARD_WHY = "unknown (Deferred: where live worker state is read from is still open for the owner)"

HEADER = re.compile(r"^@[0-9a-f]{40,64} \S+$")

HERE = pathlib.Path(__file__).resolve().parent
LINT = HERE.parent.parent / "lint"
sys.path.insert(0, str(HERE.parent.parent / "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)


def git(repo, *args, stdin=None):
    """git's stdout, or None when git cannot run or fails."""
    try:
        done = _nowindow.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


class Tree:
    """The record branch as the working tree of a checkout that stands on it."""

    def __init__(self, repo):
        self.repo, self.ref = repo, "HEAD"
        self.label = "working tree of %s" % repo.name

    def names(self, *prefixes):
        out = git(self.repo, "ls-files", "-z", "--", *prefixes)
        if out is None:
            raise SystemExit("git ls-files failed in %s" % self.repo)
        return sorted(set(filter(None, out.split("\0"))))

    def jsons(self, folder):
        return sorted(p.relative_to(self.repo).as_posix() for p in (self.repo / DATA / folder).glob("*.json"))

    def read(self, names):
        found = {}
        for name in names:
            try:
                found[name] = (self.repo / name).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
        return found


class Ref:
    """The record branch as a git ref, read with no checkout."""

    def __init__(self, repo, ref):
        self.repo, self.ref, self.label = repo, ref, ref

    def names(self, *prefixes):
        out = git(self.repo, "ls-tree", "-r", "-z", "--name-only", self.ref, "--", *prefixes)
        if out is None:
            raise SystemExit("git ls-tree failed on %s" % self.ref)
        return sorted(set(filter(None, out.split("\0"))))

    def jsons(self, folder):
        prefix = "%s/%s/" % (DATA, folder)
        return [n for n in self.names(prefix) if n.endswith(".json") and "/" not in n[len(prefix):]]

    def read(self, names):
        """Every blob in one git cat-file process."""
        if not names:
            return {}
        try:
            done = _nowindow.run(["git", "-C", str(self.repo), "cat-file", "--batch"], capture_output=True,
                                  input="".join("%s:%s\n" % (self.ref, n) for n in names).encode("utf-8"))
        except OSError:
            return {}
        raw, at, found = done.stdout, 0, {}
        for name in names:
            end = raw.find(b"\n", at)
            if end < 0:  # cat-file stopped early; the rest reads as missing
                break
            head = raw[at:end]
            at = end + 1
            if head.endswith(b" missing"):
                continue
            size = int(head.rsplit(b" ", 1)[1])
            found[name] = raw[at:at + size].decode("utf-8", errors="replace")
            at += size + 1
        return found


def record_source(repo, branch):
    """(source, why): the record branch to read, or None and the reason it cannot be read."""
    here = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    if here is not None and here.strip() == branch and (repo / DATA).is_dir():
        return Tree(repo), None
    for ref in ("origin/" + branch, branch):
        if git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}") is not None:
            return Ref(repo, ref), None
    return None, "no %s branch in this checkout" % branch


def conflict_markers(source):
    """file:line of each conflict marker in the files under SCANNED.

    A `=======` line counts only between `<<<<<<< ` and `>>>>>>> `, so a Markdown setext heading passes.
    """
    names = [n for n in source.names(*SCANNED) if n != OUTPUT]
    hits = []
    for name, text in sorted(source.read(names).items()):
        inside = False
        for n, line in enumerate(text.splitlines(), 1):
            if line.startswith("<<<<<<< "):
                inside = True
            elif line.startswith(">>>>>>> "):
                inside = False
            elif not (inside and line == "======="):
                continue
            hits.append(f"{name}:{n}: {line}")
    return hits


def load(source):
    """{steps, topics, meta}, each {file stem: JSON}, in file-name order."""
    folders = ("steps", "topics", "meta")
    names = {folder: source.jsons(folder) for folder in folders}
    texts = source.read([n for folder in folders for n in names[folder]])
    data = {}
    for folder in folders:
        data[folder] = {}
        for name in names[folder]:
            if name in texts:
                data[folder][pathlib.PurePosixPath(name).stem] = json.loads(texts[name])
    return data


def short(repo, ref):
    out = git(repo, "rev-parse", "--short", ref)
    return out.strip() if out else None


def main_ref(repo, branch):
    for ref in ("origin/" + branch, branch):
        if git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}") is not None:
            return ref
    return None


def step_trailers(repo, ref):
    """[(step id, commit, pull request or None)] for each `Step:` trailer on `ref`, from one git log.

    A commit's pull request is the one whose merge put it on the first-parent line of `ref`. Walking
    that line oldest first, each merge owns the commits its other parents bring that no earlier
    commit on the line already holds. None when git cannot read `ref`.
    """
    out = git(repo, "log", ref, "--format=%H%x1f%P%x1f%s%x1f%(trailers:key=Step,valueonly,separator=%x2C)%x1e")
    if out is None:
        return None
    parents, subject, steps = {}, {}, {}
    for rec in out.split("\x1e"):
        fields = rec.strip("\n").split("\x1f")
        if len(fields) != 4:
            continue
        sha, ps, subj, trail = fields
        parents[sha], subject[sha] = ps.split(), subj
        ids = [t for t in re.split(r"[,\s]+", trail) if t]
        if ids:
            steps[sha] = ids
    line, at = [], out.split("\x1f", 1)[0].strip("\n")
    while at in parents:
        line.append(at)
        at = parents[at][0] if parents[at] else None
    owner, seen = {}, set()
    for sha in reversed(line):
        hit = PR_SUBJECT.search(subject[sha])
        pr = "#" + (hit.group(1) or hit.group(2)) if hit else None
        stack = list(parents[sha][1:])
        while stack:
            x = stack.pop()
            if x in seen or x not in parents:
                continue
            seen.add(x)
            owner[x] = pr
            stack.extend(parents[x])
        seen.add(sha)
        owner[sha] = pr
    return [(sid, sha, owner.get(sha)) for sha, ids in steps.items() for sid in ids]


def landed_marks(repo, ref, branch, steps):
    """({open step: [pull request or commit]}, [trailer that names no step], why or None)."""
    found = step_trailers(repo, ref) if ref else None
    if found is None:
        return {}, [], "no %s branch in this checkout" % branch if ref is None else "git log failed on " + ref
    marks, strays = {}, []
    for sid, sha, pr in reversed(found):
        where = pr or sha[:7]
        if sid not in steps:
            strays.append("%s in %s%s" % (sid, sha[:7], " (%s)" % pr if pr else ""))
        elif steps[sid].get("status") != "done" and where not in marks.setdefault(sid, []):
            marks[sid].append(where)
    return {k: v for k, v in marks.items() if v}, strays, None


def homes(repo):
    """{kind: (path, why)}: each HOMES kind's folder in the checkout, or None and why it is unknown."""
    try:
        sys.path.insert(0, str(LINT))
        import layout
        found = {}
        for kind, _ in HOMES:
            paths = layout.candidates(str(repo), kind)
            hit = next((p for p in paths if (repo / p).exists()), None)
            found[kind] = (hit, None if hit else "no %s in this checkout" % " or ".join(paths))
        return found
    except Exception as err:  # the layout is a shared file; any fault in it makes every home unknown
        return {kind: (None, "the layout could not be read: %s" % err) for kind, _ in HOMES}
    finally:
        if str(LINT) in sys.path:
            sys.path.remove(str(LINT))


def extras(repo, source):
    """(extras dict, where it came from) or ({}, None)."""
    try:
        sys.path.insert(0, str(LINT))
        import layout
        if layout.rolled_out(str(repo)):
            path = repo / layout.layout()["extras"]
            found = json.loads(path.read_text(encoding="utf-8")).get("roadmap")
            if isinstance(found, dict):
                return found, layout.layout()["extras"]
    except Exception:  # an unreadable extras file falls through to the record branch's
        pass
    finally:
        if str(LINT) in sys.path:
            sys.path.remove(str(LINT))
    if source is not None:
        text = source.read([EXTRAS]).get(EXTRAS)
        try:
            found = json.loads(text) if text else None
        except ValueError:
            found = None
        if isinstance(found, dict):
            return found, "%s on %s" % (EXTRAS, source.label)
    return {}, None


def github_slug(repo, extra):
    if isinstance(extra.get("github"), str):
        return extra["github"]
    url = (git(repo, "remote", "get-url", "origin") or "").strip()
    hit = GITHUB.search(url)
    return (hit.group(1) or hit.group(2)) if hit else None


def shallow_edge(repo):
    """The commits where a shallow clone's history stops. git shows each as adding every file it holds,
    so their add dates are not real and the newest lists skip them."""
    name = (git(repo, "rev-parse", "--git-path", "shallow") or "").strip()
    try:
        return set((repo / name).read_text(encoding="utf-8").split()) if name else set()
    except OSError:
        return set()


def title_of(path):
    """The first Markdown heading of a file, else its name."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for n, line in enumerate(handle):
                if line.startswith("# "):
                    return line[2:].strip()
                if n > 40:
                    break
    except OSError:
        pass
    return path.name


def records(repo, found, slug, branch):
    """Per listed kind: its count (as `ls | wc -l` counts), its newest entries, or why it is unknown."""
    here = {kind: found[kind][0] for kind in LISTED if found.get(kind, (None,))[0]}
    added, cut = {}, set()
    if here:
        # -z keeps non-ASCII names unquoted; --no-renames counts a file renamed in as added.
        out = git(repo, "log", "HEAD", "--diff-filter=A", "--no-renames", "-z", "--format=@%H %cI", "--name-only",
                  "--", *here.values()) or ""
        cut = shallow_edge(repo)
        when, rank, skip = None, 0, False
        for line in out.split("\0"):
            line = line.strip("\n")
            if HEADER.match(line):
                sha, when = line[1:].split(" ", 1)
                rank, skip = rank + 1, sha in cut
            elif line and not skip:
                # A file in a subfolder dates the subfolder, the entry `ls` shows.
                for home in here.values():
                    if line.startswith(home + "/"):
                        added.setdefault(home + "/" + line[len(home) + 1:].split("/")[0], (rank, when))
    rows = []
    for kind in LISTED:
        name = dict(HOMES)[kind]
        home = here.get(kind)
        if home is None:
            rows.append({"kind": kind, "name": name, "home": None, "count": None, "newest": [],
                         "why": "unknown (%s)" % found.get(kind, (None, "no such kind"))[1]})
            continue
        folder = repo / home
        if not folder.is_dir():
            rows.append({"kind": kind, "name": name, "home": home, "count": None, "newest": [],
                         "why": "unknown (%s is not a folder)" % home})
            continue
        entries = sorted(e for e in os.listdir(folder) if not e.startswith("."))
        # git log lists newest first, so a lower rank is a newer add, and same-second commits keep their order.
        dated = sorted((added[home + "/" + e], e) for e in entries if home + "/" + e in added)
        newest = []
        for (_, at), entry in dated[:NEWEST]:
            rel = home + "/" + entry
            newest.append({"name": entry, "title": title_of(folder / entry), "added": at,
                           "url": blob_url(slug, branch, rel)})
        undated = len(entries) - len(dated)
        why = None
        if undated:
            why = "%d of %d entries have no add commit here (%s), so the list leaves them out" % (
                undated, len(entries), "a shallow clone, or not yet committed" if cut else "not yet committed")
            if not newest:
                why = "unknown (%s)" % why
        rows.append({"kind": kind, "name": name, "home": home, "count": len(entries), "newest": newest,
                     "why": None, "newestWhy": why})
    return rows


def blob_url(slug, branch, rel):
    if not slug:
        return None
    return "https://github.com/%s/blob/%s/%s" % (slug, urllib.parse.quote(branch), urllib.parse.quote(rel))


def health(repo, extra, where, slug, branch):
    """The Health panel: the repo map, the compliance scores and the session board."""
    path = extra.get("map")
    if not isinstance(path, str) or not path:
        repo_map = {"name": "Repo map", "home": None,
                    "read": "unknown (no extras file names a map%s)" % (": " + where if where else "")}
    elif not (repo / path).exists():
        repo_map = {"name": "Repo map", "home": path, "read": "unknown (%s is not in this checkout)" % path}
    else:
        last = (git(repo, "log", "-1", "--format=%h", "--", path) or "").strip()
        repo_map = {"name": "Repo map", "home": path, "read": last or "unknown (git has no commit for it)",
                    "url": blob_url(slug, branch, path)}
    return [repo_map, {"name": "Compliance scores", "home": None, "read": COMPLIANCE_WHY},
            {"name": "Session board", "home": None, "read": BOARD_WHY}]


def build_info(repo, source, why):
    """window.ROADMAP_BUILD: the build time and, per panel, the home it read and the commit it read at."""
    if source is None:
        steps = {"name": "Steps", "home": "roadmap/data", "read": "unknown (%s)" % why}
    else:
        at = short(repo, source.ref)
        read = at or "unknown (git could not name the commit)"
        if isinstance(source, Tree) and at:
            read = at + " with any edits not yet committed"
        steps = {"name": "Steps", "home": "%s, roadmap/data" % source.label, "read": read}
    head = short(repo, "HEAD")
    panels = [steps]
    found = homes(repo)
    there = [found[kind][0] for kind, _ in HOMES if found[kind][0]]
    # The homes are read from the working tree, so a home with uncommitted or untracked files says so.
    status = git(repo, "status", "--porcelain=v1", "-z", "-uall", "--", *there) if there else ""
    dirty = [n[3:] for n in (status or "").split("\0") if len(n) > 3]
    for kind, name in HOMES:
        path, missing = found[kind]
        if path is None:
            panels.append({"name": name, "kind": kind, "home": None, "read": "unknown (%s)" % missing})
            continue
        read = head or "unknown (git could not name the commit)"
        if status is None:
            read += " (unknown whether it has edits not yet committed)"
        elif head and any(n == path or n.startswith(path + "/") for n in dirty):
            read += " with edits not yet committed"
        panels.append({"name": name, "kind": kind, "home": path, "read": read})
    return {"repo": repo.name, "builtAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "panels": panels}


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
# No record branch: the viewer finds no database and says the plan cannot be read.
NO_DB = "<script>\nwindow.ROADMAP_DB = null;\n</script>\n"
BUILD_BLOCK = "<!-- build:info -->\n<script>\nwindow.ROADMAP_BUILD = %s;\n</script>\n<!-- /build:info -->\n"


def as_script(value):
    """JSON for inside a <script>: no `</` to end it and no `<!--` to change how the browser reads it."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "\\u003c!--")


def render(data, info):
    page = (HERE / "page" / "index.html").read_text(encoding="utf-8")
    stub = NO_DB if data is None else STUB % as_script(data)
    head, sep, rest = page.partition("<body>")
    if not sep:
        raise SystemExit("page/index.html has no <body> tag")
    return head + sep + "\n" + stub + BUILD_BLOCK % as_script(info) + rest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bake a repo's roadmap into one read-only page.")
    ap.add_argument("--repo", default=".", help="the checkout to read (default: the current folder)")
    ap.add_argument("--record-branch", default="roadmap", help="the branch that holds roadmap/data/")
    ap.add_argument("--main-branch", default="main", help="the branch whose merges carry Step: trailers")
    ap.add_argument("--out", help="the page to write; needed unless the checkout stands on the record branch")
    args = ap.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    source, why = record_source(repo, args.record_branch)
    if args.out:
        out = pathlib.Path(args.out)
    elif isinstance(source, Tree):
        out = repo / OUTPUT
    else:
        raise SystemExit("This checkout is not on the %s branch, so name the page to write with --out FILE."
                         % args.record_branch)
    data = None
    if source is not None:
        hits = conflict_markers(source)
        if hits:
            print("Conflict markers on %s, so no page was written. Resolve them, then build again:" % source.label)
            print("\n".join("  " + h for h in hits))
            raise SystemExit(1)
        data = load(source)
    info = build_info(repo, source, why)
    ref = main_ref(repo, args.main_branch)
    marks, strays, unread = landed_marks(repo, ref, args.main_branch, data["steps"] if data else {})
    info["landed"] = marks
    extra, where = extras(repo, source)
    slug, found = github_slug(repo, extra), homes(repo)
    info["records"] = records(repo, found, slug, args.main_branch)
    info["health"] = health(repo, extra, where, slug, args.main_branch)
    info["panels"].insert(1, {"name": "Merges", "home": ref or args.main_branch,
                              "read": "unknown (%s)" % unread if unread else short(repo, ref) or "unknown (git could not name the commit)"})
    out.write_text(render(data, info), encoding="utf-8")
    if data is None:
        print(f"{out.name}: steps unknown ({why})")
        return
    print(f"{out.name}: {len(data['steps'])} steps, {len(data['topics'])} topics, {len(data['meta'])} meta")
    upkeep(data["steps"], added_at(source), marks, strays if not unread else ["unknown (%s)" % unread])


def added_at(source):
    """Each step's first-commit time, from one git log; empty when git cannot answer."""
    out = git(source.repo, "log", source.ref, "--diff-filter=A", "--format=@%aI", "--name-only", "--", DATA + "/steps")
    if out is None:
        return {}
    seen, when = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            when = datetime.datetime.fromisoformat(line[1:])
        elif line.endswith(".json"):
            seen.setdefault(pathlib.PurePosixPath(line).stem, when)
    return seen


def upkeep(steps, added, marks, strays):
    now = datetime.datetime.now(datetime.timezone.utc)
    open_ = sorted(((k, d) for k, d in steps.items() if d.get("status") != "done"),
                   key=lambda kd: kd[1].get("order", 1e9))
    live = {d.get("phase") for _, d in open_ if d.get("status") == "active"}
    long_, stale, empty = [], [], []
    for k, d in open_:
        note = d.get("note") or ""
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
    jumped = [k for k, d in open_[:TOP]
              if k in added and (now - added[k]).total_seconds() < 86400
              and "Placed ahead of" not in (d.get("note") or "")]
    if not added:
        jumped = ["unknown (git log could not run)"]
    rows = [("notes over %d words" % NOTE_WORDS, long_), ("untouched %d days in a live phase" % STALE_DAYS, stale),
            ("no note in a live phase", empty), ("new in top %d with no placement line" % TOP, jumped),
            ("landed, waiting for triage to close", ["%s (%s)" % (k, ", ".join(v)) for k, v in sorted(marks.items())]),
            ("Step trailers naming no step", strays)]
    print("upkeep: " + "; ".join(f"{label}: {len(v)}" for label, v in rows))
    for label, v in rows:
        if v:
            print(f"  {label}: {', '.join(v)}")


if __name__ == "__main__":
    main()
