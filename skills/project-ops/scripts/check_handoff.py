#!/usr/bin/env python3
"""Checks a role handoff file: a successor must be told to watch the page, so it hears each answer.

    python3 check_handoff.py <handoff file>

A save of the waiting page wakes only a session that watches the page. A successor with no watch hears
no answer on the items it inherits. Reason: measured incident, the owner's two test saves
(rule building-guard-needs-incident). The check reads the `## Pages` section of the handoff
(templates/role-handoff.md). It needs an `Open items:` line: `none`, or the URL of the page's items
collection. A handoff never carries item ids, which go stale after a compaction, so an id, a number or a
placeholder is a problem. It needs a `Watch:` line with a real page URL: the first http(s) URL in the value, with no `<` or `>`, and text may follow it.
The one exception is `Watch: none` together with `Open items: none`. A `Watch:` line that is there but wrong
is a problem that quotes its value.
Exit 0 ok, 1 a problem (each printed), 2 a bad argument or an unreadable file.
"""
import re
import sys

OPEN_ITEMS = re.compile(r"^Open items:[ \t]*(.*?)[ \t]*$", re.M)
WATCH = re.compile(r"^Watch:[ \t]*(.*?)[ \t]*$", re.M)
PAGES = re.compile(r"^## Pages[ \t]*\n(.*?)(?=^## |\Z)", re.M | re.S)
# `0` is none only alone: `05` and `0, 4` are ids.
NONE = re.compile(r"(?:none\b|0(?![\w,]))", re.I)
WATCH_NONE = re.compile(r"none\b", re.I)
URL = re.compile(r"https?://\S+")
HOME = "Write `Open items: none`, or name the page's items collection by URL, not ids."


def _is_url(value):
    """True when the first http(s) URL in `value` holds no placeholder bracket."""
    m = URL.search(value)
    return bool(m) and "<" not in m.group(0) and ">" not in m.group(0)


def handoff_problems(text):
    """-> the problems of a handoff file's text, one string each. An empty list is ok."""
    text = text.replace("\r\n", "\n")
    section = PAGES.search(text)
    pages = section.group(1) if section else ""
    held = OPEN_ITEMS.search(pages)
    if held is None:
        return [f"No `Open items:` line in the Pages section. {HOME}"]
    items = held.group(1)
    no_items = bool(NONE.match(items))
    if not items:
        return [f"The `Open items:` line is not filled. {HOME}"]
    if not no_items and not _is_url(items):
        return [f'The `Open items:` line holds no items collection URL: "{items}". {HOME}']
    watches = WATCH.findall(pages)
    if not watches:
        return ["No `Watch:` line in the Pages section. Add `Watch: <page URL>`, one line per page. "
                "A successor with no watch hears no answer."]
    found = []
    valid = any(_is_url(w) for w in watches)
    for w in watches:
        if _is_url(w):
            continue
        if WATCH_NONE.match(w):
            if no_items or valid:
                continue
            found.append("`Watch: none` is allowed only with `Open items: none`, and these items are open. "
                         "Write the page URL on the `Watch:` line.")
        elif not w:
            found.append("The `Watch:` line is empty. Write the page URL.")
        else:
            found.append(f'The `Watch:` line holds no real page URL: "{w}". '
                         "Write the full http(s) URL, with no `<` or `>`.")
    return found


def main(argv):
    if len(argv) != 1:
        print("check_handoff: give one argument, the handoff file.", file=sys.stderr)
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
