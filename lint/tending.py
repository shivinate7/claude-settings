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
An item already marked [closed] gets no verdict. close(entry, text, verdicts) gives the rewritten text.

The command line reads each live store that runs from the point, closes what its close step can, writes a store
file only when its text changed, and exits 1 for a stale item that close "none" cannot fix or for a malformed
contract. A declared store, and an external one, is never read here.

Cost: importing this file starts no process, thread or timer. A call point imports it in the process it already runs.
A run reads the store files and, for home-held, one for-each-ref and one cat-file per distinct home, through
hooks/ruling_home.py, the one home of "some ref's tree holds this file". It writes only a store file whose text
changed.
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
CLOSES = ("mark", "delete", "none")
STATES = ("live", "declared")
FIELDS = ("where", "item", "still-true", "close", "runs-from", "state")
EXTERNAL = "external:"
TRUE, STALE, UNKNOWN = "true", "stale", "unknown"
CLOSED_TOKEN = "[closed]"
CLOSED = re.compile(r"(?<!\S)\[closed\](?!\S)")  # as feedback_guard reads the token: a whole token, anywhere on the line

HOME = re.compile(r"\bHome:\s*(\S+)")
STEP_HOME = re.compile(r"step:([A-Za-z0-9_-]+)")
UNTIL = re.compile(r"\buntil:?\s*(\d{4}-\d{2}-\d{2})", re.I)
CITE = re.compile(r"\bcites\s+(\S+)")
RECORD_ID = re.compile(r"[A-Za-z0-9_-]+")
COPY = re.compile(r"\bcopy of (\S+?):\s(.*?)\s*$")
TRAILING = ".,;:)"


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
    word = _clean(found.group(1).split("#", 1)[0])
    home = _hook("ruling_home")
    if word == home.PROCESS_ONLY:
        return TRUE
    if word.startswith("step:"):
        step = STEP_HOME.fullmatch(word)
        if not step:
            return STALE
        word = _hook("override").STEP_DIR + step.group(1) + ".json"
    path = posixpath.normpath(word.replace("\\", "/"))
    if not word or os.path.isabs(word) or path == ".." or path.startswith("../") or path == ".":
        return STALE  # a home outside the repo never counts, as ruling_home.value_resolves reads it
    held = reads.held(path)
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


def tend(entry, text, root):
    """{item id: verdict} for each open item in text. An id that repeats keeps its worst verdict."""
    test = TESTS.get(entry["still-true"])
    if test is None:
        raise ValueError("no still-true test named %r" % (entry["still-true"],))
    item, reads, found = re.compile(entry["item"], re.M), _Reads(root), {}
    for line in text.split("\n"):
        hit = _match(item, line)
        if hit is None or CLOSED.search(hit[1]):
            continue
        verdict = test(hit[1], reads)
        if hit[0] not in found or RANK[verdict] > RANK[found[hit[0]]]:
            found[hit[0]] = verdict
    return found


def close(entry, text, verdicts):
    """text with each stale item closed the way entry["close"] says. Every other byte stays."""
    mode = entry["close"]
    if mode not in CLOSES:
        raise ValueError("no close step named %r" % (mode,))
    if mode == "none":
        return text
    item, out = re.compile(entry["item"], re.M), []
    for line in text.split("\n"):
        hit = _match(item, line)
        if hit is not None and verdicts.get(hit[0]) == STALE:
            if mode == "delete":
                continue
            if not CLOSED.search(hit[1]):
                line = hit[1].rstrip() + " " + CLOSED_TOKEN + hit[2]
        out.append(line)
    return "\n".join(out)


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
    """The files a store holds in the repo at root, or None for an external store. A folder gives its .md files."""
    if entry["where"].startswith(EXTERNAL):
        return None
    for rel in layout.candidates(root, entry["where"]):
        full = os.path.join(root, *rel.split("/"))
        if os.path.isfile(full):
            return [full]
        if os.path.isdir(full):
            return sorted(os.path.join(folder, name) for folder, _, names in os.walk(full)
                          for name in names if name.endswith(".md"))
    return []


def _tend_point(store, entry, root):
    """(lines to print, whether a stale item stays that close cannot fix) for one live store."""
    files = store_files(entry, root)
    if files is None:
        return ["tending: unknown, %s is outside the repo, so nothing was read" % store], False
    lines, failed = [], False
    for path in files:
        shown = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as err:
            lines.append("tending: unknown, %s %s cannot be read: %s" % (store, shown, err))
            continue
        verdicts = tend(entry, text, root)
        stale = sorted(ident for ident, verdict in verdicts.items() if verdict == STALE)
        unread = sum(1 for verdict in verdicts.values() if verdict == UNKNOWN)
        if unread:
            lines.append("tending: unknown, %s %s: %d item(s) not read" % (store, shown, unread))
        if entry["close"] == "none":
            failed = failed or bool(stale)
            lines.extend("tending: FAIL: %s %s: %s is stale" % (store, shown, ident) for ident in stale)
            continue
        new = close(entry, text, verdicts)
        if new != text:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(new)
            lines.append("tending: %s %s: closed %s" % (store, shown, ", ".join(stale)))
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
        lines, bad = _tend_point(store, entry, root)
        for line in lines:
            print(line)
        failed = failed or bad
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
