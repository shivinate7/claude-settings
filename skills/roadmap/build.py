"""Bake a repo's roadmap into one read-only page that opens straight from disk.

    python3 ~/.claude/skills/roadmap/build.py --repo <checkout> [--record-branch NAME] [--out FILE] [--block]

The steps, topics and numbers come from the repo's record branch, under roadmap/data/. In a
checkout that stands on the record branch, this script reads the working tree and writes
roadmap/roadmap.html there. In any other checkout it reads the branch through git (origin's copy
first, else the local one) and writes to --out. The record homes (decisions, debts, plans and the
rest) come from the checkout itself, at the paths lint/layout.py gives. Without --record-branch the
branch is the one the checkout's extras file names ("record-branch", a fork worktree's own), else
"roadmap"; the flag wins.

With --block this script writes only the marked data block (window.ROADMAP_DATA and window.ROADMAP_BUILD,
never ROADMAP_DB) to --out. The one page of a repo is the waiting page: its writer splices that block into
the live page and alone publishes (skills/waiting-page/splice.py). This script publishes nothing.

The viewer in page/index.html reads its data through the artifact database (window.claude.use('db')).
This script puts a small read-only stand-in for that database (window.ROADMAP_DB), holding every JSON
file, in front of the page's own script, so the same viewer runs from disk and as the published
artifact. It also writes window.ROADMAP_BUILD: the commit each panel read, or "unknown" and why.

Live work (step o8, option a) comes from --live FILE: the project threads and the open pull requests
and branches, which the publisher reads with its own tools just before the build. This script cannot
reach either itself, so it only checks the file's shape and bakes it in.

After it runs, this script prints an upkeep list for the triage thread (step c55): open-step notes over
NOTE_WORDS words; in phases that hold an active step, open steps untouched for STALE_DAYS days and
open steps with no note (a later phase waits on purpose, so flagging it would cry wolf); and steps that
entered the top TOP open places in the last day without a "Placed ahead of" line.

The upkeep list also names each step marked doing or active that has no live lane session and no open
pull request, so triage can set it back (step roadmap-matches-lanes). A step is live when a session in
the live file's "sessions" list is not archived (any other status counts) and carries both
the tag cs-repo:<this repo's GitHub name> and the tag cs-step:<step id>, or when an open pull request's
branch equals the step id or lane/<step id>. The step id matches exactly; the GitHub name ignores case. A session row
with no tags key, or null tags, has no tags. The cs-repo tag is needed because list_sessions is
account-wide and step ids repeat across repos. A step whose status is none of todo, ready, doing, active or
done is listed as unknown status. The row reads one unknown entry, never an empty list, when the live
file is missing or unreadable; its readAt is not an ISO time, has no time zone, is over STALE_LIVE_MINUTES
old or is more than FUTURE_MINUTES ahead; it has no sessions list; the repo's GitHub name cannot be read;
or a session row or pull row has the wrong shape.

The upkeep list also holds two rows for the stale-ready report (step triage-stale-ready-report): "ready todo
steps" (each todo step whose note holds the sentence "Ready.", not gated on live phases) and "draft PRs over
STALE_DRAFT_HOURS h with no live lane" (each draft pull row whose optional createdAt, GitHub's created_at, is
that far before the live file's readAt, when no live session step equals the pull's branch). A draft row with no
usable createdAt reads "unknown (#N has no createdAt)". A pull names a step when its branch equals the step id or
its title holds the id as a whole token (names_step), used by the pair line below. The stale-draft row's lane check is
unlaned's: the branch equals a live session step exactly.

The row "lanes to archive" (idle_lanes) lists each completed or review-ready lane session whose steps have all landed (a Step trailer, status done, or a landed pull, read from
`closedPulls` and the open pulls) and that no open pull (on lane_head_refs, or whose body names the session) or open page item holds; `merge --idle-lanes` prints the same list. An idle lane
not to archive now reads `hold (<reason>; lane <session id>)` and is left out of the row's count. The reason is no
cs-step tag, a step unproven on main, or a step whose `lane` is the session and that is still doing or active and not
landed; the last clears when the step moves or closes.
A lane that waits (step not done, open pull, open item) prints no line.

This script goes red (step roadmap-pr-without-step) when a todo step is named by an open pull: it prints
"todo step with an open PR: <id> (#N)" per pair, writes the page, then exits 1. Without a usable readAt and pulls read (sessions are not
needed) it prints one "todo step with an open PR: unknown (<why>)" line and exits 0. The conflict-marker refusal also exits 1; the
printed line tells them apart.

The build goes red (decision mockup-home) when an open step (status not done) has a note, why or ask that cites a
mockup by its id (`item<N>-<letter>`, a whole token) and the step's `mockups` field, {"<id>": "<path>"}, holds no
file for it. It prints "mockup with no file: <step id> <mockup id> (<remedy>)" per miss, writes the page, then exits
1. The remedy names git fetch, since a stale or unfetched origin ref reads as a miss. An
entry is a miss when its path is outside the design folder (lint/layout.py mockup_homes; a machine-home path is
outside it), is a link or a folder, or names a file that no origin ref holds (mockup_on_origin below: any
remote-tracking ref under refs/remotes/origin/, an open PR's branch too, not the checkout). It reads unknown,
never a miss, and prints "mockup file unread: <step id> <mockup id> (<why>)" with exit 0, when origin cannot be
shown: no origin ref, a shallow checkout, a failed git read, or a layout that cannot be read. Cost: at most four
git processes per build, however many entries and origin refs (the ref listing, the shallow check, one batched
`git cat-file --batch-check` type read, and one batched link read when some ref holds a blob at an entry's path);
no file or log.

The upkeep list also names each closed waiting-page item whose home is an open step that never cites
the item (step page-ruling-reaches-step). The live file's optional "items" list holds one row per item
of the repo's waiting page: {"n": int, "status": str, "home": str}. An item is listed when its status
is "closed", its home (trimmed, with an optional leading "step " dropped) equals the id of a step that
is not done, and none of that step's note, why or ask matches `item <n>` (any case, an optional #).
Each entry reads `<step id> (page item <n>)`. The row reads one unknown entry, never an empty list,
when the live file is missing or unreadable, its readAt is bad (the stale-step row's readAt cases), it has no
items list, or it holds an item row of the wrong shape. A skipped session row does not blank this row.

The upkeep list also names each doing or active step whose note holds a stale dated claim, so triage asks
for a re-check on main before a lane starts (step stale-note-recheck). A claim is the whole word Finding or
Checked (any case; no letter, digit or hyphen may touch it, so "Findings", "Rechecked", "Re-checked" and
"c146-checked-map" do not count), then within 40 characters, with no "." or newline between, a date:
`Mon D` or `Month D` with an optional `, YYYY` or ` YYYY`, or ISO `YYYY-MM-DD`. A month name needs a
capital first letter, so "May 2" counts and "may 2" does not. A
date with no year takes the build year, or the year before if it would be in the future. A date that does
not exist is skipped. When the newest claim in a note is STALE_DAYS or more days old, the entry reads
`<step id> (<date as written>)`. The row reads the notes only, so it needs no live file.

Before it builds, it refuses a record branch with git conflict markers (step c72) in any file under
SCANNED, and writes no page.

Cost per build: about six git processes, one read of each scanned file, one page written. No
watcher, no timer, no log. The stale-step row adds no git process, file, timer or log to the build. It
adds to triage's publish, already running: one more list_sessions walk (every page) and three more
fields (id, session_status, tags) per session in the live file it already writes. The page-ruling row adds
one read of the waiting page's items (n, status, home) to that same publish. This script adds no git
process, file, timer or log for it. The dated-claim row adds no git process, file, timer or log: it reads
the notes already loaded.
The red line and the two stale-ready rows add no process, file, timer or log: they read the live file this
script already reads. The publisher adds one field (createdAt) per pull row, from the GitHub list call it
already makes.
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
# A live file older than this counts a dead lane as live, so the stale-step row reads unknown.
STALE_LIVE_MINUTES = 60
STALE_DRAFT_HOURS = 12
PAIR_LINE = "todo step with an open PR"
# Every stalled line starts with this. An unknown read prints `<STALLED_LINE>: unknown (<why>)` and exits 0.
STALLED_LINE = "stalled step"
# Every ready line starts with this. It never changes the exit code.
READY_LINE = "ready not started"
# Who may decide a paused step (the `paused.decides` field, written by triage).
PAUSE_DECIDES = ("owner", "coordinator", "triage")
MOCKUP_LINE = "mockup with no file"
MOCKUP_UNREAD_LINE = "mockup file unread"
# A miss line's remedy. A stale or unfetched origin ref reads as a miss, so the remedy names the fetch.
MOCKUP_REMEDY = "commit the file under the design folder and push it; if it is pushed, run git fetch"
# One found record of `git cat-file --batch-check=%(objectname) %(objecttype)`: a sha-1 or sha-256 name, then the type.
CAT_FOUND = re.compile(r"([0-9a-f]{40}|[0-9a-f]{64}) (\w+)")
# The two-line records `--follow-symlinks` prints for a link it cannot resolve to an object: the word and a size.
CAT_LINK_WORDS = ("symlink", "dangling", "loop", "notdir")
# A mockup id cited in a step's text: item<N>-<letter>, a whole token (no letter, digit, "_" or "-" touches it).
MOCKUP_ID = re.compile(r"(?<![A-Za-z0-9_-])item\d+-[a-z](?![A-Za-z0-9_-])", re.I)
MOCKUP_TEXT = ("note", "why", "ask")
READY_SENTENCE = re.compile(r"(?:^|[.!?]\s+)Ready\.(?=\s|$)")
# A session keeps its step live unless its status is archived (session-tiers, Live-coordinator check).
# An unseen status reads live: a false "set to todo" resets a working lane's step; a missed flag only delays cleanup.
ARCHIVED_SESSION = "SESSION_STATUS_ARCHIVED"
# list_sessions' five status_bucket enum names. A live lane row with none of them is a wrong form, so the lanes read unknown.
SESSION_BUCKETS = ("SESSION_STATUS_BUCKET_WORKING", "SESSION_STATUS_BUCKET_BLOCKED", "SESSION_STATUS_BUCKET_REVIEW_READY",
                   "SESSION_STATUS_BUCKET_COMPLETED", "SESSION_STATUS_BUCKET_FAILED")
# The buckets that mark a lane as done working: only these two can list a lane to archive.
IDLE_BUCKETS = SESSION_BUCKETS[2:4]
# A waiting-page item in one of these statuses no longer holds its lane. The page writes open and closed only
# (skill waiting-page, the database), so any other status holds.
ITEM_DONE_STATUSES = ("closed",)
# A live file with no items list: the open items are unknown, so the lanes to archive read unknown.
ITEMS_MISSING_WHY = "unknown (the live file has no items list)"
IDLE_LANES_LINE = "lanes to archive"
# A readAt this far past the build time is clock skew; further than that is a bad stamp.
FUTURE_MINUTES = 5
# `ready` reads as todo.
TODO_STATUS = ("todo", "ready")
RUNNING_STATUS = ("doing", "active")
KNOWN_STATUS = TODO_STATUS + RUNNING_STATUS + ("done",)
TOP = 5
DATA = "roadmap/data"
# roadmap.html is left out: this script rewrites it, so a conflict there is resolved by building.
SCANNED = ("roadmap", "briefs", "plans", "handoffs")
OUTPUT = "roadmap/roadmap.html"
# The layout kinds whose homes the page reads, with the panel name each one gets.
HOMES = (("decisions", "Decisions"), ("debts", "Debts"), ("debt-notes", "Debt notes"),
         ("todo", "To-do"), ("plans", "Plans"), ("specs", "Specs"))

# A merge subject that names its pull request: GitHub's merge commit, or a squash title ending "(#N)".
PR_SUBJECT = re.compile(r"^Merge pull request #(\d+)\b|\(#(\d+)\)\s*$")

# The listed kinds the Records panel counts. Each shows its count and its NEWEST newest entries.
LISTED = ("decisions", "debts", "plans")
NEWEST = 5
# The extras: {"map": "<path of the repo map>", "github": "<owner>/<repo>"}. The rolled-out layout
# extras file holds them under "roadmap"; else the record branch holds them in EXTRAS.
EXTRAS = "roadmap/extras.json"
COMPLIANCE_WHY = "unknown (no home yet: the scorecard lives only in chat until compliance-check writes one)"
BOARD_WHY = ("unknown (session-board's store lives on one machine, so a cloud build cannot read it; "
             "Live work reads project threads and GitHub instead)")
# The thread states the publisher's live file may carry, in the order the page lists them.
STATES = ("blocked", "working", "review_ready", "failed", "stopped", "done")

HEADER = re.compile(r"^@[0-9a-f]{40,64} \S+$")

HERE = pathlib.Path(__file__).resolve().parent
LINT = HERE.parent.parent / "lint"
sys.path.insert(0, str(HERE.parent.parent / "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import git_reads  # noqa: E402  the one home of a checkout's GitHub repo, shared with the guard (hooks/git_reads.py)
from shared_names import (  # noqa: E402,F401  REPO_TAG: test_build pins build.REPO_TAG to the shared object  the one home of the tag names and lane head refs, shared with the guard (hooks/shared_names.py)
    BUILD_TAG, LANE_TAG, REPO_TAG, STEP_TAG, TOPIC_TAG, body_names_session, lane_head_refs, repo_tag_names,
)


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


DEFAULT_RECORD_BRANCH = "roadmap"  # the same default as lint/layout.py, for when layout.py cannot be imported


def default_record_branch(repo):
    """The record branch the checkout's extras file names, else "roadmap"."""
    sys.path.insert(0, str(LINT))
    try:
        import layout
        try:
            return layout.record_branch(str(repo))
        except layout.BranchNameError as err:  # a bad key must not read as "roadmap": it would build the wrong record
            raise SystemExit("The record branch cannot be read from the layout extras file: %s" % err)
    except SystemExit:
        raise
    except Exception as err:  # an extras file that cannot be parsed builds as it did before the key existed
        print("warning: %s; reading the record branch %s" % (err, DEFAULT_RECORD_BRANCH), file=sys.stderr)
        return DEFAULT_RECORD_BRANCH
    finally:
        if str(LINT) in sys.path:
            sys.path.remove(str(LINT))


