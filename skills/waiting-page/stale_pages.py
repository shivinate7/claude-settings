#!/usr/bin/env python3
"""Name each live waiting page that is behind skills/waiting-page/page.html (skill waiting-page).

    python3 ~/.claude/skills/waiting-page/stale_pages.py <fetched-dir> [<repo root> ...]

A script cannot call the Artifact tool, so the session fetches first. For each page in the list
(lint/layout.py `live_pages`, from the `waiting-page` key of each repo's extras file; with no root
given, the claude-settings checkout and every sibling folder of it that has one), the session reads
the page with Artifact `read` and saves the text to <fetched-dir>/<artifact id>.html. A page it
could not read gets an empty file <artifact id>.unreadable instead. A page that Artifact read
reports as not found, and that this account's Artifact list (scope all) holds no id for, gets an empty
<artifact id>.notfound. A page with no file is unknown too.

Verdict, one line per page, then a total line:
  current  the fetched page holds page.html (white space, the designData mockups, the roadmap block and the document <title> text ignored)
  behind   the fetched page differs: republish it (skill waiting-page, "Update a repo's pages")
  unknown  the page was not read: another account, a missing file, an empty file, an .unreadable marker
  not-found  the page has a .notfound marker: not found from this account (deleted, or another account's).
           The line says to re-file the repo's items on the claude-settings waiting page: the URL recorded in the
           extras file of the claude-settings checkout that holds this script, not fetched. That target reads
           "the claude-settings waiting page is unknown" when the checkout has no page, its extras file cannot be
           read, or its page has a .notfound or .unreadable marker in <fetched-dir> (so a not-found page that is
           the claude-settings page names no target). The check never repoints a page.
The total line reads `waiting pages: N current, N behind, N unknown, N not-found`.
Exit 0 only when every page is current. A behind, unknown or not-found page exits 1: an unread page is never
counted current. A host wrapper is tolerated, in both modes: the template must appear inside the
page. The text before it may hold only a document skeleton (doctype, html, head, meta, title and
body tags, white space) and style elements inside the leading head, before body opens. The text
after it may hold only closing body and html tags and white space. Any other text or code around
it makes the page behind, a style or script after body opens too. Batch mode reads page.html
beside this script, and needs no hooks/ folder.

Single-page mode (the writer, at each wake and before each republish):

    python3 ~/.claude/skills/waiting-page/stale_pages.py --page <fetched.html> [--write <out.html>] [--main <page.html>] [--items <file|folder>] [--answers <file|folder>]

One verdict line names the template source: `origin/main <short sha>` or the --main path. Exit 0
current, 1 behind, 2 unknown. Unknown: the file is missing or empty, it holds no designData block
or more than one, main's page.html cannot be read, or --write fails. --write, on current or behind,
saves main's page with the live designData and roadmap blocks kept (splice.carry); unknown writes nothing. The template is
--main; else page.html at origin/main of the checkout that holds this script, else of the checkout
the `@<path>` line in ~/.claude/CLAUDE.md names. With neither, or with no hooks/_nowindow.py to
start git, the verdict is unknown: the installed copy never stands in for main.
--items names the items the session saved with `ArtifactData list items`: a JSON list file (bare data objects, or {id, data} entries), or the folder of
<id>.json files that call saves. A folder without the .complete marker reads every wait `unknown`, with no gh call.
--items needs hooks/_nowindow.py to start gh; without it every wait reads `unknown`. A `run` or `pr` is a whole
number above zero, or a string of digits with no leading zero; anything else reads `unknown`. For each open item (status not `closed`) with a `waits` field, `{repo, run}`
or `{repo, pr}`, one gh call runs through the program named by WAITING_PAGE_GH (default `gh`):
`run view <id> --repo <repo> --json status,conclusion` or `pr view <n> --repo <repo> --json state,mergedAt`.
Each such item prints one line after the verdict line, `wait: item <n> (<what>): <word> (<detail>)`. An open item with a
non-empty string `lane` and a `lastAnswer` object but no `waits` prints `wait: item <n> (lane <slug>): waiting (answered <lastAnswer.at>)`
(`answered at unknown` when `at` is missing or not a string) instead: a routed answer whose receiver has not reported the act done. It starts no gh process and does not count against WAIT_CAP.
An item with `waits` keeps its one line. The word is
`ended` (the run completed with any conclusion; the PR merged; the PR closed unmerged, which its line says),
`waiting` (the run or PR is still going), or `unknown` (gh missing, non-zero, timed out, not JSON, or a
malformed `waits`; also an item past the WAIT_CAP-th call, which is not asked). The exit code stays the page verdict's.
--answers, with --items, names the answers the session saved with `ArtifactData list answers`, in the same two shapes, read by the same
loader (a list entry names its item in `item`, or is {"id", "data"}; a folder doc by its file name). After the wait and lane lines, one line per closed item,
in item order, whose answer is still kept: `kept-answer: item <n> (<id>) is closed and answers/<id> is kept`, then the remedy (delete
the answer; a routed item stays closed). A closed item with `waits` prints `kept-answer: item <n> (<id>) is closed with waits and
answers/<id> is kept`, then the remedy: when its wait has ended, drop `waits` and delete the answer; no gh call. Never named: an open item or one with no status,
a closed item with a `lane` and a `lastAnswer` (routed: its answer stays until the done report), an item with `arbiter` true, a park answer (`park.<id>`, `parked: true` or `act: "park"`), an answer with no item. An unreadable file, a folder without the marker,
unreadable items, an items folder without the marker, or --answers without --items print one `kept-answer: unknown (...)` line, with no other kept-answer line.
The folder loader is export_page.docs_in, the one home of reading that folder.
Session-start mode, run by hooks/session_start.sh in a repo whose extras name a waiting page:

    python3 ~/.claude/skills/waiting-page/stale_pages.py --session-line <repo toplevel> [--main-checkout <dir>]

It prints one line when the stamp an allowed publish wrote (<git common dir>/waiting-page-built, main's
page.html blob sha) differs from main's blob sha, and nothing else: no stamp, or an unreadable main, prints
nothing. It always exits 0. One python process and one read-only git process.

Parked mode, run by the writer at each wake when meta/page.parked is not empty (SKILL.md, "Route and close"):

    python3 ~/.claude/skills/waiting-page/stale_pages.py --parked <dir> [--now <iso>]

<dir> holds three files the session saved from the store: meta.json (the data of meta/page), items.json and
answers.json (a list of {"id", "data"} entries each). One line per stale thing, then exit 1:
`parked-open <id>` for a parked entry whose item is open (status other than closed, as the page reads it),
and `park-answer-old <key>` for a park answer (answers/park.<id>, or answers/<item id> with act park) whose `at` is
more than 10 minutes before --now (default: the clock). With none, `parked: clean` and exit 0. A missing or unreadable
file, a file of the wrong shape (meta not an object, items or answers not a list), or a park answer with no readable
`at` prints an `unknown:` line and exits 2.
Cost: one python process, reads 3 files, writes none, starts no git, no timer.

Unread mode, run by the writer at a comment wake, never at turn start (SKILL.md, "Read the answers").
At the end of that wake the writer writes `woke`: `ArtifactData update meta/page` with only `woke`, ISO UTC with a
trailing Z, and never on exit 2.

    python3 ~/.claude/skills/waiting-page/stale_pages.py --unread <dir>

<dir> holds four files the session saved from the store: meta.json (the data of meta/page, an object), items.json,
answers.json and receipts.json (a list of {"id", "data"} entries each). One line per item answer the writer has not
read back, in answers.json order, then exit 1:
`answer-unread <id> (item <n>, owner <owner>, answered <at>, before wake <woke>)`
(`?` for a missing n or owner). An answer is listed when it is an item answer (not `park.<id>`, `parked: true` or
act `park`), its item exists (open, or closed with the answer kept), its `at` is earlier than meta `woke` (the
writer's previous wake) and no receipt with the answer's id has a `read` at or after `at`. A receipt with only `filed`
does not clear it (the check reads `read` only, never `filed`). With no `woke` (absent or null) every answer with
no such receipt is listed, and the last field reads `before wake: none recorded`. With none listed,
`unread: clean` and exit 0. A missing or unreadable file, a file of the wrong shape (meta not an object, the others
not a list), an unreadable `woke`, an answer with no readable `at`
or a compared receipt with no readable `read` prints an `unknown:` line and exits 2.
The mode reads no clock and has no time bound: what it lists depends on the saved files alone. `woke` is the writer's
own optional field in meta/page. The incident: an answer that sat unread 10.5 h (owner's report).
Write `read` and `filed` as ISO UTC with a trailing Z: a time with no zone is read in the host's zone.
Cost: one python process, reads 4 files, writes none, starts no git, no timer.

Cost: one python process, at most one read-only git process (no fetch, no network, 30 s cap), no
extra process for --answers (it reads one more file, a folder one per answer), no
file written without --write, no timer, thread or child left running. Single-page mode never imports `layout`; batch and session-line modes do.
Without --items: 0 gh processes. With it: one gh process per open item with a `waits` field, at most WAIT_CAP, each
run to its end or its 30 s cap before the next (a lane line starts none); no file written, no timer, no process left running.
"""
import argparse
import datetime
import json
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
WAIT_CAP = 50  # most gh calls one --items run makes
REPO_NAME = re.compile(r"[\w.-]+/[\w.-]+")
WAIT_NUMBER = re.compile(r"[1-9][0-9]*")  # a run id or PR number: a whole number above zero, with no leading zero (page.html waitsOf reads the same form)
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


