#!/usr/bin/env python3
"""At Stop, blocks once when the owner's feedback inbox needs the session: a message of a burst with no item lines, a bad item line, a ruling or task whose home is not a tracked file of its kind, a page item or a chat page pick with no send to the page writer, a grant word with no home, a closed note with no home, or an open standing item whose id is missing from the handoff.

Reads <config dir>/handoffs/<session_id>.inbox.md, which local_time.py writes for every owner message,
and the session's handoff beside it. A burst is the messages saved since the last Stop when they are
two or more, or one message of three or more non-blank lines or two or more bullet lines (BULLET).
Only a burst's messages need items: a lone short message never triggers the guard. The turn state file
<session_id>.inbox.turns (local_time.inbox_paths) holds how many messages earlier Stops saw and which
were bursts. Each Stop updates it, even with stop_hook_active, so a message is classed once, in the
turn it arrived. A missing or damaged state file counts every saved message as this turn's. It blocks
a turn end in these cases:
  - a burst's message has no item lines under it. The reason gives the inbox file's absolute path, the
    message's heading line and its line number, and an example item. Items added in any later turn
    count, because each Stop reads the whole file;
  - an item line is not `- <id> [<kind>] -> <home>`, kind one of ruling, task, question, note, standing, page
    (KIND_WORDS: the home each kind without a file home takes);
  - a ruling or task item, open or closed, whose home is not a file under a home of its kind
    (HOME_KINDS, paths from lint/layout.py for the repo of the hook's cwd) that some branch's tree
    holds (ruling_home.value_resolves). Memory and the handoff hold only in-flight notes, so they
    never count for these two kinds (rule building-memory-is-short-term). A home outside them is
    reported as "<path> is not a tracked <kind> home", with the homes listed (kind_homes). When the cwd is in no git
    repo, or the layout cannot be read, these homes pass unchecked and a systemMessage says so;
  - an open page item (`[page] -> page:<n>`: the owner answers waiting-page item n; checked in
    every block that holds one, burst or not; a `[closed]` one is never checked) has a home that is not
    `page:<digits>`, or the session's transcript shows no send after the owner's message: send_message
    or SendMessage naming n as a whole token, or an ArtifactData set, update or batch whose input has
    key n equal to the item number under collection `items` (Pages; lint/_transcript.py reads the
    transcript). The k-th block with text T anchors to the k-th owner record with text T, line ends made
    the same. Owner records are user records and queued_command attachments (_transcript.owner_text):
    a peer's words and machine notices never count. A missing or unreadable transcript passes every
    block with a systemMessage. A block with no owner record for its text passes with a systemMessage,
    and the other blocks are still checked;
  - page-chat-answer-lands. An owner block whose whole text is page picks (PICK: `<n> <letter>`, an
    optional parenthetical, comma-separated), in a repo whose extras name a waiting page
    (layout.waiting_page, as for any waiting-page read), needs for each n the same send proof
    Pages.sent accepts. An n that an open page item of the block names is left to that item's check.
    A block that also holds a non-page item is not checked. Risk kind: named incident. F46 (the
    answer "143 b" never reached the page writer) and F43 ("99 a (done)", same shape), in the
    owner-feedback audit (claude-settings draft PR #1008, docs/plans/owner-feedback-audit.md).
    Landed 2026-11-02. Cost: the transcript is read only for a pick block in a repo with a waiting
    page, or for an open page item. No file written, no process started. The cost case proves it;
  - chat-grant-needs-home. An owner block whose text holds a grant word (GRANT: approval, approve,
    approved, grant, granted, authorize, authorized, go ahead, "permission to", "permissions to";
    whole words, any case; a bare "permission" is none) needs one real item line of these: a
    `[ruling]` item (its home gets the check above), an open `[page]` item (its send gets the check
    above), or `[note] -> not-a-grant`. Lines inside the message's fence are text, never items. For
    a block with a grant word, a ruling home may also be `settings.json` or `.claude/CLAUDE.md` at
    the repo root (GRANT_ROOT_HOMES), if some branch tracks it. A lone short message counts. Risk
    kind: named incident. F47 (an all-repos grant left in chat) and F31 (a grant homed to the
    handoff), same audit. Landed 2026-11-02. Cost: one regex on text already in memory;
  - inbox-close-needs-home. A `[closed]` note needs a home that is a file some branch tracks,
    `step:<slug>` (roadmap/data/steps/<slug>.json, resolved by ruling_home.value_resolves), `page:<n>`
    or `not-a-grant`. `noted` is not one. A closed `[question] -> answered` is never checked. Risk
    kind: likely risk. F88 (a closed note with no step, record or answer behind it) is the related
    incident, not a measured one. Landed 2026-11-02. Cost: one git read per closed note;
  - an open standing item has an id that is not a whole token in the handoff;
  - the inbox cannot be read. The block names the file: a Stop hook's stderr never reaches the owner,
    so a silent pass would drop feedback. This stays advisory, per decision guard-hooks-fail-closed:
    `stop_hook_active` true exits with no output, so the block costs one turn at most.
Format: see hooks/test_feedback_inbox.py. Exit 0 always. Any other error goes to stderr and passes.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

LINT = os.path.join(HERE, "..", "lint")
if LINT not in sys.path:
    sys.path.insert(0, LINT)

import _transcript  # noqa: E402  the one home of the transcript readers and the owner-record test
import local_time  # noqa: E402  the one home of the inbox paths
import ruling_home  # noqa: E402  the one home of "a branch's tree holds this file"
import precompact_handoff  # noqa: E402  the one home of the handoff path
from shared_names import MACHINE_TAGS  # noqa: E402  the one home of the machine notice tags

ITEM = re.compile(r"- (fb-\S+)(?:\s+(.*))?$")
KINDS = ("ruling", "task", "question", "note", "standing", "page")
JOT = re.compile(r"\[(%s)\]\s+->\s+\S" % "|".join(KINDS))
PAGE_HOME = re.compile(r"page:(\d+)")
STEP_HOME = re.compile(r"step:([A-Za-z0-9_-]+)")
STEP_PATH = "roadmap/data/steps/%s.json"  # where a `step:<slug>` home resolves, as a blob on some ref
NOT_A_GRANT = "not-a-grant"  # the home of a [note] that says its grant word is no grant
# A chat pick answers waiting-page item n: `<n> <letter>`, an optional parenthetical, comma-separated.
_ONE_PICK = r"\d+[ \t]+[A-Za-z](?:[ \t]*\([^)\n]*\))?"
PICK = re.compile(r"%s(?:[ \t]*,[ \t]*%s)*" % (_ONE_PICK, _ONE_PICK))
# Whole words, any case. A bare "permission" is no grant word, so a pasted "Permission denied" passes.
GRANT = re.compile(r"(?<![A-Za-z0-9_])(?:approval|approved?|grant(?:ed)?|authorized?|go ahead|permissions? to)"
                   r"(?![A-Za-z0-9_])", re.IGNORECASE)
# A grant's [ruling] home may also be one of these root files, when git tracks it on some branch.
GRANT_ROOT_HOMES = ("settings.json", ".claude/CLAUDE.md")
SEND_TOOLS = ("mcp__claude-code-remote__send_message", "SendMessage")
ARTIFACT_DATA = ("ArtifactData", "mcp__ArtifactData")
WRITE_VERBS = ("set", "update", "batch")
HEADING_PREFIX = local_time.HEADING_PREFIX  # the heading and stamp the writer emits
HEADER = re.compile(re.escape(HEADING_PREFIX) + local_time.STAMP_PATTERN + "$")
STAMP_HHMM = re.compile(local_time.STAMP_PATTERN)
# The home each kind without a file home takes, as the decision gives it.
KIND_WORDS = {"question": "answered", "note": "noted (closed: a tracked file, step:<slug> or page:<n>; "
              "not-a-grant when a grant word is no grant)", "standing": "handoff", "page": "page:<n>"}
EXAMPLE_KIND = "note"  # a key of KIND_WORDS
EXAMPLE_HOME = "noted"
OPEN_KINDS = ("[ruling]", "[task]", "[standing]")
# Layout keys (lint/layout.json, or a repo's extras file) whose paths may hold each kind's home.
HOME_KINDS = {"ruling": ("decisions", "rules", "claude-md", "agents-md"),
              "task": ("todo", "debts", "debt-notes")}
FAIL_OPEN = "Feedback guard: ruling and task homes not checked (%s)."
FAIL_OPEN_PAGES = "Feedback guard: page sends not checked (%s)."
GRANT_HOMES = ("a [ruling] item whose home is a tracked file, a [page] item `page:<n>` with its send, or a"
               " [note] item `-> %s` when the words are no grant" % NOT_A_GRANT)
BULLET = re.compile(r"[ \t]*(?:[-*+\u2022]|\d+[.)])[ \t]+\S")


def is_burst(texts):
    """True when one turn's messages need items: two or more, or one with three or more non-blank
    lines or two or more bullet lines."""
    if len(texts) != 1:
        return len(texts) > 1
    lines = [ln for ln in (texts[0] or "").split("\n") if ln.strip()]
    return len(lines) >= 3 or sum(1 for ln in lines if BULLET.match(ln)) >= 2


def burst_indexes(blocks, turns):
    """Classes the messages saved since the last Stop, records them in the turn state file, and
    returns the indexes of every burst message so far. A write failure goes to stderr: the next
    Stop then counts these messages again, as part of its own turn."""
    try:
        with open(turns, encoding="utf-8") as f:
            state = json.load(f)
        seen, burst = min(int(state["seen"]), len(blocks)), {int(i) for i in state["burst"]}
    except (OSError, ValueError, KeyError, TypeError):
        seen, burst = 0, set()
    if is_burst([b["text"] for b in blocks[seen:]]):
        burst.update(range(seen, len(blocks)))
    try:
        with open(turns, "w", encoding="utf-8") as f:
            json.dump({"seen": len(blocks), "burst": sorted(burst)}, f)
    except OSError as e:
        print("feedback_guard: turn state not saved: %s" % e, file=sys.stderr)
    return burst


def parse(text):
    """[{stamp, line, text, items}] from the inbox, `line` being the heading's 1-based line number. Lines inside a fence are never headers or items, and a
    `### ` line that is not the hook's own Central header is plain text."""
    blocks, fence = [], None
    for number, ln in enumerate(text.split("\n"), 1):
        ln = ln.rstrip("\r")
        if fence is not None:
            if re.fullmatch(r"`+", ln) and len(ln) >= len(fence):
                fence = None
            else:
                blocks[-1]["text"] = ln if blocks[-1]["text"] is None else blocks[-1]["text"] + "\n" + ln
        elif HEADER.match(ln):
            blocks.append({"stamp": ln[len(HEADING_PREFIX):], "line": number, "text": None, "items": [],
                           "fenced": False})
        elif blocks and not blocks[-1]["fenced"] and re.fullmatch(r"`{3,}", ln):
            fence, blocks[-1]["fenced"] = ln, True
        elif blocks and ln.startswith("- fb-"):
            blocks[-1]["items"].append(ln)
    return blocks


