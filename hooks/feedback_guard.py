#!/usr/bin/env python3
"""At Stop, blocks once when the owner's feedback inbox needs the session: a message of a burst with no item lines, a bad item line, a ruling or task whose home is not a tracked file of its kind, an answer with no send to the page writer, or an open standing item whose id is missing from the handoff.

Reads <config dir>/handoffs/<session_id>.inbox.md, which local_time.py writes for every owner message,
and the session's handoff beside it. A burst is the messages saved since the last Stop when they are
two or more, or one message of three or more non-blank lines or two or more bullet lines (BULLET).
Only a burst's messages need items: a lone short message never triggers the guard. The turn state file
<session_id>.inbox.turns (local_time.inbox_paths) holds how many messages earlier Stops saw and which
were bursts. Each Stop updates it, even with stop_hook_active, so a message is classed once, in the
turn it arrived. A missing or damaged state file counts every saved message as this turn's. It blocks
a turn end in these cases:
  - a burst's message has no item lines under it;
  - an item line is not `- <id> [<kind>] -> <home>`, kind one of ruling, task, question, note, standing, answer;
  - a ruling or task item, open or closed, whose home is not a file under a home of its kind
    (HOME_KINDS, paths from lint/layout.py for the repo of the hook's cwd) that some branch's tree
    holds (ruling_home.value_resolves). Memory and the handoff hold only in-flight notes, so they
    never count for these two kinds (rule building-memory-is-short-term). When the cwd is in no git
    repo, or the layout cannot be read, these homes pass unchecked and a systemMessage says so;
  - an answer item (`[answer] -> page:<n>`, checked in every block that holds one, burst or not) has a
    home that is not `page:<digits>`, or the session's transcript shows no send after the owner's
    message: send_message or SendMessage naming n as a whole token, or an ArtifactData write whose
    input has key n equal to the item number under collection `items` (Answers, lint/_transcript.py
    reads the transcript). A missing or unreadable transcript passes, with a systemMessage;
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

ITEM = re.compile(r"- (fb-\S+)(?:\s+(.*))?$")
JOT = re.compile(r"\[(ruling|task|question|note|standing|answer)\]\s+->\s+\S")
ANSWER_HOME = re.compile(r"page:(\d+)")
SEND_TOOLS = ("mcp__claude-code-remote__send_message", "SendMessage")
ARTIFACT_DATA = ("ArtifactData", "mcp__ArtifactData")
HEADER = re.compile(r"### \d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:CDT|CST) \(UTC-0[56]:00\)$")
OPEN_KINDS = ("[ruling]", "[task]", "[standing]")
# Layout keys (lint/layout.json, or a repo's extras file) whose paths may hold each kind's home.
HOME_KINDS = {"ruling": ("decisions", "rules", "claude-md", "agents-md"),
              "task": ("todo", "debts", "debt-notes")}
FAIL_OPEN = "Feedback guard: ruling and task homes not checked (%s)."
FAIL_OPEN_ANSWERS = "Feedback guard: answer sends not checked (%s)."
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
    """[{stamp, text, items}] from the inbox. Lines inside a fence are never headers or items, and a
    `### ` line that is not the hook's own Central header is plain text."""
    blocks, fence = [], None
    for ln in text.split("\n"):
        ln = ln.rstrip("\r")
        if fence is not None:
            if re.fullmatch(r"`+", ln) and len(ln) >= len(fence):
                fence = None
            else:
                blocks[-1]["text"] = ln if blocks[-1]["text"] is None else blocks[-1]["text"] + "\n" + ln
        elif HEADER.match(ln):
            blocks.append({"stamp": ln[4:], "text": None, "items": [], "fenced": False})
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

    def problem(self, item_id, kind, rest):
        """None when the home is good or the check stood down, else the reason text."""
        try:
            import layout  # lint/layout.py, the one home of where each kind lives
        except ImportError as e:
            return self._stand_down(e)
        try:
            found = home_path(rest)
            if os.path.isabs(found):
                parent = os.path.dirname(found)
                root = self._root(parent) if os.path.isdir(parent) else None
                if root is None:
                    return "%s [%s] names %s, which is in no git repo" % (item_id, kind, found)
                rel = os.path.relpath(os.path.realpath(found), root)
            else:
                start = self.cwd if self.cwd and os.path.isdir(self.cwd) else None
                root = self._root(start) if start else None
                if root is None:
                    self.skip = self.skip or "the session's folder is in no git repo"
                    return None
                rel = os.path.normpath(found)
            rel = rel.replace(os.sep, "/")
            known = layout.kinds(root)
            base = layout.layout()["kinds"]
            homes = []
            for key in HOME_KINDS[kind]:
                if key in known:
                    homes += [layout.path(root, key)] + ([base[key]["path"].strip("/")] if key in base else [])
            homes = [h for h in dict.fromkeys(homes) if os.path.exists(os.path.join(root, *h.split("/")))]
            keys = ", ".join(HOME_KINDS[kind])
            if not homes:
                return ("%s [%s]: this repo has no %s home; none of the layout keys %s is in it"
                        % (item_id, kind, kind, keys))
            if not any(rel == h or rel.startswith(h + "/") for h in homes):
                return ("%s [%s] needs a home under %s (layout keys %s), never the handoff or memory"
                        % (item_id, kind, ", ".join(homes), keys))
            if not ruling_home.value_resolves(rel, root):
                return "%s [%s]: its home is not a file that git tracks on any branch" % (item_id, kind)
            return None
        except (layout.LayoutError, ruling_home._GitFailure) as e:
            return self._stand_down(e)

    def _stand_down(self, e):
        self.skip = self.skip or " ".join(str(e).split()) or type(e).__name__
        return None


