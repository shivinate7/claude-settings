#!/usr/bin/env python3
"""The one runner of the prose-tending contract (decision prose-tending-contract). Standard library only.

    python3 lint/tending.py --point <merge-check|stop|compact|triage-status> [--store NAME] [--root DIR]

lint/layout.json, key "tending" (read by layout.tending()), holds one entry per prose store:
  where       a layout kind, or external:<name> for a store outside the repo
  item        a regex; group 1 is the item's id; it is matched against one line at a time
  still-true  the name of one test in TESTS: home-held, until-date, cite-resolves or copy-matches-live
  close       mark (append " [closed]" to a stale item's line), delete (drop the line) or none (report only)
  runs-from   a subset of POINTS: the call points that run the store
  state       live, or declared (named, but no call point runs it yet)

tend(entry, text, root) gives {id: "true" | "stale" | "unknown"}. A claim that cannot be read is "unknown", never
"true" (rule verification-report-unknown-reads). A line that holds no claim the test reads is "unknown" too.
An item already marked [closed] gets no verdict. close(entry, text, verdicts) gives the rewritten text; it marks by
the verdict of an id, so a caller that must tell two lines of one id apart uses the command line's per-line close.

The command line reads each live store that runs from the point. At merge-check it writes nothing and exits 1 for
each stale item, whatever the close step. At stop, compact and triage-status it closes the stale items its close
step can and writes a store file only when its text changed; it exits 1 for a stale item that close "none" cannot fix,
for a live store whose file is missing, and for a malformed contract. A file it cannot read, an item that cannot be
judged and a bullet line the item regex misses (`shape`) print as `unknown <store>: <why>` and never fail the point.
A declared store is never read.

An external:<name> store is outside the repo, so the runner reads no file for it: the caller supplies the text to
tend() and close(). Asked for by --store at a point with no text, it prints `unknown <store>: caller supplies text`.

Reuse: the home test resolves a home as hooks/ruling_home.py does (its whole-value read, `_unwrap`, the refusal of an
absolute or leaving path) and a step home as hooks/feedback_guard.py does (STEP_HOME, STEP_PATH). It calls the
resolver's two git reads itself, not value_resolves, because value_resolves lists the refs on each call and a run here
lists them once. The [closed] token is feedback_guard.CLOSED_TOKEN. These modules are imported on first use, and
importing them starts no process or thread.

Cost: importing this file starts no process, thread or timer. A call point imports it in the process it already runs.
A run reads the store files and, for home-held, one for-each-ref and one cat-file per distinct home, through
hooks/ruling_home.py, the one home of "some ref's tree holds this file". It writes only a store file whose text
changed, and never at merge-check.
"""
import argparse
import datetime
import os
import posixpath
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
for _folder in (HERE, os.path.join(HERE, "..", "hooks")):
    if _folder not in sys.path:
        sys.path.append(_folder)  # append: a hook's name never shadows a module already loaded
import layout  # noqa: E402  the one reader of lint/layout.json

POINTS = ("merge-check", "stop", "compact", "triage-status")
CLOSING_POINTS = ("stop", "compact", "triage-status")  # merge-check never writes: a merge check that rewrites a tree edits what it reads
CLOSES = ("mark", "delete", "none")
STATES = ("live", "declared")
FIELDS = ("where", "item", "still-true", "close", "runs-from", "state")
EXTERNAL = "external:"
TRUE, STALE, UNKNOWN = "true", "stale", "unknown"
MARK = "[closed]"
HOME = re.compile(r"\bHome:\s*(.+?)\s*$")  # the whole rest of the line, as ruling_home.HOME_RE reads a home
BULLET = re.compile(r"\s*[-*+]\s")
BULLET_ITEM = re.compile(r"\^?[-*+] ")  # an item regex that starts with a bullet, so a bullet line it misses has the wrong shape
UNTIL = re.compile(r"\buntil:?\s*(\d{4}-\d{2}-\d{2})", re.I)
CITE = re.compile(r"\bcites\s+(\S+)")
RECORD_ID = re.compile(r"[A-Za-z0-9_-]+")
COPY = re.compile(r"\bcopy of (\S+?):\s(.*?)\s*$")
TRAILING = ".,;:)"


def _closed():
    """The [closed] token pattern feedback_guard reads, the one home of that token."""
    return _hook("feedback_guard").CLOSED_TOKEN


def _hook(name):
    """A hooks/ module, imported on first use so importing this file reads nothing."""
    return __import__(name)


class _Reads:
    """What one tend() call has read, so no item repeats a read."""

    def __init__(self, root):
        self.root = root
        self._refs = False  # False: not read yet. None: git cannot read the repo.
        self._held = {}

    def refs(self):
        """Every branch ref of the repo at root, or None when git cannot read it."""
        if self._refs is False:
            home = _hook("ruling_home")
            self._refs = None
            if home.is_git_work_tree(self.root):
                try:
                    self._refs = home._list_refs(self.root)
                except home._GitFailure:
                    pass
        return self._refs

    def held(self, git_path):
        """True or False: some ref's tree holds a blob at git_path. None: git could not be read."""
        if git_path not in self._held:
            refs = self.refs()
            if refs is None:
                self._held[git_path] = None
            else:
                home = _hook("ruling_home")
                try:
                    self._held[git_path] = home._resolve_value(self.root, refs, git_path)
                except home._GitFailure:
                    self._held[git_path] = None
        return self._held[git_path]