def item(ln):
    """(id, rest, jotted, closed) for an item line, or None when the line is malformed."""
    m = ITEM.match(ln)
    if m is None:
        return None
    rest = m.group(2) or ""
    return m.group(1), rest, JOT.match(rest) is not None, rest.rstrip().endswith("[closed]")


def open_ids(blocks, kinds=OPEN_KINDS):
    """Ids of well-formed, not closed, open items (ruling, task, standing, or `kinds`), in file order."""
    ids = []
    for b in blocks:
        for ln in b["items"]:
            it = item(ln)
            if it and it[2] and not it[3] and it[1].startswith(kinds):
                ids.append(it[0])
    return ids


def example_item(stamp):
    """An item line the check accepts (ITEM and JOT) for the message at `stamp`: id `fb-HHMM-1`."""
    m = STAMP_HHMM.match(stamp)
    return "- fb-%s%s-1 [%s] -> %s" % (m.group(1), m.group(2), EXAMPLE_KIND, EXAMPLE_HOME) if m else None


def no_items_problem(block, inbox, homes_line=""):
    """The reason for a burst message with no items: where the items go, what one looks like, and each kind's home."""
    first = (block["text"] or "").split("\n")[0][:40]
    where = "add items under the line `%s%s` (line %d of %s)" % (HEADING_PREFIX, block["stamp"], block["line"], inbox)
    example = example_item(block["stamp"])
    return "the message at %s (%s) has no items: %s%s%s" % (
        block["stamp"], first, where, ", one per line, for example `%s`" % example if example else "",
        ". Kind homes: %s" % homes_line if homes_line else "")


