#!/usr/bin/env python3
"""Fails when text names an owner ruling that no record backs. Standard library only.

    python3 lint/check_ruling_claims.py [--base REF] [--root DIR] [--rulings-dir DIR] [file ...]
    python3 lint/check_ruling_claims.py [--root DIR] [--rulings-dir DIR] --brief FILE [FILE ...]

A session's own call has passed as an owner ruling. The mistake reached tests and code comments until a reviewer
found no record. This check reads text, prose, comment or string alike, with no parser. A claim cannot hide
in a string or after a lone quote.

Time claims. The lead is `owner ruling`, `owner's ruling` or `ruled at`. A connector (`,` `(` `at` `of`) may follow.
Then comes a time, `H:MM` or `H.MM`, with an optional zone. A date makes it a dated claim: `YYYY-MM-DD` or `Mon D`
(a comma is optional) before the time. A bare time is refused, whatever the records hold, since no record can
tell which day it means. A dated claim has a record when one line of a record holds both its date and its time. A
zone and a leading zero are ignored. A record is a decision record, CLAUDE.md, or a rulings entry's `at`.

Id claims. An id is a kebab slug of two or more words. It is read in backticks after `ruling`, after `ruling:`,
after `owner ruling` or `decision`, or after a capital `Ruling` or `RULING` that starts a line. A lowercase `ruling`
followed by a word is prose. An id has a record when a decision file stem, a rulings entry `id` or a CLAUDE.md
rule marker (`<!-- rule:<id> -->`) equals it.

A claim split across two lines is read joined and reported on its first line. A line that holds `no record: <reason>`
passes. The reason must be given.

Modes. Files named: every line of each. --brief: the same, for the files of a brief, read whole and never as a
diff. With neither, the lines the change adds against --base (default origin/main), in every file of the diff.
--rulings-dir reads the rulings from a folder of JSON files. Without it, entries come from lint/ruled_store.py,
the folder roadmap/rulings on origin/roadmap of --root. A store that cannot be read exits 2 when a claim is found.

Exit: 0 clear, 1 an unbacked claim, 2 an input that cannot be read (named).

NAMED LIMITS.
- A record that a change adds in the same diff backs its own claim. A decision that files a ruling needs no
  second record. The check cannot tell whether the owner said it. It checks that a record exists.
- An id shaped `fb-<digits>-<digits>` (a feedback item) passes. It has no record file.
- A claim that wraps from an unchanged line into an added line is read only from the added lines.
- Only this check reads a brief, run by hand or in CI. No guard reads a brief when a session spawns an agent.

Cost: starts no process in file mode. Base mode starts two git processes (merge-base, diff). It reads the
records only when a claim is found, and writes nothing.
"""
import argparse
import bisect
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

NAME = "check_ruling_claims"
# One break between two words of a claim: spaces, or a line end with an optional comment or quote prefix.
SEP = r"(?:[ \t]+|[ \t]*\r?\n[ \t]*(?:(?:#|//|\*|>|;|--)[ \t]*)?)"
SEP0 = r"(?:" + SEP + r")?"
TIME = r"(?<![\d:.])((?:[01]?\d|2[0-3])[:.][0-5]\d)(?!\d)"
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
ISO_DATE = r"(\d{4})-(\d{2})-(\d{2})"
MON_DATE = r"(?i:(" + "|".join(MONTHS) + r")[a-z]*\.?)" + SEP + r"(\d{1,2})(?:st|nd|rd|th)?,?"
LEAD = r"(?i:\bowner(?:'s|\u2019s)?" + SEP + r"ruling|\bruled" + SEP + r"at)"
CONNECTOR = r"(?:" + SEP0 + r"(?:,|\(|(?i:at|of)\b))?"
TIME_CLAIM = re.compile(LEAD + CONNECTOR + SEP0 + r"(?:(?:" + ISO_DATE + r"|" + MON_DATE + r")" + SEP + r")?" +
                        TIME + r"(?:[ \t]+[A-Z]{2,4}\b)?")
SLUG = r"`?([a-z][a-z0-9]*(?:-[a-z0-9]+)+)(?![\w-])`?"
ID_CLAIMS = (
    re.compile(r"\bruling:?" + SEP0 + r"`([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`"),
    re.compile(r"\bruling:" + SEP + SLUG),
    re.compile(r"(?i:\bowner(?:'s|\u2019s)?" + SEP + r"ruling):?" + SEP + SLUG),
    re.compile(r"(?i:\bdecision):?" + SEP + SLUG),
    re.compile(r"(?m:^)[ \t>*#-]*(?:Ruling|RULING)" + SEP + SLUG),
)
FEEDBACK_ID = re.compile(r"^fb-\d+-\d+$")
NO_RECORD = re.compile(r"\bno record:\s*\S")
RECORD_TIME = re.compile(r"(?<![\d:.+-])(\d{1,2}):(\d{2})(?!\d)")
RECORD_ISO = re.compile(ISO_DATE)
RECORD_MON = re.compile(MON_DATE)
MARKER = re.compile(r"<!--\s*rule:([a-z0-9][a-z0-9-]*)\s*-->")
HUNK = re.compile(r"^@@ -\S+ \+(\d+)")


