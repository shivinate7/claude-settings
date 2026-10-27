#!/usr/bin/env python3
"""Names each short label that shows more than once on one screen (ux-label-once, a label shows once).

    python3 lint/label_once.py PAGE.html [PAGE.html ...]

Each PAGE is one screen's rendered page, such as the .html file `bin/shoot` writes beside each PNG.
A label is a text run of one to three words, each word made of letters, with two letters or more
in all; a lone letter is a key, such as the A of a choice. A trailing colon or count is dropped,
so "Upcoming (3)" and "Upcoming:" are "upcoming". A second showing is a hit. Case does not count, so
"Blocking" and "blocking" are one label. These do not count: text in a control (button, link,
label, select, option, textarea, summary), in a table cell, in svg, in script, style, template,
noscript or head, and text under a `hidden` or `aria-hidden="true"` element. `bin/shoot` marks
each element the browser does not show as `hidden` before it saves the page. The HTML parser reads the page, so text
in a comment never counts. The reviewer judges each hit against the screenshot.

Exits 0 and prints nothing when each label shows once. Exits 1 and prints one line per repeated
label. Exits 2 when a page cannot be read, or a skipped tag stays open to the end: that page is
unknown, never clear.
Cost: one read of each page named. No process, file or log.
"""
import collections
import re
import sys
from html.parser import HTMLParser

SKIP = {"button", "a", "label", "select", "option", "textarea", "summary", "td", "th",
        "script", "style", "template", "noscript", "head", "svg"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr"}
WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
MAX_WORDS = 3
COUNT = re.compile(r"\s*\(\d+\)$")  # a count after a label: "Upcoming (3)"; "Oct 27" stays a date


class Labels(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # (tag, skips) per open element
        self.counts = collections.Counter()

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        a = dict(attrs)
        hidden = "hidden" in a or (a.get("aria-hidden") or "").strip().lower() == "true"
        self.stack.append((tag, tag in SKIP or hidden))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if any(skips for _, skips in self.stack):
            return
        words = COUNT.sub("", data.strip().rstrip(":")).rstrip(":").split()
        if not 1 <= len(words) <= MAX_WORDS or not all(WORD.fullmatch(w) for w in words):
            return
        if len(words) == 1 and len(words[0]) < 2:
            return
        self.counts[" ".join(words).casefold()] += 1


def repeats(html):
    """The labels that show twice or more, or None when a skipped tag stays open to the end."""
    p = Labels()
    p.feed(html)
    p.close()
    if any(skips for _, skips in p.stack):
        return None  # the rest of the page was never read, so it is not clear
    return [(label, n) for label, n in sorted(p.counts.items()) if n > 1]


def main(argv):
    if not argv:
        print("usage: label_once.py PAGE.html [PAGE.html ...]")
        return 2
    found = unknown = False
    for page in argv:
        try:
            with open(page, encoding="utf-8", errors="replace") as f:
                html = f.read()
        except OSError as e:
            print(f"label_once: UNKNOWN {page}: {e.strerror}")
            unknown = True
            continue
        found_here = repeats(html)
        if found_here is None:
            print(f"label_once: UNKNOWN {page}: a control or hidden element is never closed")
            unknown = True
            continue
        for label, n in found_here:
            print(f'label_once: {page}: "{label}" shows {n} times')
            found = True
    return 2 if unknown else 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