def kind_homes(layout, root, kind):
    """The paths under `root` that may hold a `kind` item's home: each HOME_KINDS layout key the
    repo has, as its layout path and its base path, that exist. The check and the block text both use it."""
    known, base = layout.kinds(root), layout.layout()["kinds"]
    homes = []
    for key in HOME_KINDS[kind]:
        if key in known:
            homes += [layout.path(root, key)] + ([base[key]["path"].strip("/")] if key in base else [])
    return [h for h in dict.fromkeys(homes) if os.path.exists(os.path.join(root, *h.split("/")))]


def home_word(rest):
    """The first word after `->`, or "" when there is none."""
    words = rest.split("->", 1)[1].split() if "->" in rest else []
    return words[0] if words else ""


def home_path(rest):
    """The path a ruling or task item names: the first word after `->`, unwrapped of backticks or
    quotes, without a `#anchor` and trailing punctuation."""
    word = rest.split("->", 1)[1].split()[0]
    word = ruling_home._unwrap(word).split("#", 1)[0]
    return word.rstrip(":,;.")


class Homes:
    """Checks ruling and task homes against the layout. `skip` holds the reason the check stood
    down, once, for the systemMessage line."""

    def __init__(self, cwd):
        self.cwd, self.skip = cwd, None

    def _root(self, where):
        run = ruling_home._run_git(where, ["rev-parse", "--show-toplevel"])
        return os.path.realpath(run.stdout.strip()) if run.returncode == 0 and run.stdout.strip() else None

    def _locate(self, found):
        """(root, rel, error) for the path a home names. `root` is None with `error` set when an absolute
        path is in no git repo, and with no error when the session's folder is in none: the check stands down."""
        if os.path.isabs(found):
            parent = os.path.dirname(found)
            root = self._root(parent) if os.path.isdir(parent) else None
            if root is None:
                return None, None, "names %s, which is in no git repo" % found
            return root, os.path.relpath(os.path.realpath(found), root).replace(os.sep, "/"), None
        start = self.cwd if self.cwd and os.path.isdir(self.cwd) else None
        root = self._root(start) if start else None
        if root is None:
            self.skip = self.skip or "the session's folder is in no git repo"
            return None, None, None
        return root, os.path.normpath(found).replace(os.sep, "/"), None

    def problem(self, item_id, kind, rest, grant=False):
        """None when the home is good or the check stood down, else the reason text. `grant` is true in a
        block that holds a grant word: a ruling may then name a GRANT_ROOT_HOMES file, if git tracks it."""
        try:
            import layout  # lint/layout.py, the one home of where each kind lives
        except ImportError as e:
            return self._stand_down(e)
        try:
            root, rel, err = self._locate(home_path(rest))
            if err:
                return "%s [%s] %s" % (item_id, kind, err)
            if root is None:
                return None
            if not (grant and kind == "ruling" and rel in GRANT_ROOT_HOMES):
                homes = kind_homes(layout, root, kind)
                keys = ", ".join(HOME_KINDS[kind])
                if not homes:
                    return ("%s [%s]: this repo has no %s home; none of the layout keys %s is in it"
                            % (item_id, kind, kind, keys))
                if not any(rel == h or rel.startswith(h + "/") for h in homes):
                    return ("%s [%s]: %s is not a tracked %s home. %s homes: %s. The handoff and memory are no home"
                            % (item_id, kind, rel, kind, kind.capitalize(), ", ".join(homes)))
            if not ruling_home.value_resolves(rel, root):
                return "%s [%s]: its home is not a file that git tracks on any branch" % (item_id, kind)
            return None
        except (layout.LayoutError, ruling_home._GitFailure) as e:
            return self._stand_down(e)

    def closed_problem(self, item_id, rest):
        """None when a closed note's home is a page, a not-a-grant verdict, a `step:<slug>` whose step file
        some branch holds, or a file git tracks; else the reason text. None too when the check stood down."""
        word = home_word(rest)
        if PAGE_HOME.fullmatch(word) or word == NOT_A_GRANT:
            return None
        step = STEP_HOME.fullmatch(word)
        try:
            root, rel, err = self._locate(STEP_PATH % step.group(1) if step else home_path(rest))
            if err:
                return "%s [note] %s" % (item_id, err)
            if root is None or ruling_home.value_resolves(rel, root):
                return None
        except ruling_home._GitFailure as e:
            return self._stand_down(e)
        return ("%s [note] is closed with no home: a closed note needs a tracked file, `step:<slug>` naming a"
                " step file that some branch holds, or `page:<n>`" % item_id)

    def has_waiting_page(self):
        """(found, why): `found` is true when the repo of the session's folder names a waiting page
        (layout.waiting_page, the one home of that read). `why` holds the reason the read stood down."""
        try:
            import layout
        except ImportError as e:
            return False, " ".join(str(e).split()) or "ImportError"
        try:
            start = self.cwd if self.cwd and os.path.isdir(self.cwd) else None
            root = self._root(start) if start else None
            return (root is not None and layout.waiting_page(root) != "unknown"), None
        except (layout.LayoutError, ruling_home._GitFailure) as e:
            return False, " ".join(str(e).split()) or type(e).__name__

    def homes_line(self):
        """`ruling -> <homes>; task -> <homes>; question -> answered; ...` for every kind in KINDS. The file homes
        come from kind_homes; when the layout or the repo cannot be read, such a kind names "a tracked file"."""
        found = {}
        try:
            import layout
        except ImportError:
            layout = None
        if layout is not None:
            try:
                start = self.cwd if self.cwd and os.path.isdir(self.cwd) else None
                root = self._root(start) if start else None
                if root is not None:
                    found = {k: kind_homes(layout, root, k) for k in HOME_KINDS}
            except (layout.LayoutError, ruling_home._GitFailure):
                found = {}
        return "; ".join("%s -> %s" % (k, KIND_WORDS[k] if k in KIND_WORDS
                                       else ", ".join(found.get(k) or ()) or "a tracked file") for k in KINDS)

    def _stand_down(self, e):
        self.skip = self.skip or " ".join(str(e).split()) or type(e).__name__
        return None