def carries_data(template, live):
    """True when the live page is not main's untouched template: its title text (read as splice.carry would
    rename it), its designData block or its roadmap block differs from the template's own (all white space ignored). A page that --write built
    from a live page has its own title, and carries the live blocks, so it is not untouched. Fails toward
    True: a page whose parts cannot be found is not judged untouched. A live page with no roadmap marker
    predates the block and counts as empty there, as splice.carry reads it."""
    def part(text, span, rename=False):
        if not span:
            return None
        text = text[span[0]:span[1]]
        return "".join((splice.renamed_title(text) if rename else text).split())
    try:
        # A live title of an old form carries as the page name, so it reads as that name here (splice.carry).
        if part(template, splice.title_span(template)) != part(live, splice.title_span(live), rename=True):
            return True
        if part(template, splice.design_span(template, "the template")) != part(live, splice.design_span(live, "the live page")):
            return True
        if splice.markers(live) and (part(template, splice.block_span(template, "the template"))
                                     != part(live, splice.block_span(live, "the live page"))):
            return True
    except SystemExit:
        return True
    return False


def hub_clone():
    """The claude-settings checkout that holds this script: the one home of the clone that default_roots() starts from."""
    return os.path.abspath(os.path.join(HERE, "..", ".."))


def marker(url, fetched):
    """"notfound" or "unreadable" when <fetched>/<artifact id> has that marker, else None. The file name is
    layout.artifact_id(url), the one home of "same artifact", so a query string names the same file."""
    import layout  # batch mode only
    name = os.path.join(fetched, layout.artifact_id(url))
    for kind in ("notfound", "unreadable"):
        if os.path.isfile(name + "." + kind):
            return kind
    return None