def _clean(word):
    return word.rstrip(TRAILING).strip("`'\"").rstrip(TRAILING)


def _home_held(line, reads):
    found = HOME.search(line)
    if not found:
        return UNKNOWN
    home, guard = _hook("ruling_home"), _hook("feedback_guard")
    value = home._unwrap(found.group(1))
    if value == home.PROCESS_ONLY:
        return TRUE
    step = guard.STEP_HOME.fullmatch(value)
    if step:
        value = guard.STEP_PATH % step.group(1)
    normalized = os.path.normpath(value)
    if os.path.isabs(value) or normalized in (".", "..") or normalized.startswith(".." + os.sep):
        return STALE  # a home outside the repo never counts, as ruling_home.value_resolves reads it
    held = reads.held(normalized.replace(os.sep, "/"))
    return UNKNOWN if held is None else TRUE if held else STALE


def _until_date(line, reads):
    dates = UNTIL.findall(line)
    if not dates:
        return UNKNOWN
    today, verdict = datetime.date.today(), TRUE
    for text in dates:
        try:
            when = datetime.date.fromisoformat(text)
        except ValueError:
            return UNKNOWN
        if when < today:
            verdict = STALE
    return verdict


def _record_folders(root):
    return [os.path.join(root, *rel.split("/")) for rel in layout.candidates(root, "decisions")]


def _cite_resolves(line, reads):
    cites = [_clean(word) for word in CITE.findall(line)]
    if not cites:
        return UNKNOWN
    folders = [folder for folder in _record_folders(reads.root) if os.path.isdir(folder)]
    if not folders:
        return UNKNOWN
    for name in cites:
        if not RECORD_ID.fullmatch(name) or not any(os.path.isfile(os.path.join(f, name + ".md")) for f in folders):
            return STALE
    return TRUE


def _copy_matches_live(line, reads):
    found = COPY.search(line)
    if not found:
        return UNKNOWN
    rel = found.group(1).replace("\\", "/")
    path = posixpath.normpath(rel)
    if os.path.isabs(rel) or re.match(r"[A-Za-z]:", rel) or path == ".." or path.startswith("../"):
        return UNKNOWN
    try:
        with open(os.path.join(reads.root, *path.split("/")), encoding="utf-8", newline="") as handle:
            live = handle.read()
    except (OSError, ValueError):
        return UNKNOWN
    return TRUE if found.group(2) in [row.rstrip("\r") for row in live.split("\n")] else STALE


TESTS = {
    "home-held": _home_held,
    "until-date": _until_date,
    "cite-resolves": _cite_resolves,
    "copy-matches-live": _copy_matches_live,
}
RANK = {TRUE: 0, UNKNOWN: 1, STALE: 2}


def _match(item, line):
    """(id, body, carriage return) when the line holds an item, else None. The body is the line with "\\r" cut off."""
    body, cr = (line[:-1], "\r") if line.endswith("\r") else (line, "")
    found = item.search(body)
    if found is None or found.group(1) is None:
        return None
    return found.group(1), body, cr


def _scan(entry, text, root):
    """[(line index, id, verdict)] for each open item line of text, in order."""
    test = TESTS.get(entry["still-true"])
    if test is None:
        raise ValueError("no still-true test named %r" % (entry["still-true"],))
    item, reads, closed, found = re.compile(entry["item"], re.M), _Reads(root), _closed(), []
    for index, line in enumerate(text.split("\n")):
        hit = _match(item, line)
        if hit is not None and not closed.search(hit[1]):
            found.append((index, hit[0], test(hit[1], reads)))
    return found


def tend(entry, text, root):
    """{item id: verdict} for each open item in text. An id that repeats keeps its worst verdict."""
    found = {}
    for _, ident, verdict in _scan(entry, text, root):
        if ident not in found or RANK[verdict] > RANK[found[ident]]:
            found[ident] = verdict
    return found


def _rewrite(entry, text, wanted):
    """text with each item line closed for which wanted(line index, id) is true. Every other byte stays."""
    mode = entry["close"]
    if mode not in CLOSES:
        raise ValueError("no close step named %r" % (mode,))
    if mode == "none":
        return text
    item, closed, out = re.compile(entry["item"], re.M), _closed(), []
    for index, line in enumerate(text.split("\n")):
        hit = _match(item, line)
        if hit is not None and wanted(index, hit[0]):
            if mode == "delete":
                continue
            if not closed.search(hit[1]):
                line = hit[1].rstrip() + " " + MARK + hit[2]
        out.append(line)
    return "\n".join(out)


def close(entry, text, verdicts):
    """text with each item whose id has a stale verdict closed the way entry["close"] says."""
    return _rewrite(entry, text, lambda index, ident: verdicts.get(ident) == STALE)


