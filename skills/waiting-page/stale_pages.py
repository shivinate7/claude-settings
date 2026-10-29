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
counted current. A host wrapper is tolerated, in both modes: the template must appear inside the
page, and the text around it may hold only a document skeleton (doctype, html, head, meta, title
and body tags, white space). Any other text or code around it makes the page behind. Batch mode
reads page.html beside this script, and needs no hooks/ folder.

Single-page mode (the writer, at each wake and before each republish):

    python3 ~/.claude/skills/waiting-page/stale_pages.py --page <fetched.html> [--write <out.html>] [--main <page.html>]

One verdict line names the template source: `origin/main <short sha>` or the --main path. Exit 0
current, 1 behind, 2 unknown. Unknown: the file is missing or empty, it holds no designData block
or more than one, main's page.html cannot be read, or --write fails. --write, on current or behind,
saves main's page with the live designData body kept; unknown writes nothing. The template is
--main; else page.html at origin/main of the checkout that holds this script, else of the checkout
the `@<path>` line in ~/.claude/CLAUDE.md names. With neither, or with no hooks/_nowindow.py to
start git, the verdict is unknown: the installed copy never stands in for main.
Cost: one python process, at most one read-only git process (no fetch, no network, 30 s cap), no
file written without --write, no timer, thread or child left running. It never imports `layout`.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
sys.path.insert(1, os.path.join(os.path.expanduser("~"), ".claude", "lint"))
sys.path.insert(2, os.path.join(HERE, "..", "..", "hooks"))
sys.path.insert(3, os.path.join(os.path.expanduser("~"), ".claude", "hooks"))

TEMPLATE = os.path.join(HERE, "page.html")
DESIGN = re.compile(r'(<script type="application/json" id="designData">).*?(</script>)', re.S)
DESIGN_BODY = re.compile(r'(<script type="application/json" id="designData">)(.*?)(</script>)', re.S)
TEMPLATE_IN_GIT = "skills/waiting-page/page.html"
GIT_TIMEOUT = 30
# What may surround the template: document skeleton tags (no event-handler attributes) and white space.
ATTRS = r'(?:\s+(?!on)[a-z][\w:-]*(?:\s*=\s*(?:"[^"<>]*"|\'[^\'<>]*\'|[^\s"\'<>=]+))?)*'
SKELETON = re.compile(r'(?:\s|<!doctype[^<>]*>|</?(?:html|head|body)%s\s*>|<meta%s\s*/?>|<title%s\s*>[^<>]*</title\s*>)*'
                      % (ATTRS, ATTRS, ATTRS), re.I)


def normal(text):
    """The page text with every designData body emptied and white space collapsed."""
    return " ".join(DESIGN.sub(r"\1\2", text).split())


def matches(template, live):
    """True when the live text is the template, with nothing around it but a document skeleton."""
    want, got = normal(template), normal(live)
    at = got.find(want)
    return at >= 0 and SKELETON.fullmatch(got[:at] + " " + got[at + len(want):]) is not None


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
        live = f.read()
    if not normal(live):
        return "unknown", "the fetched file is empty"
    return ("current", "") if matches(template, live) else ("behind", "differs from page.html")


def default_roots():
    import layout  # batch mode only: single-page mode must run without lint/
    clone = os.path.abspath(os.path.join(HERE, "..", ".."))
    parent = os.path.dirname(clone)
    extras = layout.layout()["extras"]
    return [clone] + sorted(os.path.join(parent, d) for d in os.listdir(parent)
                            if os.path.join(parent, d) != clone and os.path.isfile(os.path.join(parent, d, extras)))