class Pages:
    """Checks that each page item's number was sent to the page writer after the owner's message.
    The transcript loads once, on the first open page item. `skip` holds the reasons a block stood
    down, for the systemMessage line. An unreadable transcript stands down every block; a block with
    no owner record stands down alone."""

    def __init__(self, path):
        self.path, self.records, self.owners, self.unread, self.skip = path, None, None, False, []

    def _load(self):
        if self.records is None:
            self.records, self.owners = [], []
            try:
                if not self.path:
                    raise OSError("no transcript_path in the payload")
                self.records = _transcript.read_transcript(self.path)
            except (OSError, ValueError) as e:
                self.unread = True
                self.skip.append("the transcript cannot be read: %s" % (" ".join(str(e).split())
                                                                       or type(e).__name__))
            for i, rec in enumerate(self.records):
                text = _transcript.owner_text(rec, MACHINE_TAGS)
                if text is not None:
                    self.owners.append((i, norm(text)))
        return not self.unread

    def sent(self, text, k, n, stamp):
        """True when a send naming item n follows the owner record that anchors the k-th block with
        this text. True too when the check stands down: no transcript, or no such owner record."""
        if not self._load():
            return True
        anchors = [i for i, said in self.owners if said == text]
        if len(anchors) < k:
            self.skip.append("the transcript has no owner record %d for the message at %s" % (k, stamp))
            return True
        return any(_proves(use, n) for r in self.records[anchors[k - 1] + 1:] if r.get("type") == "assistant"
                   for use in _transcript.tool_uses(r))


