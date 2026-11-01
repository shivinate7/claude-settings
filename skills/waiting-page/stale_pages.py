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
  current  the fetched page holds page.html (white space, the designData mockups, the roadmap block and the document <title> text ignored)
  behind   the fetched page differs: republish it (SKILL.md, "Update a repo's pages")
  unknown  the page was not read: another account, a missing file, an empty file
Exit 0 only when every page is current. A behind or unknown page exits 1: an unread page is never
counted current. A host wrapper is tolerated, in both modes: the template must appear inside the
page. The text before it may hold only a document skeleton (doctype, html, head, meta, title and
body tags, white space) and style elements inside the leading head, before body opens. The text
after it may hold only closing body and html tags and white space. Any other text or code around
it makes the page behind, a style or script after body opens too. Batch mode reads page.html
beside this script, and needs no hooks/ folder.

Single-page mode (the writer, at each wake and before each republish):

    python3 ~/.claude/skills/waiting-page/stale_pages.py --page <fetched.html> [--write <out.html>] [--main <page.html>]

One verdict line names the template source: `origin/main <short sha>` or the --main path. Exit 0
current, 1 behind, 2 unknown. Unknown: the file is missing or empty, it holds no designData block
or more than one, main's page.html cannot be read, or --write fails. --write, on current or behind,
saves main's page with the live designData and roadmap blocks kept (splice.carry); unknown writes nothing. The template is
--main; else page.html at origin/main of the checkout that holds this script, else of the checkout
the `@<path>` line in ~/.claude/CLAUDE.md names. With neither, or with no hooks/_nowindow.py to
start git, the verdict is unknown: the installed copy never stands in for main.
Session-start mode, run by hooks/session_start.sh in a repo whose extras name a waiting page:

    python3 ~/.claude/skills/waiting-page/stale_pages.py --session-line <repo toplevel> [--main-checkout <dir>]

It prints one line when the stamp an allowed publish wrote (<git common dir>/waiting-page-built, main's
page.html blob sha) differs from main's blob sha, and nothing else: no stamp, or an unreadable main, prints
nothing. It always exits 0. One python process and one read-only git process.

Cost: one python process, at most one read-only git process (no fetch, no network, 30 s cap), no
file written without --write, no timer, thread or child left running. Single-page mode never imports `layout`; batch and session-line modes do.
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
import splice  # noqa: E402  the one home of the roadmap block's markers (beside this script)

TEMPLATE = os.path.join(HERE, "page.html")
DESIGN = re.compile(r'(<script type="application/json" id="designData">).*?(</script>)', re.S)
DESIGN_BODY = re.compile(r'(<script type="application/json" id="designData">)(.*?)(</script>)', re.S)
TEMPLATE_IN_GIT = "skills/waiting-page/page.html"
GIT_TIMEOUT = 30
# One piece of the text before the template: white space or a document skeleton tag (no event-handler
# attributes). A style piece counts only inside the leading head; skeleton_before() keeps that state.
ATTRS = r'(?:\s+(?!on)[a-z][\w:-]*(?:\s*=\s*(?:"[^"<>]*"|\'[^\'<>]*\'|[^\s"\'<>=]+))?)*'
PIECE = re.compile(r'\s+|<!doctype[^<>]*>|<(?P<close>/?)(?P<tag>html|head|body)%s\s*>|<meta%s\s*/?>'
                   r'|<title%s\s*>[^<>]*</title\s*>|(?P<style><style%s\s*>.*?</style\s*>)'
                   % (ATTRS, ATTRS, ATTRS, ATTRS), re.I | re.S)
# The text after the template: closing body and html tags and white space only.
TAIL = re.compile(r'(?:\s|</(?:body|html)\s*>)*', re.I)


def empty_roadmap_block(text):
    """`text` with the body of its roadmap block cut out, markers kept; unchanged when it has no one block."""
    found = splice.markers(text)
    if [m[0] for m in found] != [splice.OPEN, splice.CLOSE]:
        return text
    return text[:found[0][2]] + text[found[1][1]:]


def empty_title(text):
    """`text` with the text of the page's own document title cut out; an svg title and a title in script text stay."""
    span = splice.title_span(text)
    return text[:span[0]] + text[span[1]:] if span else text


def normal(text):
    """The page text with every designData body, the roadmap block and the document title's text emptied, and white space collapsed."""
    return " ".join(empty_roadmap_block(DESIGN.sub(r"\1\2", empty_title(text))).split())


def skeleton_before(text):
    """True when `text` holds only PIECE pieces, with each style inside the first head, before body opens."""
    at, in_head, seen_head, seen_body = 0, False, False, False
    while at < len(text):
        piece = PIECE.match(text, at)
        if not piece:
            return False
        tag = (piece.group("tag") or "").lower()
        if piece.group("style") and not in_head:
            return False
        if tag == "body" or (tag == "head" and piece.group("close")):
            in_head, seen_body = False, seen_body or tag == "body"
        elif tag == "head":
            in_head, seen_head = not seen_head and not seen_body, True
        at = piece.end()
    return True


def matches(template, live):
    """True when the live text is the template, with only a document skeleton before it and closing tags after it."""
    want, got = normal(template), normal(live)
    at = got.find(want)
    return at >= 0 and skeleton_before(got[:at]) and TAIL.fullmatch(got[at + len(want):]) is not None


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
        with open(os.path.join(os.path.expanduser("~"), ".claude", "CLAUDE.md"), encoding="utf-8", errors="replace") as f:
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
    """(page text, short commit sha, blob sha) of page.html at origin/main in `checkout`, or None. The blob
    sha is the full 40-hex id of main's page.html, the one name of "main's page version" (the guard's stamp
    and the session-start line compare it). One git process, read only."""
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
    return objects[1][1].decode("utf-8", errors="replace"), objects[0][0][:8], objects[1][0]