def extras(repo, source):
    """(extras dict, where it came from) or ({}, None)."""
    try:
        sys.path.insert(0, str(LINT))
        import layout
        if layout.has_extras(str(repo)):
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
    """The repo's `owner/name`: the extras' "github" key, else the origin (git_reads.github_repo, shared with the guard)."""
    return git_reads.github_repo(repo, extra)


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


def live_work(path, steps, slug=None):
    """window.ROADMAP_BUILD.live: the publisher's threads, pull requests and branches, or why unknown.

    Shape: {"readAt": ISO, "threads": [{"title", "state", "lastActivity"?, "step"?, "pr"?}],
    "pulls": [{"number", "title", "branch"?, "draft"?, "createdAt"?, "url"?, "checks"?}], "branches"?: [{"name", "updatedAt"?}],
    "sessions"?: [{"id", "session_status", "tags"?}]} (triage copies the list_sessions rows, every page;
    list_sessions omits the tags key on a tagless session, so a missing or null tags reads as no tags).
    A file with no threads or pulls list reads unknown, so a dropped key never shows as "none". An entry with the wrong shape is counted in `skipped`, never dropped silently. A step a thread
    names that is not an open step is listed in `strays`. The session rows feed only the stale-step upkeep row:
    `sessionSteps` holds the step ids of sessions that are not archived, carrying this repo's cs-repo tag, and `staleWhy`
    says why that row reads unknown, or None. `pullWhy` says why the todo-with-open-PR line reads
    unknown, or None; it reads only readAt and the pulls list, never the sessions.
    A live file with no sessions list still renders Live work.
    "items" (optional, the waiting page's rows `{"n", "status", "home", "lane"?, "owner"?}`) feeds the page-ruling upkeep
    row, the stalled items and the lanes-to-archive row: `pageItems` holds the rows, or None with `itemsWhy` saying why
    they read unknown. `lane` is where the item's answer went (text, or null for none) and `owner` is the session that
    reads the answer; a row keeps each only when the file has the key.
    `laneTags` holds the cs-topic: and cs-build: tags of the live sessions, for lane_live.
    Two more optional keys feed the lanes-to-archive row (idle_lanes): a sessions row's `status_bucket` (list_sessions'
    enum name; missing reads as not completed) and a pulls row's `head` (the head commit sha). `laneSessions` holds the
    kept session rows, or None. Old files without them read as before.
    "closedPulls" (optional, `[{"number", "branch", "head"?, "base"?, "merged"?, "body"?}]`) are the closed and merged pull
    requests, kept apart from the open `pulls` so the open-pull rows never read a closed one as open; idle_lanes reads them
    for the landed test. An open pull row may also carry `body`. A closed row with the wrong shape is counted in `skipped`.
    `path` may also be the parsed live object (a dict), for `merge --idle-lanes --sessions`, which builds it without a file.
    """
    if not path:
        return {"read": "unknown (no --live file: the publisher writes it from the project threads and GitHub)"}
    if isinstance(path, dict):
        raw = path
    else:
        try:
            raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            return {"read": "unknown (the live file could not be read: %s)" % err}
    if not isinstance(raw, dict):
        return {"read": "unknown (the live file is not a JSON object)"}
    read = raw.get("readAt")
    try:
        datetime.datetime.fromisoformat(read.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        read = "unknown (the live file's readAt is not an ISO time: %r)" % (read,)
    missing = [key for key in ("threads", "pulls") if not isinstance(raw.get(key), list)]
    if missing:
        return {"read": "unknown (the live file has no %s list)" % " or ".join(missing)}
    skipped, strays = [], []

    def keep(kind, rows, ok):
        good = []
        for n, row in enumerate(rows if isinstance(rows, list) else []):
            if isinstance(row, dict) and ok(row):
                good.append(row)
            else:
                skipped.append("%s %d" % (kind, n + 1))
        if not isinstance(rows, list):
            skipped.append("%s (not a list)" % kind)
        return good

    text = lambda row, key: isinstance(row.get(key), str) and row[key].strip()
    threads = keep("thread", raw.get("threads", []), lambda r: text(r, "title") and r.get("state") in STATES
                   and (r.get("step") is None or isinstance(r["step"], str)))
    before_pulls = len(skipped)
    pulls = keep("pull", raw.get("pulls", []),
                 lambda r: type(r.get("number")) is int and text(r, "title")
                 and (r.get("branch") is None or isinstance(r["branch"], str)))
    pulls_skipped = len(skipped) - before_pulls
    closed_pulls = keep("closed pull", raw.get("closedPulls", []), lambda r: type(r.get("number")) is int
                        and (r.get("branch") is None or isinstance(r["branch"], str)))
    branches = keep("branch", raw.get("branches", []), lambda r: text(r, "name"))
    for row in threads:
        sid = row.get("step") or None
        if sid and steps is None:
            strays = ["unknown (the steps could not be read)"]
            break
        if sid and (sid not in steps or steps[sid].get("status") == "done"):
            strays.append("%s (%s)" % (sid, row["title"]))
    threads.sort(key=lambda r: (STATES.index(r["state"]), r.get("title")))
    why, session_steps, lane_sessions = [], [], None  # the first reason wins
    lane_tags = []  # the cs-topic: and cs-build: tags of the same live sessions, for lane_live
    if read.startswith("unknown"):
        why.append(read)
    else:
        minutes = live_age_minutes(read)
        if minutes is None:
            why.append("unknown (the live file's readAt has no time zone: %r)" % (read,))
        elif minutes > STALE_LIVE_MINUTES:
            why.append("unknown (the live file was read %d minutes ago; read it again)" % minutes)
        elif minutes < -FUTURE_MINUTES:
            why.append("unknown (the live file's readAt is in the future)")
    read_why = why[0] if why else None  # the page-ruling row takes the readAt reasons only, never the sessions ones
    pull_why = read_why  # the red pair line reads readAt and pulls only, never sessions
    if not isinstance(raw.get("sessions"), list):
        why.append("unknown (the live file has no sessions list)")
    elif not slug:
        why.append("unknown (the repo's GitHub name could not be read)")
    else:
        before = len(skipped)
        sessions = keep("session", raw["sessions"], lambda r: isinstance(r.get("id"), str)
                        and isinstance(r.get("session_status"), str)
                        and (r.get("tags") is None or isinstance(r["tags"], list)))
        # list_sessions is account-wide and step ids repeat across repos, so a session counts only with this repo's tag.
        # GitHub names ignore case, so the slug compare does too.
        ours = lambda t: repo_tag_names(t, slug)
        # One filtered list feeds both tag readings, so the archived and repo filters cannot drift apart.
        tags = [t for r in sessions if r["session_status"] != ARCHIVED_SESSION and any(map(ours, r.get("tags") or []))
                for t in r.get("tags") or [] if isinstance(t, str)]
        session_steps = sorted({t[len(STEP_TAG):] for t in tags if t.startswith(STEP_TAG)})
        lane_tags = sorted({t for t in tags if t.startswith((TOPIC_TAG, BUILD_TAG))})
        lane_sessions = [{"id": r["id"], "session_status": r["session_status"], "tags": r.get("tags") or [],
                          "status_bucket": r.get("status_bucket") if isinstance(r.get("status_bucket"), str) else None}
                         for r in sessions]
        if len(skipped) > before:
            why.append("unknown (%d session rows skipped)" % (len(skipped) - before))
    if pulls_skipped:
        why.append("unknown (%d pull rows skipped)" % pulls_skipped)
        pull_why = pull_why or why[-1]
    stale_why = why[0] if why else None
    page_items, items_why = None, None
    if read_why:
        items_why = read_why
    elif not isinstance(raw.get("items"), list):
        items_why = ITEMS_MISSING_WHY
    elif not all(isinstance(r, dict) and type(r.get("n")) is int and isinstance(r.get("status"), str)
                 and isinstance(r.get("home"), str) and (r.get("lane") is None or isinstance(r["lane"], str))
                 for r in raw["items"]):
        items_why = "unknown (an items row has the wrong shape)"
    else:
        # A row's `lane` (where its answer went, str or null) and `owner` are copied only when the file has the key, so
        # a publisher that does not send `lane` reads unknown in stalled_items, never "no lane".
        page_items = [dict({"n": r["n"], "status": r["status"], "home": r["home"]},
                           **{k: r[k] for k in ("lane", "owner") if k in r}) for r in raw["items"]]
    return {"read": read, "threads": threads, "pulls": sorted(pulls, key=lambda r: r["number"]),
            "branches": branches, "skipped": skipped, "strays": strays,
            "sessionSteps": session_steps, "laneTags": lane_tags, "staleWhy": stale_why, "pullWhy": pull_why,
            "pageItems": page_items, "itemsWhy": items_why, "laneSessions": lane_sessions, "closedPulls": closed_pulls}


def live_age_minutes(read):
    """Whole minutes since the ISO time `read`, or None when it has no time zone."""
    at = datetime.datetime.fromisoformat(read.replace("Z", "+00:00"))
    if at.tzinfo is None:
        return None
    return int((datetime.datetime.now(datetime.timezone.utc) - at).total_seconds() // 60)


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


MARK_OPEN, MARK_CLOSE = "<!-- roadmap:data -->", "<!-- /roadmap:data -->"


def render_block(data, info):
    """Only the marked data block of the one page: the two globals the Status tab reads, never ROADMAP_DB.
    The page writer splices it into the live page (skills/waiting-page/splice.py)."""
    return "%s\n<script>window.ROADMAP_DATA = %s; window.ROADMAP_BUILD = %s;</script>\n%s\n" % (
        MARK_OPEN, as_script(data), as_script(info), MARK_CLOSE)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bake a repo's roadmap into one read-only page.")
    ap.add_argument("--repo", default=".", help="the checkout to read (default: the current folder)")
    ap.add_argument("--record-branch", default=None,
                    help="the branch that holds roadmap/data/ (default: the checkout's record-branch key, else roadmap)")
    ap.add_argument("--main-branch", default="main", help="the branch whose merges carry Step: trailers")
    ap.add_argument("--live", help="the publisher's live-work file: project threads, open pull requests and branches")
    ap.add_argument("--out", help="the page to write; needed unless the checkout stands on the record branch")
    ap.add_argument("--block", action="store_true",
                    help="write only the roadmap data block (needs --out), for the page writer to splice in")
    args = ap.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    if args.record_branch is None:
        args.record_branch = default_record_branch(repo)
    source, why = record_source(repo, args.record_branch)
    if args.block and not args.out:
        raise SystemExit("--block writes the data block to a file, so name it with --out FILE.")
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
    info["live"] = live_work(args.live, data["steps"] if data else None, slug)
    info["stalled"] = (stalled(data["steps"], marks, info["live"]) if data else
                       {"why": "unknown (steps unknown)", "steps": None, "paused": [], "badPause": [],
                        "items": None, "itemsWhy": "unknown (steps unknown)"})
    info["panels"].append({"name": "Live work", "home": "project threads and GitHub" if args.live else None,
                           "read": info["live"]["read"]})
    info["panels"].insert(1, {"name": "Merges", "home": ref or args.main_branch,
                              "read": "unknown (%s)" % unread if unread else short(repo, ref) or "unknown (git could not name the commit)"})
    info["ready"] = (ready_steps(data["steps"], info["live"]) if data else
                     {"why": "unknown (steps unknown)", "steps": None})
    out.write_text(render_block(data, info) if args.block else render(data, info), encoding="utf-8")
    if data is None:
        print(f"{out.name}: steps unknown ({why})")
        print("%s: unknown (steps unknown)" % PAIR_LINE)
        print("\n".join(stalled_lines(info["stalled"])))
        print("\n".join(ready_lines(info["ready"])))
        return
    print(f"{out.name}: {len(data['steps'])} steps, {len(data['topics'])} topics, {len(data['meta'])} meta")
    pairs = todo_pairs(data["steps"], info["live"])
    if pairs is None:
        print("%s: %s" % (PAIR_LINE, pair_why(info["live"])))
    for k, number in pairs or []:
        print("%s: %s (#%d)" % (PAIR_LINE, k, number))
    misses, unread_files = mockup_misses(repo, data["steps"])
    for sid, mid in misses:
        print("%s: %s %s (%s)" % (MOCKUP_LINE, sid, mid, MOCKUP_REMEDY))
    for sid, mid, why in unread_files:
        print("%s: %s %s (%s)" % (MOCKUP_UNREAD_LINE, sid, mid, why))
    upkeep(data["steps"], added_at(source), marks, strays if not unread else ["unknown (%s)" % unread], info["live"],
           slug, repo, args.main_branch, unread)
    lines = stalled_lines(info["stalled"])
    if lines:
        print("\n".join(lines))
    lines = ready_lines(info["ready"])
    if lines:
        print("\n".join(lines))
    if pairs or misses or info["stalled"]["steps"] or info["stalled"]["items"]:
        raise SystemExit(1)


def mockup_cites(step):
    """The mockup ids a step's note, why and ask cite, lowercased, in first-cited order, each once."""
    found = []
    for field in MOCKUP_TEXT:
        text = step.get(field)
        for hit in MOCKUP_ID.findall(text) if isinstance(text, str) else []:
            if hit.lower() not in found:
                found.append(hit.lower())
    return found


def cat_check(repo, asks, follow=False):
    """[(objectname, objecttype) or None, one per ask in order] from one `git cat-file --batch-check` fed the asks
    (`<rev>:<path>`, no line break) on stdin. An ask git reports missing or ambiguous is None, and so, with `follow`
    (--follow-symlinks), is a link git cannot resolve to an object. The whole result is None when git fails or
    prints a record this does not know, so a failed read is never read as an absent file."""
    out = git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype)", *(["--follow-symlinks"] if follow else []),
              stdin="".join(ask + "\n" for ask in asks))
    if out is None:
        return None
    lines, rows = iter(out.split("\n")), []
    for ask in asks:
        line = next(lines, None)
        found = CAT_FOUND.fullmatch(line) if line is not None else None
        word, _, size = (line or "").partition(" ")
        if found:
            rows.append((found[1], found[2]))
        elif line in (ask + " missing", ask + " ambiguous"):
            rows.append(None)
        elif follow and word in CAT_LINK_WORDS and size.isdigit() and next(lines, None) is not None:
            rows.append(None)  # the record's second line names the link's target or the ask
        else:
            return None
    return rows if not any(lines) else None