def norm(text):
    """A message text with CRLF and CR line ends made LF, ends trimmed."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _proves(use, n):
    """True when a tool_use sends page item n: a message naming n as a whole token, or an
    ArtifactData write with key n == n under collection `items`."""
    name, tool_input = use.get("name") or "", use.get("input")
    if not isinstance(tool_input, dict):
        return False
    if name in SEND_TOOLS:
        msg = tool_input.get("message")
        return isinstance(msg, str) and re.search(r"(?<![A-Za-z0-9-])%s(?![A-Za-z0-9-])" % n, msg) is not None
    return name.startswith(ARTIFACT_DATA) and _writes_n(tool_input, n)


def _in_items(d):
    return (d.get("collection") == "items"
            or any(isinstance(d.get(k), str) and d[k].startswith("items/") for k in ("doc_id", "path")))


def _is_write(d):
    """False for a dict whose action or op is a verb other than set, update, batch."""
    verb = d.get("action", d.get("op"))
    return not isinstance(verb, str) or verb in WRITE_VERBS


def _has_n(node, n):
    if isinstance(node, dict):
        if not _is_write(node):
            return False
        v = node.get("n")
        if (isinstance(v, int) and not isinstance(v, bool) and v == int(n)) or (
                isinstance(v, str) and v.isdigit() and int(v) == int(n)):
            return True
        return any(_has_n(c, n) for c in node.values())
    return isinstance(node, list) and any(_has_n(c, n) for c in node)


def _writes_n(node, n):
    """True when a write dict that names the items collection holds key n == n at any depth below it."""
    if isinstance(node, dict):
        if not _is_write(node):
            return False
        return (_in_items(node) and _has_n(node, n)) or any(_writes_n(c, n) for c in node.values())
    return isinstance(node, list) and any(_writes_n(c, n) for c in node)


def page_problem(item_id, rest, text, k, stamp, pages):
    """None when the page item's home is page:<n> and the send is proved, or the check stood down."""
    m = PAGE_HOME.fullmatch(home_word(rest))
    if m is None:
        return "%s [page] has a malformed page home: it needs `page:<digits>`" % item_id
    if pages is None or pages.sent(text, k, m.group(1), stamp):
        return None
    return ("%s [page] page:%s: the transcript shows no send of the owner's ruling to the page writer after"
            " the owner's message; send the ruling to the page writer (send_message naming %s, or an"
            " ArtifactData write with n %s)" % (item_id, m.group(1), m.group(1), m.group(1)))