def find_template(main_path):
    """(text, source name, blob sha) of main's page.html for single-page mode, or None when main cannot be
    read. The blob sha is None for a --main file. Raises OSError when --main names a file that cannot be read."""
    if main_path:
        with open(main_path, encoding="utf-8", errors="replace", newline="") as f:
            return f.read(), main_path, None
    checkout = checkout_of(HERE) or pointer_checkout()
    if checkout:
        got = read_origin_main(checkout)
        if got:
            return got[0], "origin/main %s" % got[1], got[2]
        print("stale_pages: origin/main is not readable in %s" % checkout, file=sys.stderr)
    return None


def main_blob(checkout=None):
    """The full blob sha of page.html at origin/main, or None when main cannot be read. `checkout` is the
    clone to read; none reads the clone that holds this script, else the one the `@<path>` line names."""
    checkout = checkout or checkout_of(HERE) or pointer_checkout()
    got = read_origin_main(checkout) if checkout else None
    return got[2] if got else None


# The stamp: an allowed publish of main's page writes main's blob sha here, in the common git dir of the
# repo (file reads only, no child process). The session-start line reads it back (rule page-stale).
STAMP = "waiting-page-built"


def common_git_dir(root):
    """The common git dir of the checkout at `root`, read from files, or None. A primary checkout has a
    .git folder. A linked worktree has a .git file naming its own gitdir, whose `commondir` file names the
    common one."""
    dot = os.path.join(root, ".git")
    if os.path.isdir(dot):
        return dot
    try:
        with open(dot, encoding="utf-8") as f:
            line = f.read().strip()
        if not line.startswith("gitdir:"):
            return None
        own = os.path.normpath(os.path.join(root, line[len("gitdir:"):].strip()))
        with open(os.path.join(own, "commondir"), encoding="utf-8") as f:
            return os.path.normpath(os.path.join(own, f.read().strip()))
    except OSError:
        return None


def read_stamp(root):
    """The blob sha the last allowed publish stamped for the repo at `root`, or None."""
    common = common_git_dir(root)
    try:
        with open(os.path.join(common, STAMP), encoding="utf-8") as f:
            return f.read().strip() or None
    except (OSError, TypeError):
        return None


def write_common_file(root, name, text):
    """Write `text` to the file `name` in the repo's common git dir, the one home of these stamps. True when
    it wrote; a failure is False and never raises."""
    common = common_git_dir(root)
    try:
        with open(os.path.join(common, name), "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return True
    except (OSError, TypeError):
        return False


def write_stamp(root, blob):
    """Write `blob` to the repo's stamp. True when it wrote; a failure is False and never raises."""
    return write_common_file(root, STAMP, blob)


# The published-path stamp: an allowed publish of the waiting page writes the absolute path of the file it
# published, so a later item write can load that exact page (rule page-item-design).
PUBLISHED = "waiting-page-published"


def write_published(root, path):
    """Stamp `path` as the file last published. True when it wrote; never raises."""
    return write_common_file(root, PUBLISHED, path)


def read_published(root):
    """The path the last allowed publish recorded for the repo at `root`, or None."""
    common = common_git_dir(root)
    try:
        with open(os.path.join(common, PUBLISHED), encoding="utf-8") as f:
            return f.read().strip() or None
    except (OSError, TypeError):
        return None


def session_line(root, main_checkout=None):
    """One line naming the repo's waiting page as behind when the stamp differs from main's blob, else "".
    No stamp, or an unreadable main, gives "": an unread state is never reported as behind."""
    stamp = read_stamp(root)
    if not stamp:
        return ""
    blob = main_blob(main_checkout)
    if not blob or blob == stamp:
        return ""
    import layout  # only for a repo that has a stamp
    url = layout.waiting_page(root)
    if url == "unknown":
        return ""
    return ("waiting page %s is behind main's page.html: it was last published from another version. "
            "The writer runs stale_pages.py --page <file> --write <out> and publishes <out> "
            "(skill waiting-page, \"Keep the page on main's code\")." % url)


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
    template, source, _blob = found
    spot = DESIGN_BODY.search(template)
    if not spot or len(DESIGN_BODY.findall(template)) != 1:
        print("unknown: the template has no single designData block (%s)" % source)
        return 2
    current = matches(template, live)
    if args.write:
        try:
            text = splice.carry(template, live)  # the one carry home: live designData and roadmap blocks, byte for byte
        except SystemExit as err:  # a template or live page whose roadmap markers carry cannot place
            print("unknown: the --write file cannot be built (%s)" % err)
            return 2
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


def session_mode(argv):
    """`--session-line <toplevel> [--main-checkout <dir>]`: print the behind line, or nothing. Always exit 0."""
    ap = argparse.ArgumentParser(prog="stale_pages.py", allow_abbrev=False)
    ap.add_argument("--session-line", required=True)
    ap.add_argument("--main-checkout")
    args = ap.parse_args(argv)
    try:
        line = session_line(args.session_line, args.main_checkout)
    except Exception:  # a line at session start never fails the start
        line = ""
    if line:
        print(line)
    return 0


def main(argv):
    if "--session-line" in argv:
        return session_mode(argv)
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