def mockup_on_origin(repo, rels):
    """{rel: (state, why)} for design-folder files, each named by its checkout path as git names it: "ok" when some
    origin ref holds it as a file, "miss" when origin is readable and none does, "unknown" with the reason when it
    cannot tell. Origin is every remote-tracking ref under refs/remotes/origin/, as a fetch leaves them (an open PR's
    branch counts); the checkout's own files do not. A folder, a link or a submodule at the path is no file: the type
    read finds no blob there, or the link read resolves the blob to another object. A failed read, no origin ref, or
    a shallow checkout is unknown, never a miss or a pass. Cost: at most four git processes for all the files and
    refs (the ref listing, the shallow check, one batched type read, and one batched link read when some ref holds a
    blob at a path). The one home of the origin check (decision mockup-home)."""
    def every(state, why, among):
        return {rel: (state, why) for rel in among}
    if not rels:
        return {}
    refs = git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes/origin/")
    shallow = git(repo, "rev-parse", "--is-shallow-repository")
    if refs is None or shallow is None:
        return every("unknown", "the checkout could not be read", rels)
    if shallow.strip() == "true":
        return every("unknown", "a shallow checkout cannot show origin's files", rels)
    present = refs.split()
    if not present:
        return every("unknown", "no origin ref", rels)
    verdict = every("unknown", "the path holds a line break, which a batched git read cannot carry",
                    [rel for rel in rels if "\n" in rel or "\r" in rel])
    asks = [(rel, "%s:%s" % (ref, rel)) for rel in rels if rel not in verdict for ref in present]
    types = cat_check(repo, [ask for _, ask in asks])
    if types is None:
        verdict.update(every("unknown", "origin's files could not be read", [rel for rel, _ in asks]))
        return verdict
    blobs = [(rel, ask, row) for (rel, ask), row in zip(asks, types) if row and row[1] == "blob"]
    followed = cat_check(repo, [ask for _, ask, _ in blobs], follow=True) if blobs else []
    # A file resolves to its own blob when links are followed; a link resolves to its target, or to no object.
    held = {rel for (rel, _, row), again in zip(blobs, followed or []) if again == row}
    unread = {rel for rel, _, _ in blobs} if followed is None else set()
    for rel, _ in asks:
        if rel in held:
            verdict[rel] = ("ok", "")
        elif rel in unread:
            verdict[rel] = ("unknown", "origin's files could not be read")
        else:
            verdict[rel] = ("miss", "")
    return verdict