class Unreadable(Exception):
    """An input the check cannot read; the message names it."""


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            return f.read()
    except OSError as err:
        raise Unreadable("%s: cannot read: %s" % (path, err.strerror or err))


def month_number(word):
    return MONTHS.index(word.lower()[:3]) + 1


def clock(text):
    """(hour, minute) of an `H:MM` or `H.MM` time."""
    hour, minute = re.split(r"[:.]", text)
    return int(hour), int(minute)


def claim_date(m):
    """(year or None, month, day) of a time claim match, or None when the claim has no date."""
    if m.group(1):
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    if m.group(4):
        return None, month_number(m.group(4)), int(m.group(5))
    return None


def claims_in(text):
    """[(offset, end, kind, key, shown)] for each claim in text. Kind is "time" (key (date, (hour, minute))),
    "bare" (key None: a time with no date) or "id" (key the slug)."""
    found = []
    for m in TIME_CLAIM.finditer(text):
        date = claim_date(m)
        kind, key = ("time", (date, clock(m.group(6)))) if date else ("bare", None)
        found.append((m.start(), m.end(), kind, key, " ".join(m.group().split())))
    seen = set()
    for pattern in ID_CLAIMS:
        for m in pattern.finditer(text):
            slug = m.group(1)
            if FEEDBACK_ID.match(slug) or (m.start(1), slug) in seen:
                continue
            seen.add((m.start(1), slug))
            found.append((m.start(), m.end(), "id", slug, " ".join(m.group().split())))
    return sorted(found)


def refused(lines):
    """[(first line, kind, key, claim text)] for each claim in a {line number: text} map. Runs of consecutive line
    numbers are read joined. A claim whose lines hold `no record: <reason>` is skipped."""
    out = []
    numbers = sorted(lines)
    runs = []
    for n in numbers:
        if runs and runs[-1][-1] == n - 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    for run in runs:
        text = "\n".join(lines[n] for n in run)
        starts, pos = [], 0
        for n in run:
            starts.append(pos)
            pos += len(lines[n]) + 1
        for offset, end, kind, key, shown in claims_in(text):
            first = bisect.bisect_right(starts, offset) - 1
            last = bisect.bisect_right(starts, max(end - 1, offset)) - 1
            if any(NO_RECORD.search(lines[run[i]]) for i in range(first, last + 1)):
                continue
            out.append((run[first], kind, key, shown))
    return out


def line_dates_and_times(line):
    """({(year or None, month, day)}, {(hour, minute)}) of one record line."""
    dates = {(int(y), int(mo), int(d)) for y, mo, d in RECORD_ISO.findall(line)}
    dates |= {(None, month_number(mo), int(d)) for mo, d in RECORD_MON.findall(line)}
    return dates, {(int(h), int(mi)) for h, mi in RECORD_TIME.findall(line)}


class Records:
    """What backs a claim. Reads each source once, on the first claim that needs it."""

    def __init__(self, root, rulings_dir):
        self.root, self.rulings_dir = root, rulings_dir
        self._stamps = self._ids = None

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
            entries, state = ruled_store.read_store(self.root)
            if state != "ok":
                raise Unreadable("the rulings store of %s is %s: cannot tell whether a record exists" %
                                 (self.root, state))
            return entries
        entries = []
        for path in sorted(glob.glob(os.path.join(self.rulings_dir, "*.json"))):
            try:
                body = json.loads(read_text(path))
            except ValueError:
                continue  # a store file that is not JSON backs nothing; lint/ruled_store.py check names it
            if isinstance(body, dict):
                entries.append(body)
        return entries

    def _load(self):
        stamps, ids, lines = set(), set(), []
        for folder in self._decision_folders():
            for path in glob.glob(os.path.join(folder, "*.md")):
                ids.add(os.path.splitext(os.path.basename(path))[0])
                lines += read_text(path).split("\n")
        claude = self._claude_md()
        if os.path.isfile(claude):
            text = read_text(claude)
            lines += text.split("\n")
            ids.update(MARKER.findall(text))
        for entry in self._entries():
            if isinstance(entry.get("id"), str):
                ids.add(entry["id"])
            if isinstance(entry.get("at"), str):
                lines.append(entry["at"])
        for line in lines:
            dates, times = line_dates_and_times(line)
            stamps |= {(date, time) for date in dates for time in times}
        self._stamps, self._ids = stamps, ids

    def backs(self, kind, key):
        if kind == "bare":
            return False
        if self._stamps is None:
            self._load()
        if kind == "id":
            return key in self._ids
        (year, month, day), time = key
        return any(date[1:] == (month, day) and t == time and (year is None or date[0] in (None, year))
                   for date, t in self._stamps)

    def load(self):
        """Read every source now, so an unreadable one stops the run before any verdict."""
        if self._stamps is None:
            self._load()


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
        if named:
            units = [(name, dict(enumerate(read_text(name).split("\n"), 1))) for name in named]
            scope = "the files named"
        else:
            units = sorted(added_text(root, args.base).items())
            scope = "the lines added against " + args.base
        found = [(name, refused(lines)) for name, lines in units]
        if any(claims for _name, claims in found):
            records.load()
        bad = 0
        for name, claims in found:
            for n, kind, key, shown in claims:
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
