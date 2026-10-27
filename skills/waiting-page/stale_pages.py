#!/usr/bin/env python3
"""Name each live waiting page that is behind skills/waiting-page/page.html (skill waiting-page).

    python3 ~/.claude/skills/waiting-page/stale_pages.py <fetched-dir> [<repo root> ...]

A script cannot call the Artifact tool, so the session fetches first. For each page in the list
(lint/layout.py `live_pages`, from the `waiting-page` key of each repo's extras file; with no root
given, the claude-settings checkout and every sibling folder of it that has one), the session reads
the page with Artifact `read` and saves the text to <fetched-dir>/<artifact id>.html. A page it
could not read gets an empty file <artifact id>.unreadable instead. A page with neither file is
unknown too.

Verdict, one line per page, then a total line:
  current  the fetched page holds page.html (white space and the designData mockups ignored)
  behind   the fetched page differs: republish it (SKILL.md, "Update a repo's pages")
  unknown  the page was not read: another account, a missing file, an empty file
Exit 0 only when every page is current. A behind or unknown page exits 1: an unread page is never
counted current. A host wrapper around the page is tolerated: the template must appear inside it.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
sys.path.insert(1, os.path.join(os.path.expanduser("~"), ".claude", "lint"))
import layout  # noqa: E402

TEMPLATE = os.path.join(HERE, "page.html")
DESIGN = re.compile(r'(<script type="application/json" id="designData">).*?(</script>)', re.S)


def normal(text):
    """The page text with every designData body emptied and white space collapsed."""
    return " ".join(DESIGN.sub(r"\1\2", text).split())


def page_id(url):
    return url.rstrip("/").rsplit("/", 1)[-1]


def verdict(url, fetched, template):
    """(word, why) for one page: current, behind or unknown."""
    name = os.path.join(fetched, page_id(url))
    if os.path.isfile(name + ".unreadable"):
        return "unknown", "the read failed (another account or not found)"
    if not os.path.isfile(name + ".html"):
        return "unknown", "no fetched file"
    with open(name + ".html", encoding="utf-8", errors="replace") as f:
        got = normal(f.read())
    if not got:
        return "unknown", "the fetched file is empty"
    return ("current", "") if normal(template) in got else ("behind", "differs from page.html")


def default_roots():
    clone = os.path.abspath(os.path.join(HERE, "..", ".."))
    parent = os.path.dirname(clone)
    extras = layout.layout()["extras"]
    return [clone] + sorted(os.path.join(parent, d) for d in os.listdir(parent)
                            if os.path.join(parent, d) != clone and os.path.isfile(os.path.join(parent, d, extras)))


def main(argv):
    if not argv:
        sys.exit("usage: stale_pages.py <fetched-dir> [<repo root> ...]")
    fetched, roots = argv[0], argv[1:] or default_roots()
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()
    try:
        pages = layout.live_pages(roots)
    except layout.LayoutError as err:
        sys.exit("stale_pages: %s" % err)
    counts = {"current": 0, "behind": 0, "unknown": 0}
    for owner, url in pages:
        word, why = verdict(url, fetched, template)
        counts[word] += 1
        print("%s: %s%s (%s)" % (word, owner, " - " + why if why else "", url))
    print("waiting pages: %d current, %d behind, %d unknown" % (counts["current"], counts["behind"], counts["unknown"]))
    return 0 if counts["behind"] == 0 and counts["unknown"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