def refile_target(fetched):
    """The claude-settings waiting page URL, as its extras file records it, or "unknown" when that checkout has
    no page, its extras file cannot be read, or the page has a marker in `fetched`. A not-found page that is
    the claude-settings page has its own marker, so it never names itself."""
    import layout  # batch mode only
    try:
        url = layout.waiting_page(hub_clone())
    except layout.LayoutError:
        return "unknown"
    return "unknown" if url == "unknown" or marker(url, fetched) else url


def verdict(url, fetched, template):
    """(word, why) for one page: current, behind, unknown or not-found."""
    import layout  # batch mode only
    found = marker(url, fetched)
    if found == "notfound":
        target = refile_target(fetched)
        where = ("re-file its items on the claude-settings waiting page %s" % target if target != "unknown"
                 else "no place to re-file its items: the claude-settings waiting page is unknown")
        return "not-found", "not found from this account (deleted, or another account's); %s" % where
    if found == "unreadable":
        return "unknown", "the read failed"
    name = os.path.join(fetched, layout.artifact_id(url))
    if not os.path.isfile(name + ".html"):
        return "unknown", "no fetched file"
    with open(name + ".html", encoding="utf-8", errors="replace") as f:
        live = f.read()
    if not normal(live):
        return "unknown", "the fetched file is empty"
    return ("current", "") if matches(template, live) else ("behind", "differs from page.html")