def mockup_state(repo, layout, file):
    """(state, detail) for one `mockups` entry, read with no process. state is "miss" for a path outside the design
    folder (a machine-home path, a link), "unknown" with detail as the reason for a layout that cannot be read (a
    malformed extras file) or a file outside the checkout, never a raise, and "origin" with detail as the file's
    checkout path as git names it, for mockup_on_origin to judge; the checkout's own file does not count."""
    try:
        found, _ = layout.mockup_file(str(repo), file)
    except Exception as err:  # a fault in the shared layout reads unknown
        return "unknown", "the layout could not be read: %s" % err
    if not found:
        return "miss", ""
    rel = os.path.relpath(found, str(repo)).replace(os.sep, "/")
    if rel == ".." or rel.startswith("../"):
        return "unknown", "the file is outside the checkout"
    return "origin", rel


def mockup_misses(repo, steps):
    """([(step id, mockup id)], [(step id, mockup id, why)]): each cited mockup id that has no file, and each whose
    file could not be read here. Only open steps (status not done) are judged. A step with no cited id holds none. The layout failing to load reads every cited
    id as unknown."""
    cites = {sid: mockup_cites(step) for sid, step in sorted(steps.items())
             if isinstance(step, dict) and step.get("status") != "done"}
    if not any(cites.values()):
        return [], []
    try:
        sys.path.insert(0, str(LINT))
        import layout
    except Exception as err:  # the layout is a shared file; a fault in it makes every file unknown
        return [], [(sid, mid, "the layout could not be read: %s" % err) for sid, ids in cites.items() for mid in ids]
    finally:
        if str(LINT) in sys.path:
            sys.path.remove(str(LINT))
    judged = []
    for sid, ids in cites.items():
        entries = steps[sid].get("mockups")
        entries = {str(k).lower(): v for k, v in entries.items()} if isinstance(entries, dict) else {}
        for mid in ids:
            judged.append((sid, mid, *(mockup_state(repo, layout, entries.get(mid)) if mid in entries else ("miss", ""))))
    # Origin is read once for every entry the layout sends to it, so the cost does not grow with the entries.
    on_origin = mockup_on_origin(repo, list(dict.fromkeys(detail for _, _, state, detail in judged if state == "origin")))
    misses, unread = [], []
    for sid, mid, state, detail in judged:
        if state == "origin":
            state, detail = on_origin[detail]
        if state == "miss":
            misses.append((sid, mid))
        elif state == "unknown":
            unread.append((sid, mid, detail))
    return misses, unread


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