def pick_numbers(text):
    """The item numbers of a message that is only page picks (`143 b`, `137 a, 138 b (done)`), else []."""
    return re.findall(r"\d+", re.sub(r"\([^)\n]*\)", "", text)) if PICK.fullmatch(text) else []


def pick_problem(b, text, k, homes, pages):
    """The reason for a pick message with an item number the transcript shows no send for, else None.
    Runs for a pick block with no item but page items (a pick beside another item is a known gap), in a
    repo with a waiting page. Open page items check their own numbers. The transcript loads only here."""
    picks = pick_numbers(text)
    items = [item(ln) for ln in b["items"]]
    if not picks or homes is None or pages is None or any(
            it is None or not it[1].startswith("[page]") for it in items):
        return None
    found, why = homes.has_waiting_page()
    if why:
        pages.skip.append(why)
    if not found:
        return None
    own = {m.group(1) for it in items if it and not it[3] for m in [PAGE_HOME.fullmatch(home_word(it[1]))] if m}
    unsent = [n for n in dict.fromkeys(picks) if n not in own and not pages.sent(text, k, n, b["stamp"])]
    if not unsent:
        return None
    return ("the owner's page pick at %s names item %s, and the transcript shows no send of it to the page"
            " writer after the owner's message; send each pick to the page writer (send_message naming the item"
            " number, or an ArtifactData write with n set to it)" % (b["stamp"], ", ".join(unsent)))