def default_roots():
    import layout  # batch mode only: single-page mode must run without lint/
    clone = hub_clone()
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


def load_docs(path, what="items", keyed=False):
    """(docs, complete): the saved `what` ("items" or "answers") as a list from a JSON list file, or the folder `ArtifactData list` saves. `complete` is False
    for a folder without the marker the session leaves after the last list page, since a stopped fetch may lack docs. With `keyed`, each doc is
    (doc id, data): the file name of a folder doc, None for a bare list entry, whose data alone says which item it answers. A list entry shaped
    {"id": str, "data": dict} (what `ArtifactData list` returns) unwraps to (id, data), as a folder doc does, with or without `keyed`; so `--items`
    reads that shape's data, where it once read the wrapper. Raises ValueError with the cause."""
    from export_page import MARKER, Stop, docs_in, load_json  # lazy: only --items and --answers read a folder
    try:
        if os.path.isdir(path):
            found = docs_in(path, path)
            data = list(found.items()) if keyed else list(found.values())
        else:
            data = load_json(path, path)
            if isinstance(data, list):
                wrapped = [isinstance(doc, dict) and isinstance(doc.get("id"), str) and isinstance(doc.get("data"), dict) for doc in data]
                if keyed:
                    data = [(doc["id"], doc["data"]) if w else (None, doc) for doc, w in zip(data, wrapped)]
                else:
                    data = [doc["data"] if w else doc for doc, w in zip(data, wrapped)]
    except Stop as err:
        raise ValueError(str(err))
    except OSError as err:
        raise ValueError(err.strerror or str(err))
    if not isinstance(data, list):
        raise ValueError("%s is not a JSON list of %s" % (path, what))
    return data, not os.path.isdir(path) or os.path.isfile(os.path.join(path, MARKER))


def parse_waits(waits):
    """(gh argv, label) for a `waits` of {repo, run} or {repo, pr}; ValueError when it is anything else."""
    if not isinstance(waits, dict) or set(waits) not in ({"repo", "run"}, {"repo", "pr"}):
        raise ValueError("waits is not {repo, run} or {repo, pr}")
    repo, kind = waits["repo"], "run" if "run" in waits else "pr"
    number = waits[kind]
    if isinstance(number, int) and not isinstance(number, bool):
        number = str(number)
    if not (isinstance(repo, str) and REPO_NAME.fullmatch(repo) and isinstance(number, str) and WAIT_NUMBER.fullmatch(number)):
        raise ValueError("waits names a repo or %s that is not valid" % kind)
    fields = "status,conclusion" if kind == "run" else "state,mergedAt"
    return [kind, "view", number, "--repo", repo, "--json", fields], "%s %s in %s" % (kind, number, repo)


def ask_gh(argv):
    """The parsed JSON gh prints for `argv`, or ValueError with the cause. One gh process, ended or killed at GIT_TIMEOUT."""
    gh = os.environ.get("WAITING_PAGE_GH") or "gh"
    try:
        import _nowindow  # the one home of a no-window child start, as read_origin_main
        done = _nowindow.run([gh] + argv, capture_output=True, text=True, timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL)
    except (ImportError, OSError, subprocess.SubprocessError) as err:
        raise ValueError("gh did not run (%s)" % type(err).__name__)
    if done.returncode != 0:
        raise ValueError("gh exited %d" % done.returncode)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        raise ValueError("gh did not answer JSON")
    if not isinstance(answer, dict):
        raise ValueError("gh did not answer a JSON object")
    return answer


def wait_word(argv, answer):
    """(word, detail) for gh's answer to a run or pr view; ValueError when the answer holds neither."""
    if argv[0] == "run":
        status = answer.get("status")
        if not isinstance(status, str) or not status:
            raise ValueError("gh gave no run status")
        if status != "completed":
            return "waiting", status
        conclusion = answer.get("conclusion")
        return "ended", "completed, %s" % conclusion if isinstance(conclusion, str) and conclusion else "completed"
    state = answer.get("state")
    if answer.get("mergedAt") or state == "MERGED":
        return "ended", "merged"
    if state == "CLOSED":
        return "ended", "closed unmerged"
    if state == "OPEN":
        return "waiting", "open"
    raise ValueError("gh gave no pr state")