def checkout_of(folder):
    """The nearest folder at or above `folder` that holds a .git entry (a dir, or a worktree's file), or None."""
    folder = os.path.abspath(folder)
    while True:
        if os.path.exists(os.path.join(folder, ".git")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def pointer_checkout():
    """The checkout that an `@<path>` line in ~/.claude/CLAUDE.md names, or None. Reads one file, runs no git."""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".claude", "CLAUDE.md"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("@") and line[1:].strip():
            target = os.path.realpath(os.path.expanduser(line[1:].strip()))
            found = checkout_of(os.path.dirname(target))
            if found:
                return found
    return None


def read_origin_main(checkout):
    """(page text, short sha) of page.html at origin/main in `checkout`, or None. One git process, read only."""
    want = ("origin/main\norigin/main:%s\n" % TEMPLATE_IN_GIT).encode()
    try:
        import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py); never a raw spawn
        done = _nowindow.run(["git", "-C", checkout, "cat-file", "--batch"], input=want,
                             capture_output=True, timeout=GIT_TIMEOUT)
    except (ImportError, OSError, subprocess.SubprocessError):
        return None
    out, objects = done.stdout, []
    for kind in (b"commit", b"blob"):  # each object: "<sha> <type> <size>\n<size bytes>\n"
        head, _, rest = out.partition(b"\n")
        parts = head.split()
        if len(parts) != 3 or parts[1] != kind or not parts[2].isdigit():
            return None
        size = int(parts[2])
        objects.append((parts[0].decode(), rest[:size]))
        out = rest[size + 1:]
    return objects[1][1].decode("utf-8", errors="replace"), objects[0][0][:8]


def find_template(main_path):
    """(text, source name) of main's page.html for single-page mode, or None when main cannot be read.
    Raises OSError when --main names a file that cannot be read."""
    if main_path:
        with open(main_path, encoding="utf-8", errors="replace", newline="") as f:
            return f.read(), main_path
    checkout = checkout_of(HERE) or pointer_checkout()
    if checkout:
        got = read_origin_main(checkout)
        if got:
            return got[0], "origin/main %s" % got[1]
        print("stale_pages: origin/main is not readable in %s" % checkout, file=sys.stderr)
    return None


def single_page(argv):
    """Exit 0 current, 1 behind, 2 unknown for one fetched page. Writes a file only with --write, never on unknown."""
    ap = argparse.ArgumentParser(prog="stale_pages.py", allow_abbrev=False)
    ap.add_argument("--page", required=True)
    ap.add_argument("--write")
    ap.add_argument("--main")
    args = ap.parse_args(argv)
    try:
        with open(args.page, encoding="utf-8", errors="replace", newline="") as f:
            live = f.read()
    except OSError as err:
        print("unknown: the fetched page cannot be read (%s)" % (err.strerror or err))
        return 2
    if not normal(live):
        print("unknown: the fetched file is empty")
        return 2
    live_blocks = DESIGN_BODY.findall(live)
    if len(live_blocks) != 1:
        print("unknown: the fetched page has %d designData blocks, want 1" % len(live_blocks))
        return 2
    try:
        found = find_template(args.main)
    except OSError as err:
        print("unknown: main unreadable: the --main file cannot be read (%s)" % (err.strerror or err))
        return 2
    if not found:
        print("unknown: main unreadable: no origin/main page.html reached, and the installed copy is not used")
        return 2
    template, source = found
    spot = DESIGN_BODY.search(template)
    if not spot or len(DESIGN_BODY.findall(template)) != 1:
        print("unknown: the template has no single designData block (%s)" % source)
        return 2
    current = matches(template, live)
    if args.write:
        # Slicing, never re.sub: a mockup body holds < and backslashes that a replacement string would read.
        text = template[:spot.start(2)] + live_blocks[0][1] + template[spot.end(2):]
        try:
            with open(args.write, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        except OSError as err:
            print("unknown: the --write file cannot be written (%s)" % (err.strerror or err))
            return 2
        print("stale_pages: wrote %s" % args.write, file=sys.stderr)
    if current:
        print("current: matches the template (%s)" % source)
        return 0
    print("behind: differs from the template (%s)" % source)
    return 1


def main(argv):
    if "--page" in argv:
        return single_page(argv)
    if not argv:
        sys.exit("usage: stale_pages.py <fetched-dir> [<repo root> ...]\n"
                 "       stale_pages.py --page <fetched.html> [--write <out.html>] [--main <page.html>]")
    import layout  # batch mode only
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
