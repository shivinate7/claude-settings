#!/usr/bin/env python3
"""Say whether a page answer a session fetched is the owner's word (skill waiting-page, "Read the answers" and "Route and close").

A receiving session reads the owner's answer itself and never trusts a peer's relay text. A script cannot call
ArtifactData, so the session fetches first, then runs this checker:

    ArtifactData get collection=answers doc_id=ID out_dir=DIR   (an absent doc saves no file)
    ArtifactData get collection=items   doc_id=ID out_dir=DIR
    python3 ~/.claude/skills/waiting-page/owner_word.py --root REPO_ROOT --page-url URL --item ID --fetched DIR [--pick KEY]

DIR holds `answers/ID.json` and `items/ID.json`, the data object of each doc. REPO_ROOT is the repo of the page; its
extras file holds the artifacts registry (lint/layout.py `artifacts()`). --pick binds the pick a peer relayed: a key,
or `a+c` for a multi item; the page's choice must equal it exactly.

Verdict, one line on stdout, then exit:
  counted item=ID n=N choice=C at=T [note=JSON]  exit 0. Choice of a multi item: keys joined by `+`; of a task: `done`.
  not counted: REASON                            exit 1. REASON names the failed rule.
  unknown: REASON                                exit 2. No readable registry or waiting-page entry, a fetched file that is
                                                 not one JSON object, or a crash.
Counted only when all hold:
  1. --page-url is the same artifact (layout.artifact_id) as the registry's `waiting-page` entry.
  2. answers/ID.json and items/ID.json exist. Relay text alone never counts.
  3. The answer's `item` is --item and the item's `id`, and the answer's `n` is the item's `n`.
  4. The answer's `at` is later than the item's `added`: an earlier answer belongs to an earlier ask.
  5. A decision (`kind` absent or `decision`): `choice` is the key of one option, or `overturn` when the item's `arbiter`
     is true. `none` never counts: it asks for new options, and the routing session judges a direction. A `multi` item
     takes a non-empty list of distinct keys; a list on a pick-one item or a string on a multi item does not count.
  6. A task (`kind: task`): `done` is true. A task answer with no `done` is never a grant.
  7. With --pick, the choice equals it.

Cost: one python process, reads the extras file and two fetched files, writes nothing. No git, no network, no timer.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.realpath(__file__))

COUNTED, NOT_COUNTED, UNKNOWN = 0, 1, 2


class Verdict(Exception):
    def __init__(self, line, code):
        super().__init__(line)
        self.line, self.code = line, code


def not_counted(reason):
    return Verdict("not counted: " + reason, NOT_COUNTED)


def unknown(reason):
    return Verdict("unknown: " + reason, UNKNOWN)


def load_layout():
    """lint/layout.py, from the repo that holds this script or from the installed ~/.claude layout."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
    sys.path.insert(1, os.path.join(os.path.expanduser("~"), ".claude", "lint"))
    import layout
    return layout