def wait_lines(items, complete=True):
    """One line per open item with a `waits` field, in order; at most WAIT_CAP gh calls. With complete False, none: every wait reads unknown.
    An open item with a `lane` and a `lastAnswer` and no `waits` gets one lane line, built from the item: no gh call, not counted in WAIT_CAP."""
    lines, calls = [], 0
    for item in items:
        if not isinstance(item, dict):
            lines.append("wait: an items entry is not an object: unknown")
            continue
        if item.get("status") == "closed":
            continue
        if "waits" not in item:
            answer, lane = item.get("lastAnswer"), item.get("lane")
            if isinstance(answer, dict) and isinstance(lane, str) and lane:
                at = answer.get("at")
                lines.append("wait: item %s (lane %s): waiting (answered %s)" % (item.get("n", item.get("id", "?")), lane,
                                                                                at if isinstance(at, str) and at else "at unknown"))
            continue
        name, label = "item %s" % item.get("n", item.get("id", "?")), json.dumps(item["waits"])
        try:
            argv, label = parse_waits(item["waits"])
            if not complete:
                raise ValueError("not asked: the items folder has no .complete marker, so its list may be cut short")
            if calls >= WAIT_CAP:
                raise ValueError("not asked: more than %d gh calls" % WAIT_CAP)
            calls += 1
            word, detail = wait_word(argv, ask_gh(argv))
        except ValueError as err:
            word, detail = "unknown", str(err)
        lines.append("wait: %s (%s): %s (%s)" % (name, label, word, detail))
    return lines


def kept_answer_lines(items, answers, complete=True, answers_complete=True):
    """One line per closed item, in item order, whose answer is still kept: the writer re-reads answers/<id>, then deletes it
    (SKILL.md, "Route and close"). `items` and `answers` are (doc id, data) pairs from load_docs. A closed item with `waits` and a kept answer (a chat
    answer can close an item during a wait) gets its own line, "is closed with waits", whose remedy waits for the wait to end; no gh call. Never an open
    item, an arbiter ruling (its overturn answer is read by its own route), a park answer, an answer with no item, or a routed closed item (a
    non-empty string `lane` and a `lastAnswer` object: its answer stays until the done report).
    With `complete` or `answers_complete` False (that folder may be cut short), one unknown line naming it."""
    if not (complete and answers_complete):
        return ["kept-answer: unknown (the %s folder has no .complete marker, so its list may be cut short)"
                % ("items" if not complete else "answers")]
    kept = {}
    for doc_id, data in answers:
        if not isinstance(data, dict):
            continue
        doc_id = doc_id if doc_id is not None else data.get("item")  # a list entry has no file name
        if (isinstance(doc_id, str) and not doc_id.startswith("park.") and data.get("parked") is not True
                and data.get("act") != "park"):
            kept[doc_id] = data
    lines = []
    for doc_id, item in items:
        if not isinstance(item, dict):
            continue
        item_id = doc_id if doc_id is not None else item.get("id")  # the file name is the doc id, as for the answers
        if item.get("status") != "closed" or item.get("arbiter") is True or item_id not in kept:
            continue
        if isinstance(item.get("lane"), str) and item["lane"] and isinstance(item.get("lastAnswer"), dict):
            continue  # routed: closed at routing, answer kept until the receiver's done report
        if "waits" in item:
            lines.append('kept-answer: item %s (%s) is closed with waits and answers/%s is kept; when its wait has ended, drop waits and delete '
                         'answers/%s (SKILL.md, "Route and close")' % (item.get("n", item_id), item_id, item_id, item_id))
        else:
            lines.append('kept-answer: item %s (%s) is closed and answers/%s is kept; re-read answers/%s, then delete it '
                         '(SKILL.md, "Route and close")' % (item.get("n", item_id), item_id, item_id, item_id))
    return lines


