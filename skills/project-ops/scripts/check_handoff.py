#!/usr/bin/env python3
"""Checks a role hand-off file: a successor that inherits open waiting-page items must be told to watch the page.

    python3 check_handoff.py <handoff file>

A save of the waiting page wakes only a session that watches the page. A successor with no watch hears
no answer on the items it inherits. Reason: measured incident, the owner's two test saves, 2026-10-30
(rule building-guard-needs-incident). The check reads the `## Pages` section of the hand-off
(templates/role-handoff.md). It needs an `Open items:` line, which is `none` or the item numbers.
With open items, it needs at least one `Watch: <page URL>` line, with an http(s) URL.
Exit 0 ok, 1 a problem (each printed), 2 a bad argument or an unreadable file.
"""
import re
import sys

OPEN_ITEMS = re.compile(r"^Open items:[ \t]*(.*?)[ \t]*$", re.M)
WATCH = re.compile(r"^Watch:[ \t]*(.*?)[ \t]*$", re.M)
PAGES = re.compile(r"^## Pages[ \t]*\n(.*?)(?=^## |\Z)", re.M | re.S)


def handoff_problems(text):
    """-> the problems of a hand-off file's text, one string each. An empty list is ok."""
    text = text.replace("\r\n", "\n")
    section = PAGES.search(text)
    pages = section.group(1) if section else ""
    held = OPEN_ITEMS.search(pages)
    if held is None:
        return ["No `Open items:` line in the Pages section. Write `Open items: none` or the item numbers."]
    items = held.group(1)
    if not items or "<" in items:
        return ["The `Open items:` line is not filled. Write `none` or the item numbers."]
    if items.lower() == "none":
        return []
    if any(re.match(r"https?://\S+$", url) for url in WATCH.findall(pages)):
        return []
    return ["Open items are inherited but no `Watch: <page URL>` line holds a URL. "
            "Add one line per page: the successor cannot hear an answer without a watch."]


def main(argv):
    if len(argv) != 1:
        print("check_handoff: give one argument, the hand-off file.", file=sys.stderr)
        return 2
    try:
        with open(argv[0], encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"check_handoff: cannot read {argv[0]}: {e}", file=sys.stderr)
        return 2
    found = handoff_problems(text)
    for p in found:
        print(f"check_handoff: {p}")
    if not found:
        print("check_handoff: ok")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