class Answers:
    """Checks that each answer item's page number was sent to the page writer after the owner's
    message. The transcript loads once, on the first answer item. `skip` holds the reason the check
    stood down, once, for the systemMessage line."""

    def __init__(self, path):
        self.path, self.records, self.skip = path, None, None

    def _load(self):
        if self.records is None:
            self.records = []
            try:
                if not self.path:
                    raise OSError("no transcript_path in the payload")
                self.records = _transcript.read_transcript(self.path)
            except (OSError, ValueError) as e:
                self.skip = "the transcript cannot be read: %s" % (" ".join(str(e).split()) or type(e).__name__)
        return not self.skip

    def sent(self, text, n):
        """True when a send naming item n follows an owner record whose text is `text`."""
        if not self._load():
            return True
        text = (text or "").strip()
        for i, rec in enumerate(self.records):
            if _transcript.is_last_human(rec) and _record_text(rec) == text:
                if any(_proves(use, n) for r in self.records[i + 1:] if r.get("type") == "assistant"
                       for use in _transcript.tool_uses(r)):
                    return True
        return False


def _record_text(rec):
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                            and isinstance(b.get("text"), str))
    return content.strip() if isinstance(content, str) else None


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


def _has_n(node, n):
    if isinstance(node, dict):
        v = node.get("n")
        if (isinstance(v, int) and not isinstance(v, bool) and v == int(n)) or (
                isinstance(v, str) and v.isdigit() and int(v) == int(n)):
            return True
        return any(_has_n(c, n) for c in node.values())
    return isinstance(node, list) and any(_has_n(c, n) for c in node)


def _writes_n(node, n):
    """True when a dict that names the items collection holds key n == n at any depth below it."""
    if isinstance(node, dict):
        return (_in_items(node) and _has_n(node, n)) or any(_writes_n(c, n) for c in node.values())
    return isinstance(node, list) and any(_writes_n(c, n) for c in node)


def answer_problem(item_id, rest, text, answers):
    """None when the answer item's home is page:<n> and the send is proved, or the check stood down."""
    m = ANSWER_HOME.fullmatch(home_word(rest))
    if m is None:
        return "%s [answer] has a malformed answer home: it needs `page:<digits>`" % item_id
    if answers is None or answers.sent(text, m.group(1)):
        return None
    return ("%s [answer] page:%s: the transcript shows no send of this answer to the page writer after the"
            " owner's message; send it to the page writer (send_message naming %s, or an ArtifactData"
            " write with n %s)" % (item_id, m.group(1), m.group(1), m.group(1)))


def problems(blocks, handoff, homes=None, burst=(), answers=None):
    out = []
    for n, b in enumerate(blocks):
        if not b["items"] and n in burst:
            out.append("the message at %s (%s) has no items" % (b["stamp"], (b["text"] or "").split("\n")[0][:40]))
        for ln in b["items"]:
            it = item(ln)
            if it is None:
                out.append("the item line `%s` is malformed: it needs `- <id> [kind] -> home`" % ln[2:])
            elif not it[2]:
                out.append("%s needs `[kind] -> home`, kind one of ruling, task, question, note, standing,"
                           " answer" % it[0])
            elif it[1].startswith("[answer]"):
                found = answer_problem(it[0], it[1], b["text"], answers)
                if found:
                    out.append(found)
            elif homes is not None and it[1].startswith(("[ruling]", "[task]")):
                found = homes.problem(it[0], it[1][1:it[1].index("]")], it[1])
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
            homes, answers = Homes(hook.get("cwd")), Answers(hook.get("transcript_path"))
            reasons = problems(blocks, handoff, homes, burst, answers)
            notes = ([FAIL_OPEN % homes.skip] if homes.skip else []) + (
                [FAIL_OPEN_ANSWERS % answers.skip] if answers.skip else [])
            if notes:
                out["systemMessage"] = " ".join(notes)
        if reasons:
            out.update(decision="block", reason="Feedback inbox: " + "; ".join(reasons)
                       + ". Jot each burst message as `- <id> [kind] -> home` under it, file each ruling and task"
                       " in its tracked home, send each answer to the page writer, and put open standing ids in the handoff.")
        if out:
            print(json.dumps(out))
    except Exception as e:  # advisory: a crash passes, and says so on stderr
        print("feedback_guard: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