def single_page(argv):
    """Exit 0 current, 1 behind, 2 unknown for one fetched page. Writes a file only with --write, never on unknown.
    With --items, prints after the verdict line one wait line per open item with a `waits` field, and one lane line per open
    item with a `lane` and a `lastAnswer` and no `waits`. With --answers too, one kept-answer line per closed item whose answer is kept.
    The exit code stays the verdict's."""
    ap = argparse.ArgumentParser(prog="stale_pages.py", allow_abbrev=False)
    ap.add_argument("--page", required=True)
    ap.add_argument("--write")
    ap.add_argument("--main")
    ap.add_argument("--items")
    ap.add_argument("--answers")
    args = ap.parse_args(argv)
    code = page_verdict(args)
    if args.items is not None:
        try:
            items, complete = load_docs(args.items, keyed=True)
            lines = wait_lines([dict(d, id=k) if k and isinstance(d, dict) else d for k, d in items], complete)
        except ValueError as err:
            items, lines = None, ["wait: the items cannot be read: unknown (%s)" % err]
        if args.answers is not None:
            try:
                if items is None:
                    raise ValueError("the items cannot be read")
                answers, answers_complete = load_docs(args.answers, "answers", keyed=True)
                lines += kept_answer_lines(items, answers, complete, answers_complete)
            except ValueError as err:
                lines.append("kept-answer: unknown (%s)" % err)
        for line in lines:
            print(line)
    elif args.answers is not None:
        print("kept-answer: unknown (--answers needs --items)")
    return code


def page_verdict(args):
    """The verdict of one fetched page: prints its line and returns the exit code."""
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


PARK_ANSWER_MAX_AGE = 600  # seconds: a park answer the writer has not closed in 10 minutes is stale


def parse_utc(text):
    """An ISO time with a Z (as the store writes it) as epoch seconds, or None when it cannot be read."""
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parked_mode(argv):
    """`--parked <dir> [--now <iso>]`: name each parked entry whose item is open and each park answer older than 10 minutes."""
    ap = argparse.ArgumentParser(prog="stale_pages.py", allow_abbrev=False)
    ap.add_argument("--parked", required=True)
    ap.add_argument("--now")
    args = ap.parse_args(argv)
    now = parse_utc(args.now) if args.now else datetime.datetime.now(datetime.timezone.utc).timestamp()
    if now is None:
        print("unknown: --now is not an ISO time (%s)" % args.now)
        return 2
    try:
        loaded = {}
        for name in ("meta", "items", "answers"):
            with open(os.path.join(args.parked, name + ".json"), encoding="utf-8") as f:
                loaded[name] = json.load(f)
    except (OSError, ValueError) as err:
        print("unknown: cannot read %s.json in %s (%s)" % (name, args.parked, err))
        return 2
    meta, items, answers = loaded["meta"], loaded["items"], loaded["answers"]
    for name, ok in (("meta", isinstance(meta, dict)), ("items", isinstance(items, list)), ("answers", isinstance(answers, list))):
        if not ok:  # a file of the wrong shape is never read as clean or stale
            print("unknown: %s.json is not %s" % (name, "an object" if name == "meta" else "a list"))
            return 2
    entries = lambda rows: [r for r in rows if isinstance(r, dict)]
    data = lambda r: r.get("data") if isinstance(r.get("data"), dict) else {}
    open_ids = {r.get("id") for r in entries(items) if data(r).get("status") != "closed"}
    parked = meta.get("parked") if isinstance(meta.get("parked"), list) else []
    lines = ["parked-open %s" % p["id"] for p in parked if isinstance(p, dict) and p.get("id") in open_ids]
    unknown = []
    for r in entries(answers):
        key = str(r.get("id", ""))
        # A parked line's answer is keyed park.<id>. An item's answer is a park answer only with act park; any other act is never read.
        if not (key.startswith("park.") or data(r).get("act") == "park"):
            continue
        at = parse_utc(data(r).get("at"))
        if at is None:  # an unreadable time is never counted fresh or old
            unknown.append("unknown: the park answer %s has no readable at" % key)
        elif now - at > PARK_ANSWER_MAX_AGE:
            lines.append("park-answer-old %s" % key)
    out = lines + unknown
    print("\n".join(out) if out else "parked: clean")
    return 2 if unknown else 1 if lines else 0


