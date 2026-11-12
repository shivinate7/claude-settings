#!/usr/bin/env python3
"""Writes the item field table of SKILL.md, between `<!-- gen:item-fields -->` and `<!-- /gen -->`.

    python3 skills/waiting-page/field_table.py            write the table into SKILL.md
    python3 skills/waiting-page/field_table.py --check    exit 0, no output, when the block is current;
                                                          exit 1 and print the stale block when it is not

Sources, read each run and never copied here:
  page.html `itemFields` block   the fields and their order (hooks/question_form.py `_item_fields`).
  hooks/question_form.py         `PAGE_REASONS`: the rule the block's first line names must be a key of it.
  field_table.json               a field's one-line meaning, which no code holds. A field-to-guard-rule column
                                 is left out: the guard exposes no field-to-rule tie, so a column would go stale unread.

Problems, one line each, exit 1, nothing written: the block is unreadable, an itemFields field has no entry in
the data file, the data file names a field the page does not list, an entry has no meaning, or the rule the block names
is not in PAGE_REASONS. Exit 2 when an input cannot be read or SKILL.md has not exactly one block.

Options for tests: --skill FILE, --page FILE, --data FILE.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "hooks"))
import question_form  # noqa: E402

OPEN, CLOSE = "<!-- gen:item-fields -->", "<!-- /gen -->"
# The block sits inside the first bullet of "The database", so every line carries its two-space indent.
INDENT = "  "
EVERY_FIELD_RULE = "item-field-rendered"  # judges every field name, so the block names it once, above the table
FENCE = "```"


def problems(fields, data, reasons):
    out = []
    if fields is None:
        return ["itemFields block of the page does not read"]
    out += ["field %s is in itemFields and has no entry in the data file" % f for f in fields if f not in data]
    out += ["field %s is in the data file and not in itemFields" % f for f in data if f not in fields]
    for field, entry in data.items():
        if not isinstance(entry, dict) or not str(entry.get("meaning") or "").strip():
            out.append("field %s has no meaning" % field)
            continue
    if EVERY_FIELD_RULE not in reasons:
        out.append("rule %s is not in PAGE_REASONS" % EVERY_FIELD_RULE)
    return out


def cell(text):
    return text.replace("|", "\\|")


def render(fields, data):
    rows = ["| Field | Meaning |", "| --- | --- |"]
    for f in fields:
        rows.append("| `%s` | %s |" % (f, cell(data[f]["meaning"])))
    lines = [OPEN, "Guard rule `%s` judges every field name: a write names only the fields below." % EVERY_FIELD_RULE,
             ""] + rows + [CLOSE]
    return "\n".join(INDENT + l if l else l for l in lines)


def find_block(lines):
    """(start, end) line indexes of the one block, markers included, ignoring a marker inside a code fence.
    None when there is not exactly one open and one close, in order."""
    opens, closes, fenced = [], [], False
    for i, line in enumerate(lines):
        text = line.strip()
        if text.startswith(FENCE):
            fenced = not fenced
        elif not fenced and text == OPEN:
            opens.append(i)
        elif not fenced and text == CLOSE:
            closes.append(i)
    if len(opens) == 1 and len(closes) == 1 and opens[0] < closes[0]:
        return opens[0], closes[0]
    return None


def read(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:  # newline="": a CRLF file keeps its line endings
            return f.read()
    except OSError as e:
        print("cannot read %s: %s" % (path, e.strerror), file=sys.stderr)
        sys.exit(2)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--skill", default=os.path.join(HERE, "SKILL.md"))
    ap.add_argument("--page", default=question_form.ITEM_FIELDS_PAGE)
    ap.add_argument("--data", default=os.path.join(HERE, "field_table.json"))
    args = ap.parse_args(argv)

    try:
        data = json.loads(read(args.data))
    except ValueError as e:
        print("cannot read %s: %s" % (args.data, e), file=sys.stderr)
        return 2
    read(args.page)  # a page that cannot be opened is an unreadable input (exit 2), not an unreadable block
    fields = question_form._item_fields(args.page)
    found = problems(fields, data, question_form.PAGE_REASONS)
    if found:
        print("\n".join(found))
        return 1

    text = read(args.skill)
    lines = text.split("\n")
    span = find_block(lines)
    if span is None:
        print("%s has not exactly one %s ... %s block" % (args.skill, OPEN, CLOSE), file=sys.stderr)
        return 2
    start, end = span
    fresh = render(fields, data)
    # The block takes the line ending its open marker has, so a CRLF file stays CRLF end to end.
    cr = "\r" if lines[start].endswith("\r") else ""
    current = "\n".join(l.rstrip("\r") for l in lines[start:end + 1])
    if current == fresh:
        return 0
    if args.check:
        print("stale: %s differs from field_table.py; run it without --check" % args.skill)
        print(current)
        return 1
    with open(args.skill, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines[:start] + [l + cr for l in fresh.split("\n")] + lines[end + 1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
