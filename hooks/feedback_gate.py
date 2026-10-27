#!/usr/bin/env python3
"""At Stop, blocks once when the owner's feedback inbox is malformed or unreadable: a captured message with no item lines, a bad item line, a ruling or task whose home is not a tracked file of its kind, or an open standing item whose id is missing from the handoff.

Reads <config dir>/handoffs/<session_id>.inbox.md, which local_time.py writes while the owner's
`fb` capture is open, and the session's handoff beside it. It blocks a turn end in these cases:
  - a captured message has no item lines under it;
  - an item line is not `- <id> [<kind>] -> <home>`, kind one of ruling, task, question, note, standing;
  - a ruling or task item, open or closed, whose home is not a file under a home of its kind
    (HOME_KINDS, paths from lint/layout.py for the repo of the hook's cwd) that some branch's tree
    holds (ruling_home.value_resolves). Memory and the handoff hold only in-flight notes, so they
    never count for these two kinds (rule building-memory-is-short-term). When the cwd is in no git
    repo, or the layout cannot be read, these homes pass unchecked and a systemMessage says so;
  - an open standing item has an id that is not a whole token in the handoff;
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

LINT = os.path.join(HERE, "..", "lint")
if LINT not in sys.path:
    sys.path.insert(0, LINT)

import local_time  # noqa: E402  the one home of the inbox paths
import ruling_home  # noqa: E402  the one home of "a branch's tree holds this file"
import precompact_handoff  # noqa: E402  the one home of the handoff path

ITEM = re.compile(r"- (fb-\S+)(?:\s+(.*))?$")
JOT = re.compile(r"\[(ruling|task|question|note|standing)\]\s+->\s+\S")
HEADER = re.compile(r"### \d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:CDT|CST) \(UTC-0[56]:00\)$")
OPEN_KINDS = ("[ruling]", "[task]", "[standing]")
# Layout keys (lint/layout.json, or a repo's extras file) whose paths may hold each kind's home.
HOME_KINDS = {"ruling": ("decisions", "rules", "claude-md", "agents-md"),
              "task": ("todo", "debts", "debt-notes")}
FAIL_OPEN = "Feedback gate: ruling and task homes not checked (%s)."
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


def open_ids(blocks, kinds=OPEN_KINDS):
    """Ids of well-formed, not closed, open items (ruling, task, standing, or `kinds`), in file order."""
    ids = []
    for b in blocks:
        for ln in b["items"]:
            it = item(ln)
            if it and it[2] and not it[3] and it[1].startswith(kinds):
                ids.append(it[0])
    return ids


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


def problems(blocks, handoff, homes=None):
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
            homes = Homes(hook.get("cwd"))
            reasons = problems(blocks, handoff, homes)
            if homes.skip:
                note = FAIL_OPEN % homes.skip
                out["systemMessage"] = (out["systemMessage"] + "\n" + note) if out else note
        except FileNotFoundError:
            reasons = []
        except (OSError, UnicodeDecodeError):
            reasons = ["the inbox file %s cannot be read" % os.path.basename(inbox)]
        if reasons:
            out.update(decision="block", reason="Feedback inbox: " + "; ".join(reasons)
                       + ". Jot each message as `- <id> [kind] -> home` under it, file each ruling and task in its"
                       " tracked home, and put open standing ids in the handoff.")
        if out:
            print(json.dumps(out))
    except Exception as e:  # advisory: a crash passes, and says so on stderr
        print("feedback_gate: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
