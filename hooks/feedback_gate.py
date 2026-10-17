#!/usr/bin/env python3
"""At Stop, blocks once when the owner's feedback inbox is malformed: a captured message with no item lines, a bad item line, or an open item whose id is missing from the handoff.

Reads <config dir>/handoffs/<session_id>.inbox.md, which local_time.py writes while the owner's
`fb` capture is open, and the session's handoff beside it. It blocks a turn end in these cases:
  - a captured message has no item lines under it;
  - an item line is not `- <id> [<kind>] -> <home>`, kind one of ruling, task, question, note, standing;
  - an open item (ruling, task, standing) has an id that is not a whole token in the handoff;
  - the inbox cannot be read. The block names the file: a Stop hook's stderr never reaches the owner,
    so a silent pass would drop feedback. This stays advisory, per decision gate-hooks-fail-closed:
    `stop_hook_active` true exits at once, so the block costs one turn at most.
While capture is open, stdout also carries a `systemMessage` that tells the owner to send `fb done`.
Format: see hooks/test_feedback_inbox.py. Exit 0 always. Any other error goes to stderr and passes.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import local_time  # noqa: E402  the one home of the inbox paths
import precompact_handoff  # noqa: E402  the one home of the handoff path

ITEM = re.compile(r"- (fb-\S+)(?:\s+(.*))?$")
JOT = re.compile(r"\[(ruling|task|question|note|standing)\]\s+->\s+\S")
HEADER = re.compile(r"### \d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:CDT|CST) \(UTC-0[56]:00\)$")
OPEN_KINDS = ("[ruling]", "[task]", "[standing]")
REMINDER = ("Feedback capture is open. Send `fb done` when the burst is over to close capture. "
            "It also ends after 10 minutes with no owner message.")


def parse(text):
    """[{stamp, text, items}] from the inbox. Lines inside a fence are never headers or items, and a
    `### ` line that is not the hook's own Central header is plain text."""
    blocks, fence = [], None
    for ln in text.split("\n"):
        ln = ln.rstrip("\r")
        if fence is not None:
            if re.fullmatch(r"`+", ln) and len(ln) >= len(fence):
                fence = None
            elif blocks[-1]["text"] is None:
                blocks[-1]["text"] = ln
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


def open_ids(blocks):
    """Ids of well-formed, not closed, open items (ruling, task, standing), in file order."""
    ids = []
    for b in blocks:
        for ln in b["items"]:
            it = item(ln)
            if it and it[2] and not it[3] and it[1].startswith(OPEN_KINDS):
                ids.append(it[0])
    return ids


def problems(blocks, handoff):
    out = []
    for b in blocks:
        if not b["items"]:
            out.append("the message at %s (%s) has no items" % (b["stamp"], (b["text"] or "")[:40]))
        for ln in b["items"]:
            it = item(ln)
            if it is None:
                out.append("the item line `%s` is malformed: it needs `- <id> [kind] -> home`" % ln[2:])
            elif not it[2]:
                out.append("%s needs `[kind] -> home`, kind one of ruling, task, question, note, standing"
                           % it[0])
        for i in open_ids([b]):
            if not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(i), handoff):
                out.append("%s is not in the handoff" % i)
    return out


def main():
    try:
        hook = json.load(sys.stdin)
        paths = local_time.inbox_paths(hook.get("session_id"))
        if hook.get("stop_hook_active") or paths is None:
            return 0
        inbox, marker = paths
        out = {"systemMessage": REMINDER} if local_time.is_open(marker) else {}
        try:
            with open(inbox, encoding="utf-8") as f:
                blocks = parse(f.read())
            try:
                with open(precompact_handoff.handoff_path(hook["session_id"]), encoding="utf-8",
                          errors="replace") as f:
                    handoff = f.read()
            except OSError:
                handoff = ""
            reasons = problems(blocks, handoff)
        except FileNotFoundError:
            reasons = []
        except (OSError, UnicodeDecodeError):
            reasons = ["the inbox file %s cannot be read" % os.path.basename(inbox)]
        if reasons:
            out.update(decision="block", reason="Feedback inbox: " + "; ".join(reasons)
                       + ". Jot each message as `- <id> [kind] -> home` under it, and put open ids in the handoff.")
        if out:
            print(json.dumps(out))
    except Exception as e:  # advisory: a crash passes, and says so on stderr
        print("feedback_gate: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
