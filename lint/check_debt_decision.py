#!/usr/bin/env python3
"""Fails when a debt record does not link its decision. Stdlib only.

    python3 lint/check_debt_decision.py [--base origin/main]

Every debt record links its decision (note debt-decision-link-unchecked, docs/debts/README.md).
The check reads the Decision part of each debt a change adds or edits, against --base.
It fails when that part is not a decision slug or `none`. It also fails when a debt the change adds or edits
has no Decision part, so a change that deletes the part, or rewrites it out of its marker, is red.
An old line is never a verdict. A debt that predates the check stays green until a change edits it.

The Decision part is the line `**Decision.**` at column one or after `- `.
Its first word, with backticks, quote marks and trailing punctuation dropped, must be `none` or a decision slug.
A plain prose word before the slug (the README's form, "The decision `slug`: ...", or "Rule `slug` (...)") is skipped:
the first backticked span is judged in its place, so a rule anchor with no decision file is red and names its slug.
A first word with a `/`, or one ending `.md`, is a path cite and is red, whatever it names.
This is the forward link only. The check does not read whether the decision names the debt back.
"""
import re
import sys

import _record_diff as rd
import check_record_slugs as slugs

NAME = "check_debt_decision"
DECISION = slugs.marker("Decision")  # the one home of the marker line's form
EDGE = "`\"'“”‘’.,;:!?()"
SPAN = re.compile(r"`([^`]+)`")


def first_word(value):
    """The first word of a Decision value with backticks, quote marks and trailing punctuation dropped."""
    words = value.split(None, 1)
    return words[0].strip(EDGE) if words else ""


def verdict(value, decisions):
    """None when the Decision value links a decision or says `none`, else the reason it does not."""
    word = first_word(value)
    plain = value.lstrip()[:1] not in "`\"'“”‘’"
    span = SPAN.search(value)
    if span and plain and word != "none" and word not in decisions and "/" not in word and not word.endswith(".md"):
        word = span.group(1).strip(EDGE)  # a prose word came first: the slug is the first backticked span
    if not word:
        return "the Decision part is empty: name the decision by its slug, or write `none`"
    if "/" in word or word.endswith(".md"):
        return "the Decision part cites a path (`%s`): name the decision by its slug" % word
    if word != "none" and word not in decisions:
        return "the Decision part names `%s`, which is no decision slug: write the slug, or `none`" % word
    return None


def failures(root, base):
    """The bad Decision lines among the lines the change adds. Also the added or edited debts with no Decision part."""
    added, lines, edited = rd.changes(root, base, "debts")
    decisions = rd.tree_slugs(root, "decisions")
    out = []
    for path in sorted(lines):
        for number, text in lines[path]:
            m = DECISION.match(text)
            reason = verdict(text[m.end():], decisions) if m else None
            if reason:
                out.append("%s:%d: %s" % (path, number, reason))
    for path in sorted(set(added) | set(edited)):
        if not any(DECISION.match(line) for line in rd.head_lines(root, path)):
            out.append("%s: the debt has no Decision part: add `**Decision.**` with a decision slug, or `none`" % path)
    return out


def main(argv=None):
    return rd.run_check(NAME, __doc__, failures, argv)


if __name__ == "__main__":
    sys.exit(main())