def moment(text, what):
    """An ISO timestamp as an aware datetime (a zone-less one is UTC); not counted when it is none."""
    if not isinstance(text, str):
        raise not_counted("%s is not a timestamp" % what)
    try:
        when = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise not_counted("%s is not an ISO timestamp" % what)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def read_doc(fetched, collection, item_id):
    """The one JSON object in <fetched>/<collection>/<item_id>.json, or None when the file is absent."""
    path = os.path.join(fetched, collection, item_id + ".json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as err:
        raise unknown("%s is not readable JSON: %s" % (path, err))
    if not isinstance(doc, dict):
        raise unknown("%s is not one JSON object" % path)
    return doc


def option_keys(item):
    options = item.get("options")
    if not isinstance(options, list):
        return []
    return [opt["key"] for opt in options if isinstance(opt, dict) and isinstance(opt.get("key"), str)]


def choice_of(item, answer):
    """The counted choice text of a decision or a task answer; not counted when the answer is no clear one."""
    kind = item.get("kind", "decision")
    if kind == "task":
        if answer.get("done") is not True:
            raise not_counted("task answer has no done: a note alone is never a grant")
        return "done"
    if kind != "decision":
        raise not_counted("item kind %r is neither decision nor task" % (kind,))
    keys = option_keys(item)
    choice = answer.get("choice")
    if item.get("multi") is True:
        if not isinstance(choice, list):
            raise not_counted("item takes several options and the choice is not a list")
        if not choice:
            raise not_counted("choice is an empty list")
        if len(set(map(str, choice))) != len(choice):
            raise not_counted("choice repeats a key")
        bad = [c for c in choice if not (isinstance(c, str) and c in keys)]
        if bad:
            raise not_counted("choice holds %s, not an option key" % json.dumps(bad[0]))
        return "+".join(choice)
    if isinstance(choice, list):
        raise not_counted("item takes one option and the choice is a list")
    if isinstance(choice, str) and choice in keys:
        return choice
    if choice == "none":
        raise not_counted("choice is none: it asks for new options, and the routing session judges that")
    if choice == "overturn":
        if item.get("arbiter") is True:
            return "overturn"
        raise not_counted("choice is overturn and the item is not an arbiter ruling")
    raise not_counted("choice %s is not an option key" % json.dumps(choice))


def judge(args):
    """The counted line, or a Verdict raised."""
    layout = load_layout()
    try:
        entries = layout.artifacts(args.root)
    except layout.LayoutError as err:
        raise unknown("the artifacts registry cannot be read: %s" % err)
    pages = [e for e in entries if e["role"] == layout.WAITING_ROLE]
    if not pages:
        raise unknown("%s has no waiting-page entry in its artifacts registry" % args.root)
    page_id = layout.artifact_id(args.page_url)
    if not page_id or page_id != layout.artifact_id(pages[0]["url"]):
        raise not_counted("page URL is not the registered waiting page")
    if not args.item or os.sep in args.item or "/" in args.item or args.item in (".", ".."):
        raise not_counted("item id %r is not a plain id" % args.item)

    answer = read_doc(args.fetched, "answers", args.item)
    if answer is None:
        raise not_counted("no saved answer: relayed text is not the owner's word")
    item = read_doc(args.fetched, "items", args.item)
    if item is None:
        raise not_counted("no saved item to read the answer against")

    if answer.get("item") != args.item or item.get("id") != args.item:
        raise not_counted("answer is for item %s, not %s" % (json.dumps(answer.get("item")), args.item))
    n = answer.get("n")
    if isinstance(n, bool) or not isinstance(n, int) or n != item.get("n"):
        raise not_counted("answer n %s is not the item's n %s: the answer is for another ask" % (n, item.get("n")))
    if moment(answer.get("at"), "answer at") <= moment(item.get("added"), "item added"):
        raise not_counted("answer is not later than the item's added time: it predates the ask")

    choice = choice_of(item, answer)
    if args.pick is not None and choice != args.pick:
        raise not_counted("page pick is %s, not %s" % (choice, args.pick))
    line = "counted item=%s n=%d choice=%s at=%s" % (args.item, n, choice, answer["at"])
    note = answer.get("note")
    if note:
        line += " note=" + json.dumps(note)
    return line


def main(argv=None):
    parser = argparse.ArgumentParser(description="Say whether a fetched page answer is the owner's word.")
    parser.add_argument("--root", required=True, help="repo root of the page (holds the extras file)")
    parser.add_argument("--page-url", required=True, help="the page URL the session was given")
    parser.add_argument("--item", required=True, help="the item id")
    parser.add_argument("--fetched", required=True, help="folder with answers/<id>.json and items/<id>.json")
    parser.add_argument("--pick", help="the pick a peer relayed: a key, or a+c for several")
    args = parser.parse_args(argv)
    try:
        line, code = judge(args), COUNTED
    except Verdict as verdict:
        line, code = verdict.line, verdict.code
    except Exception as err:  # a crash is unknown, never a grant
        line, code = "unknown: the checker crashed: %s: %s" % (type(err).__name__, err), UNKNOWN
    print(" ".join(line.splitlines()))
    return code


if __name__ == "__main__":
    sys.exit(main())
