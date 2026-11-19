#!/usr/bin/env python3
"""Name each live waiting page that is behind skills/waiting-page/page.html (skill waiting-page).

    python3 ~/.claude/skills/waiting-page/stale_pages.py <fetched-dir> [<repo root> ...]

A script cannot call the Artifact tool, so the session fetches first. For each page in the list
(lint/layout.py `live_pages`: the first link of the waiting-page entry in each repo's extras file, else its old
`waiting-page` key; with no root given, the claude-settings checkout and every sibling folder of it that has one), the session reads
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
A read page whose roadmap block holds only white space (no build baked it) gets one more line,
`roadmap block: empty on <owner> page (bake it: skill waiting-page, "Update the roadmap block")`, in both modes
(page mode says `this page`), and the run exits 1; the verdict word and the total line stay. A block baked with null data is not empty.
Exit 0 only when every page is current and holds no empty roadmap block. A behind, unknown or not-found page exits 1: an unread page is never
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
loader (a list entry names its item in `item`, or is {"id", "data"}; a folder doc by its file name). After the wait and lane lines, one line per open or closed item,
in item order, whose answer is still kept: `kept-answer: item <n> (<id>) is closed and answers/<id> is kept`, then the remedy (delete
the answer; a routed item stays closed). A closed item with `waits` prints `kept-answer: item <n> (<id>) is closed with waits and
answers/<id> is kept`, then the remedy: when its wait has ended, drop `waits` and delete the answer; no gh call. An open item whose kept answer is older than its `added` (reopened or reworded, record left) prints `kept-answer: item <n> (<id>) is open and answers/<id> is older than its added`, then the remedy: re-read the answer, route it if new, then delete it. These lines come before the closed items' lines. Never named: an open item whose answer is not older than its `added` (awaiting filing), an item with no status,
a closed item with a `lane` and a `lastAnswer` (routed: its answer stays until the done report), an item with `arbiter` true, a park answer (`park.<id>`, `parked: true` or `act: "park"`), an answer with no item. An unreadable file, a folder without the marker,
unreadable items, an items folder without the marker, or --answers without --items print one `kept-answer: unknown (...)` line, with no other kept-answer line.
The folder loader is export_page.docs_in, the one home of reading that folder.
With --items and the env WAITING_PAGE_STEPS naming the record's roadmap/data/steps folder (no CLI flag), an open item whose `home` (a bare step id, or `step <id>`)
names a step whose status is done, dropped, folded or done-obsolete prints `found-false: item <n> (<id>): ...` after the other lines. The line names the home, its
status and the close (status closed, a reply, replied); the item is moot, so the owner is never asked. Unset, the check does nothing; an unreadable folder prints
one `found-false: unknown (...)` line. The exit code stays the verdict's.
Session-start mode, run by hooks/session_start.sh in a repo whose extras name a waiting page:

    python3 ~/.claude/skills/waiting-page/stale_pages.py --session-line <repo toplevel> [--main-checkout <dir>]

Two stamps hold main's page.html blob sha at the last publish: the page-built stamp roadmap/data/meta/page-built.json on
origin/roadmap of the repo (JSON {"blob", "at"}; triage writes it at each republish; the format is at RECORD_PATH below), and
the local stamp an allowed publish wrote (<git common dir>/waiting-page-built). It prints nothing when either stamp equals
main's blob sha, and the behind line when at least one stamp exists and none equals it. A missing or unreadable page-built
stamp (no branch, no file, no parse, no 40-hex blob) leaves the local stamp alone: behind when it differs from main's blob,
silent when equal. With no stamp at all, or a stamp with main unreadable, or a repo with no page in its extras, it prints
nothing. It always exits 0. One python process and at most two read-only git
processes: `git show` of the record in the repo, and the read of main's page.html in the claude-settings clone (two repos, so
one process cannot read both).

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
A listed answer on an item with a non-empty `lane` ends its parentheses with `, lane <slug>`, so the wake can message that lane.
An answer already routed is not listed: its item has a non-empty `lane` and a `lastAnswer.at` equal to the answer's `at` (the busy-lane path), and a receipt with a `read` at or after the answer's `at` exists (the routing session writes it at routing time). A routed answer with no such receipt is listed as usual.
Two more lines, after the answer lines and before any unknown line:
`answer-needs-reply <id> (item <n>, owner <owner>, answered <at>)` for an item answer of `choice` `none` whose `note` is not blank, when
the item has no `reply` with text and a `replied` later than the answer's `at` (read or unread, whatever the wake). A `replied` that is
not an ISO time, with a `reply` text, is unknown. On an item with `waits`, `replied` is not trusted, since a wait moves it too: the line clears once a receipt for the answer has a `read` at or after the answer's `at`.
`lane-missing <id> (item <n>, owner <owner>)` for an open item with `holdsLane` true and no `lane` text, whatever its `waits` and with or without `holds` text.
An item with `holds` alone (a merge or PR wait) never gets it, and neither does a closed item.
Write `read` and `filed` as ISO UTC with a trailing Z: a time with no zone is read in the host's zone.
Cost: one python process, reads 4 files, writes none, starts no git, no timer.

Close-batch mode, run by the item's owner at step 1 and 2 of "Route and close" (SKILL.md):

    python3 ~/.claude/skills/waiting-page/stale_pages.py --close-batch --item <file> --answer <file> [--receipt <file>] [--reply <text>] [--now <iso>] [--done] [--item-version <n>] [--answer-version <n>] [--receipt-version <n>]

Each file is a doc `ArtifactData get` saved ({id, data, version}) or bare data. It prints one `ArtifactData batch` payload, {"writes": [...]}:
a `set` of receipts/<id> with `read` and `filed` at --now (default: the clock, ISO UTC with a Z), an `update` of items/<id> that closes it
(`status`, `closed`, `lastAnswer` from the answer's `choice`, `done`, `note`, `at`; with --reply text also `reply` and `replied`), and a `delete` of
answers/<id>, with `"pinned"` true or false beside `writes`. A write carries `if_version` from --item-version, --answer-version or --receipt-version, else from
the fetched wrapper's `version`, else none (--receipt names the receipt already stored). With the item or answer (or a named receipt) unpinned, the first line
on stderr is `unpinned: <docs>` and `pinned` is false; the payload still prints. Exit 0.
Exit 2 with one `unknown:` line and no payload when the item is open and routed, awaiting a done report, and --done is not passed (`item waits for a done report`): it has `waits`, or a non-empty `lane` and a `lastAnswer.at` equal to the answer's `at`. An open item with `lane` and a plain pick (no matching `lastAnswer`) closes without --done, and the helper then prints `notify-lane <slug>` on stderr and `"notify": "<slug>"` in the payload: the closer messages that lane. Also when a file cannot be read, the ids differ, the answer has no readable `at`, or the answer is a
`none` that asks a question and --reply has no text. Cost: one python process, reads up to 3 files, writes none, starts no git, no timer.

Awaiting mode, run by the writer at a comment wake (SKILL.md, "Read the answers"), after it saves its report.

    python3 ~/.claude/skills/waiting-page/stale_pages.py --awaiting <dir>

<dir> holds threads.txt, the output of `ArtifactComments read` (every page, in order, the first page first), and
report.md (the writer's report), read only when it is there.
- First page: a line reads `<N> comment thread(s)` or `No comment threads`, above the first `Thread` line. The tool's notice
  lines above it are skipped. Else the file is a later page alone: `unknown`, exit 2. A later page needs no header.
- A thread starts at a `Thread <uuid>` line; its next line begins `open` or `resolved`. A comment row is a line at
  exactly two spaces, `  [<who> - <ISO time>]` (with the tool's em dash). A text line carries a six-space `<token>| `
  prefix and never counts. A `  [location] <label>` row is the label. `[anchored at]`, `[region of]` and `[on text]`
  rows are known tool rows and are skipped.
- Awaiting: the thread is open and its last comment row is not exactly `Claude (via the user)`. A viewer named
  `Claude Reyes` is a viewer. The tool prints no "awaiting reply" marker.
- Cut line: a `[N more thread(s) not listed` line is read through when a `Thread` line follows it later in the file
  (the next page was appended). With no `Thread` line after it, the read is cut.
- Elided row: a `  [N comment(s) elided` row in an open thread is unknown, wherever it sits, since it may hide the
  last comment. In a resolved thread it is skipped: a resolved thread is never awaiting.
- Unknown row: any other two-space bracket row in an open thread is unknown.
- Duplicate: the same thread id on two `Thread` lines (a page appended twice) prints
  `unknown: thread <id8> appears twice`. The thread is listed once, from its first block.
- A cut read, an unknown row, a duplicate, a missing or empty threads.txt, an open thread with no comment rows, or a
  thread with no open or resolved status prints `unknown: <what>` and exits 2, with no report check.
Without report.md, one line per awaiting thread in file order, then exit 1:
`thread-awaiting <first 8 chars of id> (last comment <time>, <location or "no location">)`. With none,
`awaiting: clean` and exit 0 (a first page with no thread is clean).
With report.md the mode prints report lines only, never the thread-awaiting lines. The text between the bold
`Input Needed` label and the next bold Done, Deviations or Next label must hold each awaiting id8. An id that sits
only on the count line, as in `Awaiting reply: 1 (<id8>)`, counts as named, since that line is in the section.
A count line must give the count (also when N is 0): `Awaiting reply: N` at the line start, after an optional `> `,
`- ` and `**`, with an optional `**` after the colon and any text after N. So `> - Awaiting reply: 1`,
`**Awaiting reply:** 1` and `**Awaiting reply: 1**` all count; `Awaiting reply: none` is no count.
`report-missing <id8>` names each omitted thread; `report-count <found or none> expected <N>` names a wrong or absent
count; exit 1. All right: `awaiting-report: ok (N listed)`, exit 0. The incident: an owner thread waited 37 h for a
reply.
Cost: one python process, reads 2 files, writes none, starts no git, no timer.

Cost: one python process, at most one read-only git process (no fetch, no network, 30 s cap; --session-line at most two, see its mode), no
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
FOUND_ENV = "WAITING_PAGE_STEPS"  # the folder of step files the --items run reads for found-false items; unset, the check does nothing
FOUND_DONE = ("done", "dropped", "folded", "done-obsolete")  # the step statuses that make an item's premise moot
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


def block_body(text):
    """(start, end) of the body of the one roadmap block in `text`, markers excluded; None when it has no one block."""
    found = splice.markers(text)
    if [m[0] for m in found] != [splice.OPEN, splice.CLOSE]:
        return None
    return found[0][2], found[1][1]


def empty_roadmap_block(text):
    """`text` with the body of its roadmap block cut out, markers kept; unchanged when it has no one block."""
    span = block_body(text)
    return text if span is None else text[:span[0]] + text[span[1]:]


def unbaked_line(text, owner):
    """The line for a page whose roadmap block holds only white space (no build baked it), else None. A block
    build.py baked with no record branch holds null data, so it is not empty."""
    span = block_body(text)
    if span is None or text[span[0]:span[1]].strip():
        return None
    return 'roadmap block: empty on %s page (bake it: skill waiting-page, "Update the roadmap block")' % owner


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


def fetched_text(url, fetched):
    """The text saved for `url` in <fetched>/<artifact id>.html, or None when there is no such file."""
    import layout  # batch mode only
    name = os.path.join(fetched, layout.artifact_id(url)) + ".html"
    if not os.path.isfile(name):
        return None
    with open(name, encoding="utf-8", errors="replace") as f:
        return f.read()


def verdict(url, fetched, template):
    """(word, why) for one page: current, behind, unknown or not-found."""
    found = marker(url, fetched)
    if found == "notfound":
        target = refile_target(fetched)
        where = ("re-file its items on the claude-settings waiting page %s" % target if target != "unknown"
                 else "no place to re-file its items: the claude-settings waiting page is unknown")
        return "not-found", "not found from this account (deleted, or another account's); %s" % where
    if found == "unreadable":
        return "unknown", "the read failed"
    live = fetched_text(url, fetched)
    if live is None:
        return "unknown", "no fetched file"
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


# The page-built stamp: triage writes it on the record branch at each republish of the live page, after the publish
# succeeds, so a fresh cloud container (no local stamp) can read it. JSON {"blob": ..., "at": ...}.
#   blob: the 40-hex git blob sha of skills/waiting-page/page.html at origin/main at the republish (what read_origin_main
#         returns as its sha; `git rev-parse origin/main:skills/waiting-page/page.html`). Written only from a real
#         republish: a stamp for a build that did not happen would hide a stale page.
#   at:   the republish time, ISO 8601 with the US Central offset, e.g. 2026-11-15T01:23:00-06:00. Informational: no reader reads it.
RECORD_REF = "origin/roadmap"
RECORD_PATH = "roadmap/data/meta/page-built.json"


def read_record_stamp(root):
    """The blob sha in the page-built stamp on origin/roadmap of `root`, or None: no branch, no file, unparseable text and a
    missing or non-hex `blob` all read as missing. One git process, read only."""
    try:
        import _nowindow  # the one home of a no-window child start, as read_origin_main
        done = _nowindow.run(["git", "-C", root, "show", "%s:%s" % (RECORD_REF, RECORD_PATH)],
                             capture_output=True, timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL)
        if done.returncode != 0:
            return None
        blob = json.loads(done.stdout.decode("utf-8", errors="replace")).get("blob")
    except (ImportError, OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return None
    return blob.strip() if isinstance(blob, str) and re.fullmatch(r"[0-9a-f]{40}", blob.strip()) else None


def session_line(root, main_checkout=None):
    """One line about the repo's page, or "". A repo with no page in its extras gives "". No stamp gives "": an unread state is
    never reported as behind. Either stamp (the page-built stamp on origin/roadmap, the local stamp) equal to main's blob gives
    "". Otherwise the behind line. A missing or unreadable page-built stamp leaves the local stamp alone (decision
    page-stale-publish). With stamps but main unreadable, "" too."""
    import layout
    url = layout.waiting_page(root)
    if url == "unknown":
        return ""
    stamps = [x for x in (read_record_stamp(root), read_stamp(root)) if x]
    if not stamps:
        return ""
    blob = main_blob(main_checkout)
    if not blob or blob in stamps:
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
    """One line per open or closed item, in item order within each group, whose answer is still kept: the writer re-reads answers/<id>, routes it if new, then deletes it
    (SKILL.md, "Route and close"). `items` and `answers` are (doc id, data) pairs from load_docs. A closed item with `waits` and a kept answer (a chat
    answer can close an item during a wait) gets its own line, "is closed with waits", whose remedy waits for the wait to end; no gh call. An open
    item gets a line, "is open", only when its kept answer is older than its `added` (a reopened item the writer left a stale record on); an open item
    with a newer record is awaiting filing and is never named. The "is open" lines come first, then the closed lines; each group is in item order.
    Never an arbiter ruling (its overturn answer is read by its own route), a park answer, an answer with no item, or a routed closed item (a
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
    lines, reopened = [], []
    for doc_id, item in items:
        if not isinstance(item, dict):
            continue
        item_id = doc_id if doc_id is not None else item.get("id")  # the file name is the doc id, as for the answers
        if item.get("arbiter") is True or item_id not in kept:
            continue
        if item.get("status") != "closed":
            # An open item is named only when its kept answer is older than its `added`: the writer reopened or reworded it and left the record.
            # A newer record is the owner's answer awaiting filing. An unreadable time names nothing.
            answered, added = parse_utc(kept[item_id].get("at")), parse_utc(item.get("added"))
            if item.get("status") == "open" and answered is not None and added is not None and answered < added:
                reopened.append('kept-answer: item %s (%s) is open and answers/%s is older than its added; re-read answers/%s, route it if new, then delete it '
                             '(SKILL.md, "Route and close")' % (item.get("n", item_id), item_id, item_id, item_id))
            continue
        if isinstance(item.get("lane"), str) and item["lane"] and isinstance(item.get("lastAnswer"), dict):
            continue  # routed: closed at routing, answer kept until the receiver's done report
        if "waits" in item:
            lines.append('kept-answer: item %s (%s) is closed with waits and answers/%s is kept; when its wait has ended, drop waits and delete '
                         'answers/%s (SKILL.md, "Route and close")' % (item.get("n", item_id), item_id, item_id, item_id))
        else:
            lines.append('kept-answer: item %s (%s) is closed and answers/%s is kept; re-read answers/%s, then delete it '
                         '(SKILL.md, "Route and close")' % (item.get("n", item_id), item_id, item_id, item_id))
    return reopened + lines  # the stale open items lead, as they hold the page's wrong state


def read_steps(folder):
    """{step id: status} from the `<step id>.json` files in `folder` (the record's roadmap/data/steps). A step's id is its file name; an `id` field,
    when present, names it too. Raises ValueError with the cause. A file that is not a JSON object with a string status reads as no status."""
    steps = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError as err:
        raise ValueError("%s cannot be read (%s)" % (FOUND_ENV, err.strerror or err))
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        status = data.get("status") if isinstance(data, dict) else None
        if not isinstance(status, str):
            continue
        steps[name[:-len(".json")]] = status
        if isinstance(data.get("id"), str):
            steps.setdefault(data["id"], status)
    return steps


def found_false_lines(items, steps):
    """One line per open item, in `n` order, whose `home` names a step that is done, dropped, folded or done-obsolete: its premise is moot, so the
    writer closes it the same turn (SKILL.md, "Route and close", an item found false). `home` reads as a bare step id or as `step <id>`; any other home (a record
    path, a pointer to a live step) is never flagged. `steps` is {step id: status} from read_steps."""
    lines = []
    # The folder lists docs by file name ("10" before "2"), so order by `n`, which is the order the page shows; an item with no whole `n` goes last.
    ordered = sorted((i for i in items if isinstance(i, dict)), key=lambda i: (not isinstance(i.get("n"), int), i.get("n") if isinstance(i.get("n"), int) else 0))
    for item in ordered:
        if item.get("status") == "closed" or not isinstance(item.get("home"), str):
            continue
        home = item["home"].strip()
        if home.startswith("step "):
            home = home[len("step "):].strip()
        status = steps.get(home)
        if status in FOUND_DONE:
            lines.append("found-false: item %s (%s): its home step %s is %s, so the item is moot; close it this turn: write status closed "
                         "and closed (now), with a reply naming the record that shows it false, and file it as replied (SKILL.md, \"Route and close\")"
                         % (item.get("n", item.get("id", "?")), item.get("id", "?"), home, status))
    return lines


def single_page(argv):
    """Exit 0 current, 1 behind, 2 unknown for one fetched page. Writes a file only with --write, never on unknown.
    With --items, prints after the verdict line one wait line per open item with a `waits` field, and one lane line per open
    item with a `lane` and a `lastAnswer` and no `waits`. With --answers too, one kept-answer line per closed item whose answer is kept, and per open item whose answer is older than its `added`.
    With --items and the env WAITING_PAGE_STEPS (the record's roadmap/data/steps), one found-false line per open item whose `home` step is done, dropped,
    folded or done-obsolete; unset, none.
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
            named = [dict(d, id=k) if k and isinstance(d, dict) else d for k, d in items]
            lines = wait_lines(named, complete)
        except ValueError as err:
            items, named, lines = None, [], ["wait: the items cannot be read: unknown (%s)" % err]
        if args.answers is not None:
            try:
                if items is None:
                    raise ValueError("the items cannot be read")
                answers, answers_complete = load_docs(args.answers, "answers", keyed=True)
                lines += kept_answer_lines(items, answers, complete, answers_complete)
            except ValueError as err:
                lines.append("kept-answer: unknown (%s)" % err)
        if os.environ.get(FOUND_ENV):
            try:
                lines += found_false_lines(named, read_steps(os.environ[FOUND_ENV]))
            except ValueError as err:
                lines.append("found-false: unknown (%s)" % err)
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
    unbaked = unbaked_line(live, "this")
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
    print(("current: matches the template (%s)" if current else "behind: differs from the template (%s)") % source)
    if unbaked:
        print(unbaked)
    return 0 if current and not unbaked else 1


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
        item = item_data[key]
        if routed_answer(item, at) and any(t is not None and t >= at for t in map(parse_utc, reads.get(key, []))):
            pass  # sent to the lane already, and the routing receipt says so: listing it again would re-message the lane
        elif woke is None or at < woke:
            times = [parse_utc(read) for read in reads.get(key, []) if read is not None]
            if any(t is not None and t >= at for t in times):
                pass
            elif any(t is None for t in times):
                unknown.append("unknown: the receipt of answer %s has no readable read" % key)
            else:
                lane = item.get("lane")
                lines.append("answer-unread %s (item %s, owner %s, answered %s, %s%s)" % (
                    key, item.get("n", "?"), item.get("owner", "?"), data(r)["at"],
                    "before wake %s" % woke_text if woke is not None else "before wake: none recorded",
                    ", lane %s" % lane if isinstance(lane, str) and lane else ""))
        if asks_question(data(r)):
            reply_at = parse_utc(item.get("replied")) if item.get("replied") is not None else None
            if item.get("replied") is not None and reply_at is None and has_text(item.get("reply")):
                unknown.append("unknown: the reply on item %s has no readable replied" % key)
            # With `waits` set, `replied` may be only the wait's own change, so a receipt with `read` at or after the answer clears the line instead:
            # the writer's reply and that receipt come in one wake, and the answer is kept during the wait.
            elif ("waits" in item and not any(parse_utc(read) is not None and parse_utc(read) >= at for read in reads.get(key, []) if read is not None)) or (
                    "waits" not in item and not (has_text(item.get("reply")) and reply_at is not None and reply_at > at)):
                lines.append("answer-needs-reply %s (item %s, owner %s, answered %s)" % (
                    key, item.get("n", "?"), item.get("owner", "?"), data(r)["at"]))
    # An open item whose lane wait is flagged (`holdsLane` true) names its lane, whatever its `waits`. `holds` alone is a merge or PR wait: no lane to name.
    for r in entries(items):
        item = data(r)
        if item.get("status") != "closed" and item.get("holdsLane") is True and not has_text(item.get("lane")):
            lines.append("lane-missing %s (item %s, owner %s)" % (r.get("id"), item.get("n", "?"), item.get("owner", "?")))
    out = lines + unknown
    print("\n".join(out) if out else "unread: clean")
    return 2 if unknown else 1 if lines else 0


def routed_answer(item, at):
    """True when the item has a `lane` and a `lastAnswer` whose `at` is the answer's `at` (parsed time `at`): the busy-lane path routed it (SKILL.md, "Already routed")."""
    last = item.get("lastAnswer")
    return has_text(item.get("lane")) and isinstance(last, dict) and at is not None and parse_utc(last.get("at")) == at


def has_text(value):
    """True for a string with a non-blank character."""
    return isinstance(value, str) and bool(value.strip())


def asks_question(answer):
    """True for a `none` answer whose note says something: it needs a written reply on the item (SKILL.md, "Route and close")."""
    return answer.get("choice") == "none" and has_text(answer.get("note"))


def read_doc(path):
    """(id, data, version) of one fetched document: {id, data, version} as ArtifactData get saves it, or bare data. The id and
    version are None when the file does not say. ValueError with the cause when the file cannot be read as an object."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as err:
        raise ValueError("cannot read %s (%s)" % (path, getattr(err, "strerror", None) or err))
    if not isinstance(doc, dict):
        raise ValueError("%s is not a JSON object" % path)
    if isinstance(doc.get("data"), dict) and ("id" in doc or "version" in doc):
        doc_id, version, doc = doc.get("id"), doc.get("version"), doc["data"]
    else:
        doc_id, version = doc.get("id"), None
    if version is not None and not (isinstance(version, int) and not isinstance(version, bool) and version >= 1):
        raise ValueError("%s has a version that is not a whole number above zero" % path)
    return (doc_id if isinstance(doc_id, str) and doc_id else None), doc, version


def close_batch_mode(argv):
    """`--close-batch --item <file> --answer <file> [--receipt <file>] [--reply <text>] [--now <iso>] [--done] [--item-version <n>]
    [--answer-version <n>] [--receipt-version <n>]`: print the one ArtifactData batch payload, {"writes": [...], "pinned": bool}, that closes the item: the receipt set (read and filed), the item update (closed, lastAnswer, and reply with
    replied) and the answer delete. A version flag, else the fetched wrapper's version, pins its write. With a doc unpinned, stderr
    starts with `unpinned: <docs>` and `pinned` is false. An open item with `waits`, or with `lane` and a `lastAnswer.at` equal to the answer's `at`, is refused unless --done."""
    ap = argparse.ArgumentParser(prog="stale_pages.py", allow_abbrev=False)
    ap.add_argument("--close-batch", action="store_true")
    ap.add_argument("--item", required=True)
    ap.add_argument("--answer", required=True)
    ap.add_argument("--receipt")
    ap.add_argument("--reply")
    ap.add_argument("--now")
    ap.add_argument("--done", action="store_true")
    for name in ("item", "answer", "receipt"):
        ap.add_argument("--%s-version" % name, type=int)
    args = ap.parse_args(argv)
    docs, ids, errors = {}, set(), []
    for name in ("item", "answer", "receipt"):
        path = getattr(args, name)
        if path is None:
            continue
        try:
            doc_id, body, version = read_doc(path)
        except ValueError as err:
            errors.append("the %s: %s" % (name, err))
            continue
        docs[name] = (body, version)
        ids.add(doc_id or (body.get("item") if name == "answer" else None))
    ids = {i for i in ids if isinstance(i, str) and i}
    if errors:  # name the id when any readable doc gives it, so the refusal says which close failed
        print("unknown: close of %s refused: %s" % (", ".join(sorted(ids)) or "the item", "; ".join(errors)))
        return 2
    if len(ids) != 1:
        print("unknown: the item, answer and receipt do not name one id (%s)" % (", ".join(sorted(ids)) or "none named"))
        return 2
    doc_id = next(iter(ids))
    answer, answer_version = docs["answer"]
    item, item_version = docs["item"]
    for name in ("item", "answer", "receipt"):
        given = getattr(args, name + "_version")
        if given is not None and given < 1:
            print("unknown: --%s-version of %s is not a whole number above zero" % (name, doc_id))
            return 2
    # A flag version wins over the wrapper's.
    versions = {"item": args.item_version or item_version, "answer": args.answer_version or answer_version,
                "receipt": args.receipt_version or (docs["receipt"][1] if "receipt" in docs else None)}
    # An item with a wait, or one routed to its lane, stays open until the receiver reports the act done (SKILL.md, "Route and close").
    # A lane with a plain pick (no matching lastAnswer) is not routed, so it closes.
    if ("waits" in item or routed_answer(item, parse_utc(answer.get("at")))) and item.get("status") != "closed" and not args.done:
        print("unknown: item waits for a done report (%s has waits or is routed to its lane; pass --done once the act is done)" % doc_id)
        return 2
    if parse_utc(answer.get("at")) is None:
        print("unknown: the answer of %s has no readable at" % doc_id)
        return 2
    now = args.now if args.now else datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if parse_utc(now) is None:
        print("unknown: --now is not an ISO time (%s)" % now)
        return 2
    reply = args.reply
    if asks_question(answer) and not has_text(reply):
        print("unknown: the answer of %s is a none that asks a question: it needs a written reply (--reply <text>)" % doc_id)
        return 2
    last = {k: answer[k] for k in ("choice", "done", "note", "at") if k in answer}
    closed = {"status": "closed", "closed": now, "lastAnswer": last}
    if has_text(reply):
        closed.update(reply=reply, replied=now)
    receipt = {"op": "set", "collection": "receipts", "doc_id": doc_id, "data": {"read": now, "filed": now}}
    update = {"op": "update", "collection": "items", "doc_id": doc_id, "data": closed}
    delete = {"op": "delete", "collection": "answers", "doc_id": doc_id}
    unpinned = [name for name in ("item", "answer", "receipt") if versions[name] is None and (name != "receipt" or "receipt" in docs)]
    for name, write in (("receipt", receipt), ("item", update), ("answer", delete)):
        if versions[name] is not None:
            write["if_version"] = versions[name]
    if unpinned:  # the live get shape is unverified, so an unpinned close is printed, never refused
        print("unpinned: %s" % ", ".join(unpinned), file=sys.stderr)
    payload = {"writes": [receipt, update, delete], "pinned": not unpinned}
    # A plain pick on an item with a lane was never relayed: the closer tells that lane (SKILL.md, step 1 of "Route and close").
    if has_text(item.get("lane")) and item.get("status") != "closed" and not routed_answer(item, parse_utc(answer.get("at"))):
        payload["notify"] = item["lane"].strip()
        print("notify-lane %s" % payload["notify"], file=sys.stderr)
    print(json.dumps(payload, indent=1))
    return 0


AWAITING_ROW = re.compile(r"  \[(?P<who>.+) — (?P<at>\d{4}-\d\d-\d\dT\S+)\]")  # exactly two spaces: a text line has six
AWAITING_ELIDED = re.compile(r"  \[\d+ comments? elided")
AWAITING_BRACKET = re.compile(r"  \[")  # any two-space bracket row; a shape that is not a comment row or a known header row is unknown
AWAITING_HEADER_ROW = re.compile(r"  \[(?:location|anchored at|region of|on text)\]")
AWAITING_CUT = re.compile(r"\[\d+ more threads? not listed")
AWAITING_FIRST_PAGE = re.compile(r"(?:\d+|No) comment threads?\b")
AWAITING_CLAUDE = "Claude (via the user)"  # the tool's one label for Claude's comment; a viewer named Claude Reyes is not it
AWAITING_END_LABELS = ("Done", "Deviations", "Next")  # the bold labels that end the Input Needed section
AWAITING_LABEL = re.compile(r"\*\*(?P<name>Input Needed|%s):?\*\*:?" % "|".join(AWAITING_END_LABELS))
AWAITING_COUNT = re.compile(r"(?:> )?(?:- )?(?:\*\*)?Awaiting reply:(?:\*\*)? (\d+)\b")


def awaiting_threads(text):
    """Parses threads.txt. Returns (threads, unknown): each thread is a dict of id, status, rows (who, at) and location."""
    threads, unknown, cur, cuts, last_head, seen = [], [], None, [], -1, set()
    lines = [line.rstrip() for line in text.splitlines()]  # a trailing space must not hide a header or a row
    for i, line in enumerate(lines):
        head = re.fullmatch(r"Thread (\S+)", line)
        if head:
            last_head = i
            status = lines[i + 1].strip() if i + 1 < len(lines) else ""
            cur = {"id": head.group(1), "rows": [], "location": None,
                   "status": "open" if status.startswith("open") else "resolved" if status.startswith("resolved") else None}
            if cur["id"] in seen:
                # A page appended twice: its rows go to a copy that is never listed, so no thread is named twice.
                unknown.append("unknown: thread %s appears twice" % cur["id"][:8])
                continue
            seen.add(cur["id"])
            threads.append(cur)
            if cur["status"] is None:
                unknown.append("unknown: thread %s has no open or resolved status line" % cur["id"][:8])
        elif AWAITING_CUT.match(line):
            cuts.append((i, line))
            cur = None
        elif cur is not None:
            row = AWAITING_ROW.fullmatch(line)
            if line.startswith("  [location] "):
                cur["location"] = line[len("  [location] "):].strip()
            elif row:
                cur["rows"].append((row.group("who"), row.group("at")))
            elif AWAITING_BRACKET.match(line) and not AWAITING_HEADER_ROW.match(line) and cur["status"] != "resolved":
                # A resolved thread cannot be awaiting, so a row it hides is no cut. An open thread's elided row may hide the last comment.
                what = "has elided comments" if AWAITING_ELIDED.match(line) else "has a row of an unknown shape (%s)" % line[:40]
                unknown.append("unknown: thread %s %s" % (cur["id"][:8], what))
    # A cut line is read through when a later page's thread block follows it; with none after it, the list is cut.
    unknown += ["unknown: the read is cut (%s)" % line[:60] for i, line in cuts if i > last_head]
    for t in threads:
        if t["status"] == "open" and not t["rows"] and not any(t["id"][:8] in u for u in unknown):
            unknown.append("unknown: open thread %s has no comment rows" % t["id"][:8])
    return threads, unknown


def awaiting_input_needed(lines):
    """The text after the first bold Input Needed label, up to the next bold Done, Deviations or Next label, else ''.
    This is a second parser of the report form beside lint/report_guard.py report_section. It stays because that one reads
    only a blockquoted block (report.md may carry unquoted lines) and its module loads the whole hook layer. It must accept
    the same label forms: a colon inside or after the bold, a blockquote, and text on the label line."""
    body, inside = [], False
    for line in lines:
        label = AWAITING_LABEL.match(line)
        if label and label.group("name") in AWAITING_END_LABELS:
            if inside:
                break
        elif label and not inside:
            inside = True
            body.append(line[label.end():])
            continue
        if inside:
            body.append(line)
    return "\n".join(body)


def awaiting_report(report, waiting):
    """The report-missing and report-count lines for the awaiting id8s `waiting`: none when the report is right."""
    lines = [re.sub(r"^\s*>[ \t]?", "", line).rstrip() for line in report.splitlines()]  # a blockquote marker and trailing space are no part of a line
    body = awaiting_input_needed(lines)
    out = ["report-missing " + t for t in waiting if not re.search(r"(?<![0-9a-f])%s(?![0-9a-f])" % t, body)]
    counts = [m.group(1) for m in map(AWAITING_COUNT.match, lines) if m]
    wrong = [c for c in counts if int(c) != len(waiting)]
    if not counts or wrong:
        out.append("report-count %s expected %d" % (wrong[0] if wrong else "none", len(waiting)))
    return out


def awaiting_mode(argv):
    """`--awaiting <dir>`: name each open thread whose last comment is not Claude's, from threads.txt, and check report.md lists them."""
    ap = argparse.ArgumentParser(prog="stale_pages.py", allow_abbrev=False)
    ap.add_argument("--awaiting", required=True)
    args = ap.parse_args(argv)
    try:
        with open(os.path.join(args.awaiting, "threads.txt"), encoding="utf-8") as f:
            text = f.read()
    except (OSError, ValueError) as err:
        print("unknown: cannot read threads.txt in %s (%s)" % (args.awaiting, err))
        return 2
    if not text.strip():
        print("unknown: threads.txt in %s is empty" % args.awaiting)
        return 2
    # The header is the first line before any Thread line; the tool's notice lines above it are skipped.
    # A file that reaches a Thread line first is a continuation page, which lists only some of the threads.
    above = []
    for line in text.splitlines():
        if re.fullmatch(r"Thread \S+\s*", line):
            break
        above.append(line.strip())
    if not any(AWAITING_FIRST_PAGE.match(line) for line in above):
        print("unknown: threads.txt does not start with the first page")
        return 2
    threads, unknown = awaiting_threads(text)
    waiting = [t for t in threads if t["status"] == "open" and t["rows"] and t["rows"][-1][0] != AWAITING_CLAUDE]
    lines = ["thread-awaiting %s (last comment %s, %s)" % (t["id"][:8], t["rows"][-1][1], t["location"] or "no location") for t in waiting]
    if unknown:
        print("\n".join(lines + unknown))
        return 2
    try:
        with open(os.path.join(args.awaiting, "report.md"), encoding="utf-8") as f:
            report = f.read()
    except FileNotFoundError:
        report = None
    except (OSError, ValueError) as err:  # a report that is there and cannot be read is never read as absent
        print("unknown: cannot read report.md in %s (%s)" % (args.awaiting, err))
        return 2
    if report is not None:
        bad = awaiting_report(report, [t["id"][:8] for t in waiting])
        print("\n".join(bad) if bad else "awaiting-report: ok (%d listed)" % len(waiting))
        return 1 if bad else 0
    print("\n".join(lines) if lines else "awaiting: clean")
    return 1 if lines else 0


def main(argv):
    if "--close-batch" in argv:
        return close_batch_mode(argv)
    if "--unread" in argv:
        return unread_mode(argv)
    if "--awaiting" in argv:
        return awaiting_mode(argv)
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
                 "       stale_pages.py --unread <dir>\n"
                 "       stale_pages.py --close-batch --item <file> --answer <file> [--receipt <file>] [--reply <text>] [--now <iso>] [--done]\n"
                 "                      [--item-version <n>] [--answer-version <n>] [--receipt-version <n>]\n"
                 "       stale_pages.py --awaiting <dir>")
    import layout  # batch mode only
    fetched, roots = argv[0], argv[1:] or default_roots()
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()
    try:
        pages = layout.live_pages(roots)
    except layout.LayoutError as err:
        sys.exit("stale_pages: %s" % err)
    counts = {"current": 0, "behind": 0, "unknown": 0, "not-found": 0}
    unbaked = 0
    for owner, url in pages:
        word, why = verdict(url, fetched, template)
        counts[word] += 1
        print("%s: %s%s (%s)" % (word, owner, " - " + why if why else "", url))
        if word in ("current", "behind"):  # the page was read, so the fetched file exists
            line = unbaked_line(fetched_text(url, fetched), owner)
            if line:
                unbaked += 1
                print(line)
    print("waiting pages: %d current, %d behind, %d unknown, %d not-found"
          % (counts["current"], counts["behind"], counts["unknown"], counts["not-found"]))
    return 0 if counts["current"] == len(pages) and not unbaked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