def grant_problem(b, text, items):
    """The reason for a message with a grant word and no home for it, else None. A home is a [ruling] item
    (its own check judges the path), an open [page] item (its own check judges the send), or a
    `[note] -> not-a-grant` item. `items` holds item() of each item line of the block."""
    if not GRANT.search(text):
        return None
    for it in items:
        if it is None or not it[2]:
            continue
        if it[1].startswith("[ruling]") or (it[1].startswith("[page]") and not it[3]) or (
                it[1].startswith("[note]") and home_word(it[1]) == NOT_A_GRANT):
            return None
    return ("the message at %s (%s) holds a grant word and has no home for it: add %s"
            % (b["stamp"], text.split("\n")[0][:40], GRANT_HOMES))


def problems(blocks, handoff, homes=None, burst=(), pages=None, inbox=""):
    out, seen = [], {}
    for n, b in enumerate(blocks):
        text = norm(b["text"])
        seen[text] = seen.get(text, 0) + 1
        if not b["items"] and n in burst:
            out.append(no_items_problem(b, inbox, homes.homes_line() if homes is not None else ""))
        grant = GRANT.search(text) is not None
        for found in (pick_problem(b, text, seen[text], homes, pages),
                      grant_problem(b, text, [item(ln) for ln in b["items"]])):
            if found:
                out.append(found)
        for ln in b["items"]:
            it = item(ln)
            if it is None:
                out.append("the item line `%s` is malformed: it needs `- <id> [kind] -> home`" % ln[2:])
            elif not it[2]:
                out.append("%s needs `[kind] -> home`, kind one of %s" % (it[0], ", ".join(KINDS)))
            elif it[1].startswith("[page]"):
                found = None if it[3] else page_problem(it[0], it[1], text, seen[text], b["stamp"], pages)
                if found:
                    out.append(found)
            elif homes is not None and it[1].startswith(("[ruling]", "[task]")):
                found = homes.problem(it[0], it[1][1:it[1].index("]")], it[1], grant)
                if found:
                    out.append(found)
            elif homes is not None and it[3] and it[1].startswith("[note]"):
                found = homes.closed_problem(it[0], it[1])
                if found:
                    out.append(found)
        for i in open_ids([b], ("[standing]",)):
            if not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(i), handoff):
                out.append("%s is not in the handoff" % i)
    return out


def main():
    try:
        hook = json.load(sys.stdin)
        paths = local_time.inbox_paths(hook.get("session_id"))
        if paths is None:
            return 0
        inbox, turns = paths
        inbox = os.path.abspath(inbox)  # CLAUDE_CONFIG_DIR may be relative; the reason promises an absolute path
        out = {}
        try:
            with open(inbox, encoding="utf-8") as f:
                blocks = parse(f.read())
        except FileNotFoundError:
            return 0
        except (OSError, UnicodeDecodeError):
            blocks = None
        if blocks is not None:
            burst = burst_indexes(blocks, turns)
        if hook.get("stop_hook_active"):
            return 0
        if blocks is None:
            reasons = ["the inbox file %s cannot be read" % os.path.basename(inbox)]
        else:
            try:
                with open(precompact_handoff.handoff_path(hook["session_id"]), encoding="utf-8",
                          errors="replace") as f:
                    handoff = f.read()
            except OSError:
                handoff = ""
            homes, pages = Homes(hook.get("cwd")), Pages(hook.get("transcript_path"))
            reasons = problems(blocks, handoff, homes, burst, pages, inbox)
            notes = ([FAIL_OPEN % homes.skip] if homes.skip else []) + (
                [FAIL_OPEN_PAGES % "; ".join(pages.skip)] if pages.skip else [])
            if notes:
                out["systemMessage"] = " ".join(notes)
        if reasons:
            out.update(decision="block", reason="Feedback inbox: " + "; ".join(reasons)
                       + ". The check reads the inbox file at each Stop, so items added in any later turn count,"
                       " and no new heading is needed. Send each page ruling to the page writer, and put open"
                       " standing ids in the handoff.")
        if out:
            print(json.dumps(out))
    except Exception as e:  # advisory: a crash passes, and says so on stderr
        print("feedback_guard: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
