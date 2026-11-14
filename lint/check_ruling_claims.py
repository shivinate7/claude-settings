#!/usr/bin/env python3
"""Fails when text names an owner ruling that no record backs. Standard library only.

    python3 lint/check_ruling_claims.py [--base REF] [--root DIR] [--rulings-dir DIR] [file ...]
    python3 lint/check_ruling_claims.py [--root DIR] [--rulings-dir DIR] --brief FILE [FILE ...]

A session's own call has passed as an owner ruling. The mistake reached tests and code comments until a reviewer
found no record. This check reads the text, prose, comment or string alike, with no parser, so a claim cannot hide
in a string or after a lone quote. Two forms are claims:

    owner ruling <H:MM> [zone]     an optional 's after owner; the zone is read and ignored
    ruling <id>                    <id> is a kebab-case slug of two or more words

A time claim has a record when any of these holds that time (H:MM, a leading zero ignored, a zone ignored): a
decision record under the layout's decisions folder, CLAUDE.md, or a rulings entry (its `at` time or any text in
it). An id claim has a record when a decision file stem, a rulings entry `id` or a CLAUDE.md rule marker
(`<!-- rule:<id> -->`) equals it. A line that holds `no record: <reason>` passes, and the reason must be given.

Modes. Files named: every line of each. --brief: the same, for the files of a brief; a brief is read whole, never as
a diff. With neither, the lines the change adds against --base (default origin/main), in every file of the diff.

--rulings-dir reads the rulings entries from a folder of JSON files. Without it, entries come from
lint/ruled_store.py (`ruled_entries`, the folder roadmap/rulings on origin/roadmap of --root).

Exit: 0 clear, 1 an unbacked claim, 2 an input that cannot be read (named).

NAMED LIMIT. A record that a change adds in the same diff backs its own claim, so a decision record that files a ruling
needs no second record. The check cannot tell whether the owner said it; it checks that a record exists to read.

Cost: starts no process in file mode. Base mode starts two git processes (merge-base, diff). It reads the records
only when a claim is found, and writes nothing.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layout  # noqa: E402  the one home of where records live (lint/layout.json)
import ruled_store  # noqa: E402  the one reader of the rulings store

TIME_CLAIM = re.compile(r"\bowner(?:'s|’s)?\s+ruling\s+(\d{1,2}):(\d{2})(?!\d)(?:\s+([A-Za-z]{2,4})\b)?",
                        re.IGNORECASE)
ID_CLAIM = re.compile(r"\bruling\s+([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b")
NO_RECORD = re.compile(r"\bno record:\s*\S")
CLOCK = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:]|\d)")
AT_TIME = re.compile(r"T(\d{2}):(\d{2})")
MARKER = re.compile(r"<!--\s*rule:([a-z0-9][a-z0-9-]*)\s*-->")
HUNK = re.compile(r"^@@ -\S+ \+(\d+)")
NAME = "check_ruling_claims"


class Unreadable(Exception):
    """An input the check cannot read; the message names it."""


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            return f.read()
    except OSError as err:
        raise Unreadable("%s: cannot read: %s" % (path, err.strerror or err))


def claims_in(line):
    """[(kind, key, text)] for each claim on a line. kind is "time" (key (hour, minute)) or "id" (key the slug)."""
    found = []
    for m in TIME_CLAIM.finditer(line):
        found.append(("time", (int(m.group(1)), int(m.group(2))), m.group(0)))
    for m in ID_CLAIM.finditer(line):
        found.append(("id", m.group(1), m.group(0)))
    return found


def sparse_refused(lines):
    """[(line number, claim kind, key, claim text)] for each claim in a {line number: text} map, on a line with no
    `no record: <reason>`. A diff gives only its added lines, so each keeps its own number."""
    out = []
    for n in sorted(lines):
        if NO_RECORD.search(lines[n]):
            continue
        out.extend((n, kind, key, shown) for kind, key, shown in claims_in(lines[n]))
    return out


class Records:
    """What backs a claim. Reads each source once, on the first claim that needs it."""

    def __init__(self, root, rulings_dir):
        self.root, self.rulings_dir = root, rulings_dir
        self._times = self._ids = None

    def _decision_folders(self):
        """Each decisions folder the layout names for this root that exists (a repo not yet rolled out holds its
        records at the legacy path, the layout path may also exist)."""
        try:
            rels = layout.candidates(self.root, "decisions")
        except layout.LayoutError as err:  # a check that cannot find its records is unknown, never clear
            raise Unreadable("decisions folder: %s" % err)
        return [os.path.join(self.root, *rel.split("/")) for rel in rels]

    def _claude_md(self):
        try:
            rel = layout.path(self.root, "claude-md")
        except layout.LayoutError as err:
            raise Unreadable("CLAUDE.md path: %s" % err)
        return os.path.join(self.root, *rel.split("/"))

    def _entries(self):
        if self.rulings_dir is None:
            return ruled_store.ruled_entries(self.root)
        entries = []
        for path in sorted(glob.glob(os.path.join(self.rulings_dir, "*.json"))):
            try:
                body = json.loads(read_text(path))
            except ValueError:
                continue  # a store file that is not JSON backs nothing; lint/ruled_store.py check names it
            if isinstance(body, dict):
                entries.append(body)
        return entries

    @staticmethod
    def _clocks(text):
        return {(int(h), int(m)) for h, m in CLOCK.findall(text)}

    def _load(self):
        times, ids = set(), set()
        for folder in self._decision_folders():
            for path in glob.glob(os.path.join(folder, "*.md")):
                ids.add(os.path.splitext(os.path.basename(path))[0])
                times |= self._clocks(read_text(path))
        claude = self._claude_md()
        if os.path.isfile(claude):
            text = read_text(claude)
            times |= self._clocks(text)
            ids.update(MARKER.findall(text))
        for entry in self._entries():
            if isinstance(entry.get("id"), str):
                ids.add(entry["id"])
            at = entry.get("at")
            if isinstance(at, str):
                times |= {(int(h), int(m)) for h, m in AT_TIME.findall(at)}
            for field, value in entry.items():
                if field != "at" and isinstance(value, str):
                    times |= self._clocks(value)
        self._times, self._ids = times, ids

    def backs(self, kind, key):
        if self._times is None:
            self._load()
        return key in (self._times if kind == "time" else self._ids)


def git(root, *args):
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if done.returncode:
        raise Unreadable("git %s failed in %s: %s" % (" ".join(args), root, done.stderr.strip()))
    return done.stdout


def added_text(root, base):
    """{path: {line number: text}} for each line the change adds against base, in every file of the diff."""
    fork = git(root, "merge-base", base, "HEAD").strip()
    diff = git(root, "diff", "-U0", "--no-color", "--no-ext-diff", fork)
    added, path, header, line = {}, None, False, 0
    for row in diff.split("\n"):
        if row.startswith("diff --git "):
            path, header = None, True
        elif header and row.startswith("+++ "):
            path = None if row == "+++ /dev/null" else row[6:].split("\t")[0]
        elif (m := HUNK.match(row)):
            header, line = False, int(m.group(1))
        elif not header and row.startswith("+") and path:
            added.setdefault(path, {})[line] = row[1:]
            line += 1
    return added


def main(argv):
    ap = argparse.ArgumentParser(prog=NAME, description="Refuse a named owner ruling that no record backs.")
    ap.add_argument("--base", default="origin/main", help="the ref the change is read against (default origin/main)")
    ap.add_argument("--root", default=os.getcwd(), help="the checkout whose records back a claim")
    ap.add_argument("--rulings-dir", help="a folder of rulings JSON files, instead of the store on origin/roadmap")
    ap.add_argument("--brief", nargs="+", default=[], metavar="FILE", help="brief files, read whole")
    ap.add_argument("files", nargs="*", help="files read whole, with no git")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        if not os.path.isdir(root):
            raise Unreadable("%s: --root is not a folder" % args.root)
        if args.rulings_dir is not None and not os.path.isdir(args.rulings_dir):
            raise Unreadable("%s: --rulings-dir is not a folder" % args.rulings_dir)
        records = Records(root, args.rulings_dir)
        named = args.brief + args.files
        # Each unit is (name shown, {line: text}). A named file is read whole; a diff gives only its added lines.
        if named:
            units = []
            for name in named:
                text = read_text(name)
                units.append((name, dict(enumerate(text.split("\n"), 1))))
            scope = "the files named"
        else:
            units = sorted(added_text(root, args.base).items())
            scope = "the lines added against " + args.base
        bad = 0
        for name, lines in units:
            for n, kind, key, shown in sparse_refused(lines):
                if not records.backs(kind, key):
                    bad = 1
                    print("%s: FAIL: %s:%d: '%s' names an owner ruling with no record. Cite the record, or add "
                          "`no record: <reason>` on the line." % (NAME, name, n, shown))
        print("%s: read %d file(s), %s" % (NAME, len(units), scope))
        return bad
    except Unreadable as err:
        print("%s: UNKNOWN: %s" % (NAME, err))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
