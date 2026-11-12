#!/usr/bin/env python3
"""Fails when a record cites a record id on its first use with no gloss. Stdlib only.

    python3 lint/check_cite_gloss.py [--base origin/main]

A record glosses each id it cites on first use (rule speak-cite-id-plus-gloss in CLAUDE.md, note
cites-lack-gloss-unchecked). The check reads the lines a change adds or edits in a record, against --base.
It fails on a first cite of a record id that has no gloss right after its closing backtick.
An old line is never a verdict. A record that predates the check stays green until a change edits its first cite.

A record is a decision or a debt (lint/_record_diff.py). A record id is the slug of such a file.
A cite is a backticked span. Its text, with quote marks and spaces dropped, is a record id.
A gloss is ` (` or `,` and a word right after the span (the form actions/stamp writes). A colon is no gloss.
The first use is the first cite in the file, from the top. A heading or a fenced block holds no use.
A record's own slug needs no gloss: a record names itself.
A backtick fence has no backtick in its info string, so a line that starts with a code span is no fence.
"""
import re
import sys

import _record_diff as rd

NAME = "check_cite_gloss"
# A run of n backticks closes at the next run of exactly n. A backslash or another backtick before the opener
# makes it text, so the match starts on a whole run.
SPAN = re.compile(r"(?<![\\`])(`+)(?!`)(.+?)(?<!`)\1(?!`)")
QUOTES = "\"'“”‘’"
GLOSS = re.compile(r" \(|,\s+\w")
HEADING = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def cite_of(content):
    """The text of a code span, with quote marks and spaces dropped: what a record id would read as."""
    return "".join(c for c in content if c not in QUOTES and not c.isspace())


def first_uses(lines, ids):
    """[(line number, slug, text after the span)] for the first cite of each id in `lines`. Headings and fenced
    blocks hold no use. A line number counts from 1."""
    seen, found, fence = set(), [], None
    for number, line in enumerate(lines, 1):
        opener = FENCE.match(line)
        if opener and opener.group(1)[0] == "`" and "`" in opener.group(2):
            opener = None  # an info string with a backtick makes the line a code span (CommonMark)
        if fence:
            if opener and opener.group(1)[0] == fence[0] and len(opener.group(1)) >= len(fence) and not opener.group(2).strip():
                fence = None
            continue
        if opener:
            fence = opener.group(1)
            continue
        if HEADING.match(line):
            continue
        for m in SPAN.finditer(line):
            slug = cite_of(m.group(2))
            if slug in ids and slug not in seen:
                seen.add(slug)
                found.append((number, slug, line[m.end():]))
    return found


def failures(root, base, only=None):
    """The bare first cites on the lines the change adds or edits.
    `only` is {path: line numbers}. A caller that judges other lines passes it in place of the change's lines."""
    ids = rd.tree_slugs(root, "decisions") | rd.tree_slugs(root, "debts")
    if only is None:
        only = {}
        for kind in ("decisions", "debts"):
            for path, rows in rd.changes(root, base, kind)[1].items():
                only[path] = {number for number, _text in rows}
    out = []
    for path in sorted(only):
        for number, slug, after in first_uses(rd.head_lines(root, path), ids - {rd.slug_of(path)}):
            if number in only[path] and not GLOSS.match(after):
                out.append("%s:%d: first cite of `%s` has no gloss: put ` (what it says)` or `, what it says` right after it"
                           % (path, number, slug))
    return out


def main(argv=None):
    return rd.run_check(NAME, __doc__, failures, argv)


if __name__ == "__main__":
    sys.exit(main())