def unread_mode(argv):
    """`--unread <dir>`: name each item answer the writer has not read back, from four saved files and no clock."""
    ap = argparse.ArgumentParser(prog="stale_pages.py", allow_abbrev=False)
    ap.add_argument("--unread", required=True)
    args = ap.parse_args(argv)
    try:
        loaded = {}
        for name in ("meta", "items", "answers", "receipts"):
            with open(os.path.join(args.unread, name + ".json"), encoding="utf-8") as f:
                loaded[name] = json.load(f)
    except (OSError, ValueError) as err:
        print("unknown: cannot read %s.json in %s (%s)" % (name, args.unread, err))
        return 2
    meta, items, answers, receipts = loaded["meta"], loaded["items"], loaded["answers"], loaded["receipts"]
    for name, ok in (("meta", isinstance(meta, dict)), ("items", isinstance(items, list)),
                     ("answers", isinstance(answers, list)), ("receipts", isinstance(receipts, list))):
        if not ok:  # a file of the wrong shape is never read as clean or listed
            print("unknown: %s.json is not %s" % (name, "an object" if name == "meta" else "a list"))
            return 2
    entries = lambda rows: [r for r in rows if isinstance(r, dict)]
    data = lambda r: r.get("data") if isinstance(r.get("data"), dict) else {}
    woke_text = meta.get("woke")
    woke = parse_utc(woke_text) if woke_text is not None else None
    if woke_text is not None and woke is None:  # an unreadable wake is never read as "no wake"
        print("unknown: meta woke is not an ISO time (%s)" % woke_text)
        return 2
    item_data = {}
    for r in entries(items):
        item_data.setdefault(r.get("id"), data(r))
    reads = {}
    for r in entries(receipts):
        reads.setdefault(r.get("id"), []).append(data(r).get("read"))
    lines, unknown = [], []
    for r in entries(answers):
        key = r.get("id")
        # A park answer is read by the --parked mode, never here: keyed park.<id>, parked: true, or act park.
        if not isinstance(key, str) or key.startswith("park.") or data(r).get("parked") is True or data(r).get("act") == "park":
            continue
        if key not in item_data:
            continue
        at = parse_utc(data(r).get("at"))
        if at is None:  # an unreadable time is never counted read or unread
            unknown.append("unknown: the answer %s has no readable at" % key)
            continue
        if woke is not None and at >= woke:
            continue
        times = [parse_utc(read) for read in reads.get(key, []) if read is not None]
        if any(t is not None and t >= at for t in times):
            continue
        if any(t is None for t in times):
            unknown.append("unknown: the receipt of answer %s has no readable read" % key)
            continue
        item = item_data[key]
        lines.append("answer-unread %s (item %s, owner %s, answered %s, %s)" % (
            key, item.get("n", "?"), item.get("owner", "?"), data(r)["at"],
            "before wake %s" % woke_text if woke is not None else "before wake: none recorded"))
    out = lines + unknown
    print("\n".join(out) if out else "unread: clean")
    return 2 if unknown else 1 if lines else 0


def main(argv):
    if "--unread" in argv:
        return unread_mode(argv)
    if "--parked" in argv:
        return parked_mode(argv)
    if "--session-line" in argv:
        return session_mode(argv)
    if "--page" in argv:
        return single_page(argv)
    if not argv:
        sys.exit("usage: stale_pages.py <fetched-dir> [<repo root> ...]\n"
                 "       stale_pages.py --page <fetched.html> [--write <out.html>] [--main <page.html>]\n"
                 "       stale_pages.py --parked <dir> [--now <iso>]\n"
                 "       stale_pages.py --unread <dir>")
    import layout  # batch mode only
    fetched, roots = argv[0], argv[1:] or default_roots()
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()
    try:
        pages = layout.live_pages(roots)
    except layout.LayoutError as err:
        sys.exit("stale_pages: %s" % err)
    counts = {"current": 0, "behind": 0, "unknown": 0, "not-found": 0}
    for owner, url in pages:
        word, why = verdict(url, fetched, template)
        counts[word] += 1
        print("%s: %s%s (%s)" % (word, owner, " - " + why if why else "", url))
    print("waiting pages: %d current, %d behind, %d unknown, %d not-found"
          % (counts["current"], counts["behind"], counts["unknown"], counts["not-found"]))
    return 0 if counts["current"] == len(pages) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
