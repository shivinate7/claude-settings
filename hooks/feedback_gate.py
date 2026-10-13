#!/usr/bin/env python3
"""Claude Code hook: feedback inbox gate (Stop). Decision owner-feedback-inbox.

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
OPEN_KINDS = ("[ruling]", "[task]", "[standing]")
REMINDER = "Feedback capture is open. Send `fb done` when the burst is over to close capture."


def parse(text):
    """[{stamp, text, items}] from the inbox. Lines inside a fence are never headers or items."""
    blocks, fence = [], None
    for ln in text.split("\n"):
        ln = ln.rstrip("\r")
        if fence is not None:
            if re.fullmatch(r"`+", ln) and len(ln) >= len(fence):
                fence = None
            elif blocks[-1]["text"] is None:
                blocks[-1]["text"] = ln
        elif ln.startswith("### "):
            blocks.append({"stamp": ln[4:], "text": None, "items": [], "fenced": False})
        elif blocks and not blocks[-1]["fenced"] and re.fullmatch(r"`{3,}", ln):
            fence, blocks[-1]["fenced"] = ln, True
        elif blocks and ln.startswith("- fb-"):
            blocks[-1]["items"].append(ln)
    return blocks


def problems(blocks, handoff):
    out = []
    for b in blocks:
        if not b["items"]:
            out.append("the message at %s (%s) has no items" % (b["stamp"], (b["text"] or "")[:40]))
        for ln in b["items"]:
            m = ITEM.match(ln)
            if not JOT.match(m.group(2) or ""):
                out.append("%s needs `[kind] -> home`, kind one of ruling, task, question, note, standing"
                           % m.group(1))
            elif m.group(2).startswith(OPEN_KINDS) and not re.search(
                    r"(?<![\w-])%s(?![\w-])" % re.escape(m.group(1)), handoff):
                out.append("%s is not in the handoff" % m.group(1))
    return out


def main():
    try:
        hook = json.load(sys.stdin)
        paths = local_time.inbox_paths(hook.get("session_id"))
        if hook.get("stop_hook_active") or paths is None:
            return 0
        inbox, marker = paths
        out = {"systemMessage": REMINDER} if os.path.exists(marker) else {}
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