def contract_problems(entries):
    """One line per way the contract is malformed, for every store, live or declared."""
    kinds = layout.layout()["kinds"]
    found = []
    for store, entry in entries.items():
        missing = [field for field in FIELDS if field not in entry]
        if missing:
            found.append("%s: lacks %s" % (store, ", ".join(missing)))
            continue
        where = entry["where"]
        if not isinstance(where, str) or not (where in kinds or (where.startswith(EXTERNAL) and len(where) > len(EXTERNAL))):
            found.append("%s: where %r is neither a layout kind nor external:<name>" % (store, where))
        if entry["still-true"] not in TESTS:
            found.append("%s: still-true %r names no test (%s)" % (store, entry["still-true"], ", ".join(TESTS)))
        if entry["close"] not in CLOSES:
            found.append("%s: close %r is not one of %s" % (store, entry["close"], ", ".join(CLOSES)))
        if entry["state"] not in STATES:
            found.append("%s: state %r is not one of %s" % (store, entry["state"], ", ".join(STATES)))
        points = entry["runs-from"]
        if not isinstance(points, list) or not points or any(point not in POINTS for point in points):
            found.append("%s: runs-from %r is not a list of call points from %s" % (store, points, ", ".join(POINTS)))
        try:
            if re.compile(entry["item"]).groups < 1:
                found.append("%s: item has no group for the id" % store)
        except (re.error, TypeError) as err:
            found.append("%s: item is no regex: %s" % (store, err))
    return found


def store_files(entry, root):
    """The files a store holds in the repo at root: a folder gives its .md files. FileNotFoundError, naming the
    store's path, when the repo holds neither the file nor the folder. The caller never asks for an external store."""
    for rel in layout.candidates(root, entry["where"]):
        full = os.path.join(root, *rel.split("/"))
        if os.path.isfile(full):
            return [full]
        if os.path.isdir(full):
            return sorted(os.path.join(folder, name) for folder, _, names in os.walk(full)
                          for name in names if name.endswith(".md"))
    raise FileNotFoundError(layout.path(root, entry["where"]))


def _shape_misses(entry, text):
    """Line numbers of bullet lines in text that the item regex misses, for an item regex that starts with a bullet."""
    if not BULLET_ITEM.match(entry["item"]):
        return []
    item = re.compile(entry["item"], re.M)
    return [number for number, line in enumerate(text.split("\n"), 1)
            if BULLET.match(line) and not item.search(line.rstrip("\r"))]


def _tend_point(store, entry, root, point):
    """(lines to print, whether the point fails) for one live store at a call point."""
    try:
        files = store_files(entry, root)
    except FileNotFoundError as err:
        return ["tending: FAIL: %s %s: the file is missing" % (store, err)], True
    lines, failed = [], False
    for path in files:
        shown = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as err:
            lines.append("tending: unknown %s: %s cannot be read: %s" % (store, shown, str(err).replace("\n", " ")))
            continue
        rows = _scan(entry, text, root)
        stale = [(index, ident) for index, ident, verdict in rows if verdict == STALE]
        unread = sum(1 for row in rows if row[2] == UNKNOWN)
        if unread:
            lines.append("tending: unknown %s: %s holds %d item(s) it could not judge" % (store, shown, unread))
        misses = _shape_misses(entry, text)
        if misses:
            lines.append("tending: unknown %s: shape, %s line(s) %s start like an item and match no item pattern"
                         % (store, shown, ", ".join(str(n) for n in misses[:5])))
        if point not in CLOSING_POINTS or entry["close"] == "none":
            failed = failed or bool(stale)
            lines.extend("tending: FAIL: %s %s: stale %s" % (store, shown, ident) for _, ident in stale)
            continue
        marked = {index for index, _ in stale}
        new = _rewrite(entry, text, lambda index, ident: index in marked)
        if new != text:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(new)
            lines.append("tending: %s %s: closed %s" % (store, shown, ", ".join(ident for _, ident in stale)))
    return lines, failed


def main(argv):
    parser = argparse.ArgumentParser(prog="tending.py", description="Tend each prose store that runs from a call point.")
    parser.add_argument("--point", required=True, choices=POINTS)
    parser.add_argument("--store")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        entries = layout.tending()
        problems = contract_problems(entries)
    except layout.LayoutError as err:
        print("tending: FAIL: %s" % err)
        return 1
    if args.store and args.store not in entries:
        problems.append("--store %s names no store in the contract" % args.store)
    for problem in problems:
        print("tending: FAIL: contract: %s" % problem)
    if problems:
        return 1
    failed = False
    for store, entry in entries.items():
        if args.store and store != args.store:
            continue
        if entry["state"] != "live" or args.point not in entry["runs-from"]:
            continue
        if entry["where"].startswith(EXTERNAL):
            if args.store:  # asked for by name: say why nothing was read, else the run is silent on it
                print("tending: unknown %s: caller supplies text" % store)
            continue
        lines, bad = _tend_point(store, entry, root, args.point)
        for line in lines:
            print(line)
        failed = failed or bad
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