def is_feel(d):
    """A step is a feel-fix unless `feel` is absent, false or null; a misread value keeps it open, never closes it."""
    feel = d.get("feel")  # identity tests: 0 == False in Python, and 0 is a misread value
    return feel is not None and feel is not False


def device_check(d):
    """"none" (absent or null), "valid" (how is simulator or device, at is an ISO time with a zone), or "bad"."""
    check = d.get("deviceCheck")
    if check is None:
        return "none"
    if not isinstance(check, dict) or check.get("how") not in ("simulator", "device") or not isinstance(check.get("at"), str):
        return "bad"
    try:
        zoned = datetime.datetime.fromisoformat(check["at"].replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        zoned = False
    return "valid" if zoned else "bad"


def names_step(pull, sid):
    """True when the pull's branch is the step id, or its title holds the id as a whole token, ignoring case.
    An empty id names nothing."""
    if not sid:
        return False
    if pull.get("branch") == sid:
        return True
    edge = "[A-Za-z0-9_-]"
    return re.search("(?<!%s)%s(?!%s)" % (edge, re.escape(sid), edge), pull["title"], re.I) is not None


def live_why(work):
    """Why the live read is unknown (no file, unreadable, stale, no sessions list), or None when it can be used."""
    work = work or {"read": "unknown (no --live file)"}
    return work["staleWhy"] if "staleWhy" in work else work["read"]


def pair_why(work):
    """Why the red pair line is unknown, or None. It reads readAt and pulls only: a missing sessions list or a bad
    session row must not mute it."""
    work = work or {"read": "unknown (no --live file)"}
    return work["pullWhy"] if "pullWhy" in work else work["read"]


def todo_pairs(steps, work):
    """(id, pull number) for each todo step that an open pull names, or None when the pulls read is unknown."""
    if pair_why(work):
        return None
    return [(k, p["number"]) for k, d in sorted(steps.items()) if d.get("status") in TODO_STATUS
            for p in work["pulls"] if names_step(p, k)]


def zoned_time(value):
    """`value` as an aware datetime, or None when it is not a string or not ISO with a zone. device_check keeps an older copy of this parse."""
    try:
        at = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return at if at.tzinfo else None


def created_at(pull):
    """The pull's createdAt as an aware datetime, or None when missing, not a string, or not ISO with a zone."""
    return zoned_time(pull.get("createdAt"))


def stale_drafts(work):
    """Entries for each draft pull older than STALE_DRAFT_HOURS at the live read with no live lane, or one unknown entry."""
    why = live_why(work)
    if why:
        return [why]
    read = datetime.datetime.fromisoformat(work["read"].replace("Z", "+00:00"))
    out = []
    for p in work["pulls"]:
        # A lane here is a live session step equal to the bare branch. unlaned also counts a lane/<id> branch.
        if p.get("draft") is not True or (p.get("branch") and p["branch"] in work["sessionSteps"]):
            continue
        at = created_at(p)
        if at is None:
            out.append("unknown (#%d has no createdAt)" % p["number"])
        elif (read - at).total_seconds() > STALE_DRAFT_HOURS * 3600:
            out.append("#%d (%s)" % (p["number"], p.get("branch") or p["title"]))
    return out


def lane_live(work, lane, item=False):
    """True when `lane` has live work: a live session of this repo carries cs-step:<lane>, or an open pull's branch
    is `<lane>` or `lane/<lane>`. An item's lane (`item=True`, a waiting-page item's answer route) is also live on
    cs-topic:<lane> and cs-build:<lane>, so a topic lane or a tier such as batch-runner counts. A step never is: a
    topic session does not work one step, and every lane session carries cs-build:lane. The caller has checked
    live_why(work) first."""
    tags = work["laneTags"]
    return (lane in work["sessionSteps"] or (item and (TOPIC_TAG + lane in tags or BUILD_TAG + lane in tags))
            or any(p.get("branch") in lane_head_refs(lane) for p in work["pulls"]))


def laneless(open_, marks, work):
    """(why, [(id, fix)]): each doing or active step with no live lane and no open PR, in step order. `why` is the
    reason the live read is unknown, else None, and then the list is the answer. `fix` is "todo", or the landed
    marks (a list of "#N") when the step landed on main. A step with an unknown status is never listed here."""
    why = live_why(work)
    if why:
        return why, []
    out = []
    for k, d in open_:
        if d.get("status") in RUNNING_STATUS and not lane_live(work, k):
            if k in marks and is_feel(d) and device_check(d) != "valid":
                continue  # the device row lists it; it must not read "set to done" before a device check
            out.append((k, marks[k] if k in marks else "todo"))
    return None, out


def unlaned(open_, marks, work):
    """Entries for each doing or active step with no live session and no open PR, or one unknown entry."""
    why, rows = laneless(open_, marks, work)
    if why:
        return [why]
    fix = dict(rows)
    out = []
    for k, d in open_:
        status = d.get("status")
        if status not in KNOWN_STATUS:
            out.append('%s (unknown status "%s")' % (k, status))
        elif k in fix:
            out.append("%s (set to todo)" % k if fix[k] == "todo"
                       else "%s (set to done: landed in %s)" % (k, ", ".join(fix[k])))
    return out


def open_steps(steps):
    """(id, step) for each step not done, in step order."""
    return sorted(((k, d) for k, d in steps.items() if d.get("status") != "done"),
                  key=lambda kd: kd[1].get("order", 1e9))


def pause_why(step):
    """None when the step's `paused` field is a valid disposition, else what is wrong with it. Triage writes it:
    {"why": non-empty text, "decides": owner|coordinator|triage, "at": ISO with a zone, "by": "triage"}."""
    p = step.get("paused")
    if not isinstance(p, dict):
        return "paused is not an object"
    if not (isinstance(p.get("why"), str) and p["why"].strip()):
        return "paused has no why"
    if p.get("decides") not in PAUSE_DECIDES:
        return "paused.decides is not one of %s" % ", ".join(PAUSE_DECIDES)
    if zoned_time(p.get("at")) is None:
        return "paused.at is not an ISO time with a zone"
    if p.get("by") != "triage":
        return "paused.by is not triage"
    return None


def stalled_items(work):
    """([{"n", "lane"}], None) for the open waiting-page items whose lane has no live work, else (None, why). An
    open item whose row has no `lane` key reads unknown, never zero: the publisher has not said where its answer
    went. A null lane names no lane and is never stalled."""
    why = live_why(work) or (work or {}).get("itemsWhy")
    if why:
        return None, why
    rows = work["pageItems"]
    if any(r["status"] != "closed" and "lane" not in r for r in rows):
        return None, "unknown (an open items row has no lane key)"
    return [{"n": r["n"], "lane": r["lane"]} for r in rows
            if r["status"] != "closed" and r["lane"] and not lane_live(work, r["lane"], item=True)], None


def stalled(steps, marks, work):
    """The page's stalled block: {"why", "steps", "paused", "badPause", "items", "itemsWhy"}.
    `steps` is a list of {"id", "fix"}, or None only when `why` says the live read is unknown, never [].
    A step with a valid `paused` field moves to `paused` (ids); a wrong-shaped one stays stalled and is listed in
    `badPause`. `items` is the open waiting-page items whose lane has no live work, or None with `itemsWhy`."""
    why, rows = laneless(open_steps(steps), marks, work)
    out = {"why": why, "steps": None if why else [], "paused": [], "badPause": []}
    for k, fix in rows:
        if "paused" in steps[k]:
            bad = pause_why(steps[k])
            if bad is None:
                out["paused"].append(k)
                continue
            out["badPause"].append({"id": k, "why": bad})
        out["steps"].append({"id": k, "fix": fix})
    out["items"], out["itemsWhy"] = stalled_items(work)
    return out


def stalled_lines(block):
    """The lines the build prints for a stalled block, each beginning STALLED_LINE. An unknown read prints an
    unknown line and no entry, so it never reads as a stall (verification-report-unknown-reads)."""
    out = []
    if block["steps"] is None:
        out.append("%s: %s" % (STALLED_LINE, block["why"]))
    for s in block["steps"] or []:
        out.append("%s: %s (%s)" % (STALLED_LINE, s["id"], "resume, pause or done" if s["fix"] == "todo"
                                    else "done: landed in %s" % ", ".join(s["fix"])))
    if block["items"] is None:
        out.append("%s: items %s" % (STALLED_LINE, block["itemsWhy"]))
    for i in block["items"] or []:
        out.append("%s: item %d (lane %s: re-route, close or resume)" % (STALLED_LINE, i["n"], i["lane"]))
    return out


def step_age(step, read):
    """Whole hours from the step's updatedAt to `read`, at least 0, or None when updatedAt is missing or not ISO with a zone."""
    at = zoned_time(step.get("updatedAt"))
    return None if at is None else max(0, int((read - at).total_seconds() // 3600))


def ready_steps(steps, work):
    """The page's ready block: {"why", "steps": [{"id", "age"}] | None}. A step is listed when its status is todo or
    ready, its phase is now, no live lane holds it, it has no valid `paused` field, and no open waiting-page item
    homed to it lacks a lane (an unanswered item). `steps` is None only when `why` says the read is unknown, never []."""
    _, why = stalled_items(work)  # live_why, then itemsWhy, then an open row with no lane key
    if why:
        return {"why": why, "steps": None}
    unanswered = {item_home(r) for r in work["pageItems"] if r["status"] != "closed" and not r["lane"]}
    read = datetime.datetime.fromisoformat(work["read"].replace("Z", "+00:00"))
    out = []
    for k, d in open_steps(steps):
        if (d.get("status") in TODO_STATUS and d.get("phase") == "now" and not lane_live(work, k)
                and pause_why(d) is not None and k not in unanswered):
            out.append({"id": k, "age": step_age(d, read)})
    return {"why": None, "steps": out}


def ready_lines(block):
    """The lines the build prints for a ready block. An unknown read prints one unknown line and no entry, never zero."""
    if block["steps"] is None:
        return ["%s: %s" % (READY_LINE, block["why"])]
    return ["%s: %s (%s)" % (READY_LINE, s["id"], "age unknown" if s["age"] is None else "%dh" % s["age"])
            for s in block["steps"]]


CLAIM = re.compile(
    r"(?<![\w-])(?i:finding|checked)(?![\w-])[^.\n]{0,40}?"  # any case; no letter, digit or hyphen touches it
    r"(?:(?P<iso>\d{4}-\d{2}-\d{2})(?!\d)|"
    r"(?P<md>(?P<mon>(?=[A-Z])(?i:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"  # capital first letter
    r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?))\s+(?P<day>\d{1,2})(?!\d)"
    r"(?:(?:,\s*|\s+)(?P<year>\d{4})(?!\d))?))")
MONTH_ABBR = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def dated_claims(open_, today):
    """Entries `<step> (<date as written>)` for each doing or active step whose newest dated claim is STALE_DAYS old."""
    out = []
    for k, d in open_:
        note = d.get("note")
        if d.get("status") not in RUNNING_STATUS or not isinstance(note, str):
            continue
        newest = None  # (date, as written)
        for m in CLAIM.finditer(note):
            try:
                if m.group("iso"):
                    when, text = datetime.date.fromisoformat(m.group("iso")), m.group("iso")
                else:
                    mon, day = MONTH_ABBR.index(m.group("mon")[:3].lower()) + 1, int(m.group("day"))
                    if m.group("year"):
                        when = datetime.date(int(m.group("year")), mon, day)
                    else:
                        when = datetime.date(today.year, mon, day)
                        if when > today:
                            when = datetime.date(today.year - 1, mon, day)
                    text = m.group("md")
            except ValueError:
                continue
            if newest is None or when > newest[0]:
                newest = (when, text)
        if newest and (today - newest[0]).days >= STALE_DAYS:
            out.append("%s (%s)" % (k, newest[1]))
    return out


def item_home(row):
    """The step id a waiting-page item row is homed to: its `home` without a leading `step `, in any case."""
    return re.sub(r"^step\s+", "", row["home"].strip(), flags=re.IGNORECASE)


def unfiled(steps, work):
    """Entries `<step> (page item <n>)` for each closed page item whose open home step never cites it, or one unknown entry."""
    work = work or {"read": "unknown (no --live file)"}
    if "itemsWhy" not in work:
        return [work["read"]]
    if work["itemsWhy"]:
        return [work["itemsWhy"]]
    out = []
    for row in work["pageItems"]:
        home = item_home(row)
        step = steps.get(home)
        if row["status"] != "closed" or step is None or step.get("status") == "done":
            continue
        cited = re.compile(r"\bitem\s+#?%d\b" % row["n"], re.IGNORECASE)
        words = " ".join(v for v in (step.get(key) for key in ("note", "why", "ask")) if isinstance(v, str))
        if not cited.search(words):
            out.append("%s (page item %d)" % (home, row["n"]))
    return out


def idle_lanes(work, steps, marks, slug, repo, main_branch="main", marks_why=None, trailer_ids=None):
    """Entries for each idle lane of this repo, sorted: `<session id> (<steps>; topic <topic or ->)` to archive, or
    `hold (<reason>; lane <session id>)` for a lane not to archive now: no cs-step tag, a step that is neither on the
    record branch nor named by a Step trailer on main, or a record-branch step whose `lane` is this session and that
    is still doing or active and not landed (this hold clears when the step moves or closes). A lane that waits (step
    not done, open pull, open item) has no line. `unknown (<why>)` is only for a whole read that could not run.

    A session is listed only when it carries cs-build:lane and this repo's cs-repo tag, is not archived, has status
    bucket completed or review ready, and names at least one cs-step with every one of them landed (a Step trailer
    on main, or status done, or a landed pull; a step off the record branch counts only by its trailer or a landed pull).
    A lane's pull set is the pulls on its steps' head refs (lane_head_refs) plus any pull, open or closed, whose body names
    the session id as a whole token (body_names_session). A pull is landed when it merged with its base the default branch,
    or its head sha is already in the default branch (`closedPulls` rows carry merged, base and head; open rows carry head).
    A step with a landed pull on its own head refs, or a landed body-named pull of the lane (which names no step, so it
    lands each step of the lane), is landed for the waiting gate. Only a landed pull on the step's own head refs (or a
    trailer, or status done) clears the "still doing under this lane" hold: a body-named pull does not. A lane is held back
    by an open pull in its set unless that pull is a draft whose head sha is already in the default branch; an open
    unlanded pull row with no `body` key (a live file from before the key) is read as naming every lane, so it holds them
    all. A closed pull that did not land neither holds nor lands. It is also held back by an open waiting-page item whose
    `lane` is one of its steps, or whose `owner` is the session itself (the item is the lane's own question); only
    status `closed` releases an item.

    Cost (rule outcomes-mechanize-rules): runs only on call; reads the live object it is given and the checkout's git: one
    `git merge-base` per distinct pull head that no row merged into the default branch already settles, plus the record
    branch and Step trailer reads. It writes no file and sets no timer. (`merge --idle-lanes --sessions` adds its own gh
    REST pages: all open pulls, closed pulls to the bound it states.) When no live
    lane row of this repo carries a SESSION_BUCKETS name, the list reads unknown. `marks_why` is landed_marks' why:
    when main could not be read, no step can be shown landed, so the list reads unknown. `trailer_ids` is the set of
    step ids named by a Step trailer on main; left out, it is read from main when a lane's step is off the record branch."""
    why = live_why(work)
    if why:
        return [why]
    if steps is None:
        return ["unknown (the steps could not be read)"]
    if not steps:
        return ["unknown (the record branch has no steps)"]
    if marks_why:
        return ["unknown (%s)" % marks_why]
    if work.get("pageItems") is None:
        return [work.get("itemsWhy") or "unknown (the page items could not be read)"]
    ref = main_ref(repo, main_branch)
    landed_heads = {}

    def in_main(pull):
        # A failed git read, or a head that is no sha, is not in main.
        head = pull.get("head")
        if not isinstance(head, str) or not re.fullmatch(r"[0-9a-fA-F]{7,64}", head) or not ref:
            return False
        if head not in landed_heads:
            landed_heads[head] = git(repo, "merge-base", "--is-ancestor", head, ref) is not None
        return landed_heads[head]

    def landed(pull):
        # The one home of the landed test: merged into the default branch (no git read), or its head already in it.
        return (pull.get("merged") is True and pull.get("base") == main_branch) or in_main(pull)

    def holds(pull):
        # An open pull holds its lane. Only a draft whose head is in main releases it (the archive guard's rule); a ready pull always holds.
        return not (pull.get("draft") is True and in_main(pull))

    open_pulls, closed_pulls = work["pulls"], work.get("closedPulls") or []

    open_items = [r for r in work["pageItems"] if r["status"] not in ITEM_DONE_STATUSES]
    # repo_tag_names takes the tag as the guard reads it, unstripped; the other tags are read stripped.
    ours = [row for row in work.get("laneSessions") or []
            if LANE_TAG in [t.strip() for t in row["tags"] if isinstance(t, str)]
            and any(repo_tag_names(t, slug) for t in row["tags"])]
    live = [row for row in ours if row["session_status"] != ARCHIVED_SESSION]
    if live and not any(row.get("status_bucket") in SESSION_BUCKETS for row in live):
        return ["unknown (no live lane session row carries a status_bucket enum name)"]
    out = []
    for row in ours:
        tags = [t.strip() for t in row["tags"] if isinstance(t, str)]
        if row["session_status"] == ARCHIVED_SESSION or row.get("status_bucket") not in IDLE_BUCKETS:
            continue
        sid = row["id"]
        mine = sorted({t[len(STEP_TAG):].strip() for t in tags if t.startswith(STEP_TAG)} - {""})
        if not mine:
            # The archive guard (hooks/guard_merge.py) refuses a lane with no cs-step tag, so archiving is not the act.
            out.append("hold (no cs-step tag; lane %s)" % sid)
            continue
        body_landed = any(landed(p) for p in (*open_pulls, *closed_pulls) if body_names_session(p.get("body"), sid))

        def by_own_pull(k):
            return any(landed(p) for p in (*open_pulls, *closed_pulls) if p.get("branch") in lane_head_refs(k))

        def by_pull(k):
            # The waiting gate and the absent-step proof accept a body-named landed pull; the doing hold below takes only a pull on the step's own head refs.
            return body_landed or by_own_pull(k)

        absent = [k for k in mine if k not in steps and not by_pull(k)]
        if absent and trailer_ids is None:
            found = step_trailers(repo, ref) if ref else None
            if found is None:
                return ["unknown (the Step trailers on %s could not be read)" % (ref or main_branch)]
            trailer_ids = {t[0] for t in found}
        unproven = [k for k in absent if k not in trailer_ids]
        if unproven:
            others = sorted({t for t in tags if t.startswith(REPO_TAG) and not repo_tag_names(t, slug)})
            out.append("hold (step %s not on the record branch and no Step trailer on main%s; lane %s)" % (
                " ".join(unproven), "; also tagged " + " ".join(others) if others else "", sid))
            continue
        if any(k in steps and steps[k].get("status") != "done" and k not in marks and not by_pull(k) for k in mine):
            continue
        heads = {name for k in mine for name in lane_head_refs(k)}
        # An open pull row with no `body` key (a live file from before the key) may name any lane, so it holds them all: fail closed.
        if any((p.get("branch") in heads or "body" not in p or body_names_session(p.get("body"), sid)) and holds(p) for p in open_pulls):
            continue
        if any(r.get("lane") in mine or r.get("owner") == sid for r in open_items):
            continue
        doing = sorted(k for k, d in steps.items()
                       if d.get("lane") == sid and d.get("status") in RUNNING_STATUS and k not in marks and not by_own_pull(k))
        if doing:
            out.append("hold (step %s still doing under this lane; lane %s)" % (" ".join(doing), sid))
            continue
        topic = next((t[len(TOPIC_TAG):].strip() for t in tags if t.startswith(TOPIC_TAG) and t[len(TOPIC_TAG):].strip()), "-")
        out.append("%s (%s; topic %s)" % (sid, " ".join(mine), topic))
    return sorted(out)


def idle_lanes_report(repo, live, record_branch=None, main_branch="main"):
    """The idle_lanes entries for the checkout `repo`, read as the build reads them (record branch, Step trailers on
    main, the repo's GitHub name, the live file). `merge --idle-lanes` calls this. A read that could not run is one
    `unknown (<why>)` entry, never an empty list."""
    repo = pathlib.Path(repo).resolve()
    source, why = record_source(repo, record_branch or default_record_branch(repo))
    if source is None:
        return ["unknown (%s)" % why]
    steps = load(source)["steps"]
    marks, _strays, unread = landed_marks(repo, main_ref(repo, main_branch), main_branch, steps)
    extra, _where = extras(repo, source)
    slug = github_slug(repo, extra)
    return idle_lanes(live_work(live, steps, slug), steps, marks, slug, repo, main_branch, unread)


def upkeep(steps, added, marks, strays, work=None, slug=None, repo=None, main_branch="main", unread=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    open_ = open_steps(steps)
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
        at = zoned_time(d.get("updatedAt"))
        if at is None or (now - at).days >= STALE_DAYS:
            stale.append(k)
    jumped = [k for k, d in open_[:TOP]
              if k in added and (now - added[k]).total_seconds() < 86400
              and "Placed ahead of" not in (d.get("note") or "")]
    if not added:
        jumped = ["unknown (git log could not run)"]
    waiting, closing = [], []
    for k, v in sorted(marks.items()):
        d, got = steps[k], ", ".join(v)
        if not is_feel(d):
            closing.append("%s (%s)" % (k, got))
        elif device_check(d) == "valid":
            closing.append("%s (%s; open a try-it item)" % (k, got))
        else:
            waiting.append("%s (%s%s)" % (k, got, "; device trial unreadable" if device_check(d) == "bad" else ""))
    ready = [k for k, d in open_ if d.get("status") in TODO_STATUS and READY_SENTENCE.search(d.get("note") or "")]
    rows = [("notes over %d words" % NOTE_WORDS, long_), ("untouched %d days in a live phase" % STALE_DAYS, stale),
            ("no note in a live phase", empty), ("new in top %d with no placement line" % TOP, jumped),
            ("in progress with no live lane or open PR", unlaned(open_, marks, work)),
            ("ready todo steps", ready),
            ("draft PRs over %d h with no live lane" % STALE_DRAFT_HOURS, stale_drafts(work)),
            ("dated claims to re-check before a lane starts", dated_claims(open_, now.date())),
            ("page rulings not on their step", unfiled(steps, work)),
            (IDLE_LANES_LINE, idle_lanes(work or {"read": "unknown (no --live file)"}, steps, marks, slug, repo, main_branch, unread)
             if repo is not None else ["unknown (the checkout was not named)"]),
            ("landed, waiting for a device trial", waiting),
            ("landed, waiting for triage to close", closing),
            ("Step trailers naming no step", strays),
            ("live threads naming no open step", (work or {}).get("strays", [])),
            ("live file entries skipped", (work or {}).get("skipped", []))]
    # A hold line is shown, never counted as a lane to archive.
    print("upkeep: " + "; ".join(
        f"{label}: {len([x for x in v if not (label == IDLE_LANES_LINE and x.startswith('hold ('))])}" for label, v in rows))
    for label, v in rows:
        if v:
            print(f"  {label}: {', '.join(v)}")


if __name__ == "__main__":
    main()
