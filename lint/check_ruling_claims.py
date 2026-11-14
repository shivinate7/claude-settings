#!/usr/bin/env python3
"""Fails when text names an owner ruling that no record backs. Standard library only.

    python3 lint/check_ruling_claims.py [--base REF] [--root DIR] [--rulings-dir DIR] [file ...]
    python3 lint/check_ruling_claims.py [--root DIR] [--rulings-dir DIR] --brief FILE [FILE ...]

A session's own call has passed as an owner ruling. The mistake reached tests and code comments until a reviewer
found no record. This check reads text, prose, comment or string alike, with no parser. A claim cannot hide
in a string or after a lone quote.

Time claims. The lead is `owner ruling`, `owner's ruling` or `ruled at`. A joiner may follow: `,` `(` `:` `at` `of`
or `on`. Then comes a time, `H:MM` or `H.MM`, with an optional zone. A date makes it a dated claim. The date is
`YYYY-MM-DD` or `Mon D`, before the time or after it and its zone. A `T` or `at` may join a date to the time that
follows. A month is a whole month word or its short form, never the head of a longer word. A house cite, the form
`<slug> item <digits>`, may sit between the lead and the stamp. It is read as part of the time claim. A bare time is
refused, whatever the records hold, since no record can tell which day it means. The refusal says to add the date.

Backing. A dated claim has a record when one record line holds both its date and its time. Each record line is read
joined with its next line, within one file. A zone and a leading zero are ignored. The record lines are those of the
decision records and CLAUDE.md. A ruling entry's `at` is read alone, as one line.

Id claims. An id is a kebab slug of two or more words. It is read in backticks after `ruling`, after `ruling:`,
after `owner ruling`, or after a capital `Ruling` or `RULING` that starts a line. A lowercase `ruling` followed by a
word is prose. The word `decision` starts no claim. A slug followed by `item <digits>` is a house cite, not an id. An
id has a record when a decision file stem, a ruling entry's `id` or a CLAUDE.md rule marker (`<!-- rule:<id> -->`)
equals it.

A claim split across two lines is read joined and reported on its first line. A line that holds `no record: <reason>`
passes. The reason must be given.

Modes. Files named: every line of each. --brief: the same, for the files of a brief, read whole and never as a
diff. With neither, the lines the change adds against --base (default origin/main), in every file of the diff.
--rulings-dir reads the ruling entries from a folder of JSON files. Without it, entries come from lint/ruled_store.py,
the folder roadmap/rulings on origin/roadmap of --root. A store that cannot be read exits 2 when a claim is found.

Exit: 0 clear, 1 an unbacked claim, 2 an input that cannot be read (named).

NAMED LIMITS.
- Any record line that holds a date and a time backs a claim with that date and time. The line need not be a ruling.
- A dated claim inside a record backs itself. So does one in a record that the change adds in the same diff.
- The check cannot tell whether the owner said it. It checks only that a record exists.
- A house cite with no time passes. The page item it names has no record file to check.
- An id shaped `fb-<digits>-<digits>` (a feedback item) passes. It has no record file.
- A claim that wraps from an unchanged line into an added line is read only from the added lines.
- CI runs base mode only. A brief is read only when a person or a caller passes it with --brief.
- No guard reads a brief when a session spawns an agent.

Cost: writes nothing. File mode starts no process when it finds no claim, or with --rulings-dir. With a claim, it
reads the store with two git processes (ls-tree, cat-file --batch), or one when the store folder is absent. Base
mode starts two git processes (merge-base, diff), plus the same store reads when it finds a claim.
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
TIME = r"(?<![\d:.])(?P<time>(?:[01]?\d|2[0-3])[:.][0-5]\d)(?!\d)"
ZONE = r"(?:[ \t]+[A-Z]{2,4}\b)?"
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
# A month word, short or whole, never the head of a longer word: "decision 14" is not a date.
MONTH = (r"(?i:\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
         r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?)")


def date_pattern(tag):
    """A `YYYY-MM-DD` or `Mon D` date, its groups named with tag: <tag>y <tag>m <tag>d, or <tag>mon <tag>day. The
    day takes no third digit, so "Nov 2026" is no date."""
    return (r"(?:(?<!\d)(?P<{0}y>\d{{4}})-(?P<{0}m>\d{{2}})-(?P<{0}d>\d{{2}})(?!\d)|(?P<{0}mon>" + MONTH + r")" + SEP +
            r"(?P<{0}day>\d{{1,2}})(?!\d)(?:st|nd|rd|th)?,?)").format(tag)


LEAD = r"(?P<lead>(?i:\bowner(?:'s|\u2019s)?" + SEP + r"ruling|\bruled" + SEP + r"at))"
CONNECTOR = r"(?:" + SEP0 + r"(?:,|\(|:|(?i:at|of|on)\b))?"
SLUG_BODY = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+"
# The tail of a house cite, `<slug> item <digits>`: the slug names a page, not a ruling.
ITEM_TAIL = SEP + r"item" + SEP + r"\d+"
HOUSE_CITE = r"`?" + SLUG_BODY + r"`?" + ITEM_TAIL + r"(?:" + SEP + r"[a-z]\b)?,?" + SEP
DATE_TIME_JOIN = r"(?:T|" + SEP + r"(?:(?i:at)" + SEP + r")?)"
TIME_CLAIM = re.compile(
    LEAD + CONNECTOR + SEP0 + r"(?:" + HOUSE_CITE + r")?(?P<stamp>(?:" + date_pattern("l") + DATE_TIME_JOIN + r")?" +
    TIME + ZONE + r"(?:,?" + SEP + r"(?:(?i:on)" + SEP + r")?" + date_pattern("t") + r")?)")
SLUG = r"`?(" + SLUG_BODY + r")(?![\w-])(?!`?" + ITEM_TAIL + r")`?"
ID_CLAIMS = (
    re.compile(r"\bruling:?" + SEP0 + r"`(" + SLUG_BODY + r")`(?!" + ITEM_TAIL + r")"),
    re.compile(r"\bruling:" + SEP + SLUG),
    re.compile(r"(?i:\bowner(?:'s|\u2019s)?" + SEP + r"ruling):?" + SEP + SLUG),
    re.compile(r"(?m:^)[ \t>*#-]*(?:Ruling|RULING)" + SEP + SLUG),
)
FEEDBACK_ID = re.compile(r"^fb-\d+-\d+$")
NO_RECORD = re.compile(r"\bno record:\s*\S")
RECORD_TIME = re.compile(r"(?<![\d:.+-])(\d{1,2}):(\d{2})(?!\d)")
RECORD_DATE = re.compile(date_pattern("r"))
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


def found_date(m, tag):
    """(year or None, month, day) of the date_pattern(tag) groups of match m, or None when they matched nothing."""
    if m.group(tag + "y"):
        return int(m.group(tag + "y")), int(m.group(tag + "m")), int(m.group(tag + "d"))
    if m.group(tag + "mon"):
        return None, month_number(m.group(tag + "mon")), int(m.group(tag + "day"))
    return None


def claims_in(text):
    """[(offset, end, kind, key, shown)] for each claim in text. Kind is "time" (key (date, (hour, minute))),
    "bare" (key None: a time with no date) or "id" (key the slug)."""
    found = []
    for m in TIME_CLAIM.finditer(text):
        date = found_date(m, "l") or found_date(m, "t")
        kind, key = ("time", (date, clock(m.group("time")))) if date else ("bare", None)
        found.append((m.start(), m.end(), kind, key, " ".join((m.group("lead") + " " + m.group("stamp")).split())))
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


def stamps_of(text):
    """{((year or None, month, day), (hour, minute))} for each date and time that share a line of text."""
    dates = {found_date(m, "r") for m in RECORD_DATE.finditer(text)}
    times = {(int(h), int(mi)) for h, mi in RECORD_TIME.findall(text)}
    return {(date, time) for date in dates for time in times}


def record_stamps(text):
    """stamps_of each line of a record read joined with its next line, so a stamp that wraps still backs a claim."""
    lines = text.split("\n")
    return set().union(*(stamps_of(" ".join(lines[i:i + 2])) for i in range(len(lines))))


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
        stamps, ids = set(), set()
        for folder in self._decision_folders():
            for path in glob.glob(os.path.join(folder, "*.md")):
                ids.add(os.path.splitext(os.path.basename(path))[0])
                stamps |= record_stamps(read_text(path))
        claude = self._claude_md()
        if os.path.isfile(claude):
            text = read_text(claude)
            stamps |= record_stamps(text)
            ids.update(MARKER.findall(text))
        for entry in self._entries():
            if isinstance(entry.get("id"), str):
                ids.add(entry["id"])
            if isinstance(entry.get("at"), str):
                stamps |= stamps_of(entry["at"])  # one entry's `at` alone: never joined with another entry's
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
                    why = ("by a time with no date. Add the date, then cite the record," if kind == "bare" else
                           "with no record. Cite the record,")
                    print("%s: FAIL: %s:%d: '%s' names an owner ruling %s or add `no record: <reason>` on the line."
                          % (NAME, name, n, shown, why))
        print("%s: read %d file(s), %s" % (NAME, len(units), scope))
        return bad
    except Unreadable as err:
        print("%s: UNKNOWN: %s" % (NAME, err))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
